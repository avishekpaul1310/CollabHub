from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from .models import WorkItem, Message, Notification, NotificationPreference, ScheduledMessage, MessageReadReceipt
from .forms import WorkItemForm, MessageForm, ThreadForm
from django.db.models import Q
from django.db import IntegrityError
from .models import Thread, FileAttachment, SlowChannel, SlowChannelMessage
from .forms import FileAttachmentForm, NotificationPreferenceForm, ScheduledMessageForm, SlowChannelForm, SlowChannelParticipantsForm, SlowChannelMessageForm
import logging
from django.utils import timezone
from django.contrib.auth.models import User
import json

logger = logging.getLogger(__name__)

@login_required
def dashboard(request):
    # Get all items where user is either owner or collaborator
    work_items = WorkItem.objects.filter(
        Q(owner=request.user) | Q(collaborators=request.user)
    ).distinct()
    
    context = {
        'work_items': work_items
    }
    return render(request, 'workspace/dashboard.html', context)

@login_required
def work_item_detail(request, pk):
    work_item = get_object_or_404(WorkItem, pk=pk)
    
    # Check if user has access to this work item
    if work_item.owner != request.user and request.user not in work_item.collaborators.all():
        messages.error(request, "You don't have permission to view this work item.")
        return redirect('dashboard')
    
    # Get threads for this work item that the user can access
    user_threads = Thread.objects.filter(work_item=work_item)
    threads = [thread for thread in user_threads if thread.user_can_access(request.user)]
    
    # Get slow channels for this work item
    slow_channels = SlowChannel.objects.filter(work_item=work_item, participants=request.user)
    
    # Get files
    files = work_item.files.all() if hasattr(work_item, 'files') else []
    
    # Mark notifications for this work item as read
    if request.user.is_authenticated:
        Notification.objects.filter(
            user=request.user,
            work_item=work_item,
            is_read=False
        ).update(is_read=True)
    
    context = {
        'work_item': work_item,
        'threads': threads,
        'slow_channels': slow_channels,
        'files': files
    }
    return render(request, 'workspace/work_item_detail.html', context)

@login_required
def thread_detail(request, work_item_pk, thread_pk):
    work_item = get_object_or_404(WorkItem, pk=work_item_pk)
    thread = get_object_or_404(Thread, pk=thread_pk, work_item=work_item)
    
    # Check if user has permission to view this thread
    if not thread.user_can_access(request.user):
        # Log access attempt for debugging
        logger.warning(
            f"Access denied to thread #{thread_pk} for user {request.user.username}. " +
            f"Thread is {'public' if thread.is_public else 'private'}, " +
            f"user is {'owner' if work_item.owner == request.user else 'not owner'}, " +
            f"user is {'collaborator' if request.user in work_item.collaborators.all() else 'not collaborator'}, " +
            f"user is {'in allowed_users' if request.user in thread.allowed_users.all() else 'not in allowed_users'}"
        )
        messages.error(request, "You don't have permission to view this thread.")
        return redirect('work_item_detail', pk=work_item.pk)
    
    # Get messages
    messages_list = thread.thread_messages.filter(Q(parent=None) | Q(is_thread_starter=True)).order_by('created_at')
    
    # For each message, preload its replies
    for message in messages_list:
        message.replies_list = message.replies.all()
    
    # Get the list of participants who can view this thread
    participants = thread.get_participants()
    
    context = {
        'work_item': work_item,
        'thread': thread,
        'messages': messages_list,
        'participants': participants,
        'is_public': thread.is_public
    }
    return render(request, 'workspace/thread_detail.html', context)

@login_required
def create_thread(request, work_item_pk):
    work_item = get_object_or_404(WorkItem, pk=work_item_pk)
    
    # Check if user has permission to create threads in this work item
    if work_item.owner != request.user and request.user not in work_item.collaborators.all():
        messages.error(request, "You don't have permission to create threads in this work item.")
        return redirect('work_item_detail', pk=work_item.pk)
    
    if request.method == 'POST':
        form = ThreadForm(request.POST, work_item=work_item, user=request.user)
        if form.is_valid():
            thread = form.save()
            messages.success(request, f'Thread "{thread.title}" has been created!')
            return redirect('thread_detail', work_item_pk=work_item.pk, thread_pk=thread.pk)
    else:
        form = ThreadForm(work_item=work_item, user=request.user)
    
    context = {
        'form': form,
        'work_item': work_item,
        'title': 'Create Thread'
    }
    return render(request, 'workspace/thread_form.html', context)

@login_required
def update_thread(request, work_item_pk, thread_pk):
    work_item = get_object_or_404(WorkItem, pk=work_item_pk)
    thread = get_object_or_404(Thread, pk=thread_pk, work_item=work_item)
    
    # Check permissions
    if thread.created_by != request.user and work_item.owner != request.user:
        messages.error(request, "You don't have permission to edit this thread.")
        return redirect('thread_detail', work_item_pk=work_item.pk, thread_pk=thread.pk)
    
    if request.method == 'POST':
        form = ThreadForm(request.POST, instance=thread, work_item=work_item, user=request.user)
        if form.is_valid():
            thread = form.save()
            messages.success(request, f'Thread "{thread.title}" has been updated!')
            return redirect('thread_detail', work_item_pk=work_item.pk, thread_pk=thread.pk)
    else:
        form = ThreadForm(instance=thread, work_item=work_item, user=request.user)
    
    context = {
        'form': form,
        'work_item': work_item,
        'thread': thread,
        'title': 'Update Thread'
    }
    return render(request, 'workspace/thread_form.html', context)


@login_required
def create_work_item(request):
    if request.method == 'POST':
        # Always pass the current user to the form
        form = WorkItemForm(request.POST, user=request.user)
        
        # Add debugging to see if the form is valid
        print(f"Form submitted. Is valid: {form.is_valid()}")
        if not form.is_valid():
            print(f"Form errors: {form.errors}")
        
        if form.is_valid():
            try:
                work_item = form.save()
                messages.success(request, f'"{work_item.title}" has been created successfully!')
                return redirect('work_item_detail', pk=work_item.pk)
            except Exception as e:
                print(f"Error when saving form: {str(e)}")
                messages.error(request, f"An error occurred: {str(e)}")
    else:
        # Pass user when initializing a new form
        form = WorkItemForm(user=request.user)
    
    context = {
        'form': form,
        'title': 'Create Work Item'
    }
    return render(request, 'workspace/work_item_form.html', context)

@login_required
def update_work_item(request, pk):
    work_item = get_object_or_404(WorkItem, pk=pk)
    
    # Check if user is owner
    if work_item.owner != request.user:
        messages.error(request, "You don't have permission to edit this work item.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = WorkItemForm(request.POST, instance=work_item, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f'"{work_item.title}" has been updated!')
            return redirect('work_item_detail', pk=work_item.pk)
    else:
        form = WorkItemForm(instance=work_item, user=request.user)
    
    context = {
        'form': form,
        'title': 'Update Work Item'
    }
    return render(request, 'workspace/work_item_form.html', context)

@login_required
def delete_work_item(request, pk):
    work_item = get_object_or_404(WorkItem, pk=pk)
    
    # Check if user is the owner
    if request.user != work_item.owner:
        messages.error(request, "You don't have permission to delete this item.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        work_item_title = work_item.title
        work_item.delete()
        messages.success(request, f'"{work_item_title}" has been deleted!')
        return redirect('dashboard')
    
    context = {'work_item': work_item}
    return render(request, 'workspace/work_item_confirm_delete.html', context)


@login_required
def upload_file(request, pk):
    work_item = get_object_or_404(WorkItem, pk=pk)
    
    if request.method == 'POST' and request.FILES.get('file'):
        uploaded_file = request.FILES['file']
        
        # Create the file attachment
        FileAttachment.objects.create(
            work_item=work_item,
            file=uploaded_file,
            name=uploaded_file.name,
            uploaded_by=request.user
        )
        
        return redirect('work_item_detail', pk=work_item.pk)
    
    return redirect('work_item_detail', pk=work_item.pk)

# Add these to your existing views.py

@login_required
def notifications_list(request):
    notifications = request.user.notifications.all()
    unread_count = notifications.filter(is_read=False).count()
    
    context = {
        'notifications': notifications,
        'unread_count': unread_count
    }
    return render(request, 'workspace/notifications_list.html', context)

@login_required
def mark_notification_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.is_read = True
    notification.save()
    
    # If this is an AJAX request, return a JSON response
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success'})
    
    # Otherwise redirect back to notifications list
    return redirect('notifications_list')

@login_required
def mark_all_read(request):
    request.user.notifications.update(is_read=True)
    
    # If this is an AJAX request, return a JSON response
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success'})
    
    # Otherwise redirect back to notifications list
    return redirect('notifications_list')

@login_required
def notification_preferences(request):
    """View to manage notification preferences"""
    try:
        preferences = request.user.notification_preferences
    except NotificationPreference.DoesNotExist:
        preferences = NotificationPreference.objects.create(user=request.user)
    
    if request.method == 'POST':
        form = NotificationPreferenceForm(request.POST, instance=preferences)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your notification preferences have been updated!')
            return redirect('notification_preferences')
    else:
        form = NotificationPreferenceForm(instance=preferences)
    
    # Get all work items for mute settings
    work_items = WorkItem.objects.filter(
        Q(owner=request.user) | Q(collaborators=request.user)
    ).distinct()
    
    muted_items = preferences.muted_channels.all()
    
    context = {
        'form': form,
        'work_items': work_items,
        'muted_items': muted_items
    }
    return render(request, 'workspace/notification_preferences.html', context)

@login_required
def toggle_mute_work_item(request, pk):
    """Ajax view to toggle muting a work item"""
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        work_item = get_object_or_404(WorkItem, pk=pk)
        preferences = request.user.notification_preferences
        
        if preferences.muted_channels.filter(id=pk).exists():
            preferences.muted_channels.remove(work_item)
            is_muted = False
        else:
            preferences.muted_channels.add(work_item)
            is_muted = True
        
        return JsonResponse({'status': 'success', 'is_muted': is_muted})
    
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def schedule_message(request, work_item_pk, thread_pk=None, parent_message_pk=None):
    """View to schedule a message for future sending"""
    work_item = get_object_or_404(WorkItem, pk=work_item_pk)
    thread = None
    parent_message = None
    
    # Get thread if applicable
    if thread_pk:
        thread = get_object_or_404(Thread, pk=thread_pk, work_item=work_item)
        # Check if user has access to this thread
        if not thread.user_can_access(request.user):
            messages.error(request, "You don't have permission to schedule messages in this thread.")
            return redirect('work_item_detail', pk=work_item.pk)
    
    # Get parent message if applicable
    if parent_message_pk:
        parent_message = get_object_or_404(Message, pk=parent_message_pk)
        # Ensure the parent message belongs to the right thread/work item
        if (thread and parent_message.thread != thread) or parent_message.work_item != work_item:
            messages.error(request, "Invalid parent message.")
            return redirect('work_item_detail', pk=work_item.pk)
    
    if request.method == 'POST':
        form = ScheduledMessageForm(
            request.POST, 
            sender=request.user,
            work_item=work_item,
            thread=thread,
            parent_message=parent_message
        )
        
        if form.is_valid():
            scheduled_msg = form.save()
            
            # Success message with scheduled time
            from django.utils import timezone
            from django.conf import settings
            
            # Format the time in user's timezone if available, otherwise use server timezone
            local_time = scheduled_msg.scheduled_time
            if hasattr(request, 'timezone'):
                local_time = timezone.localtime(scheduled_msg.scheduled_time, timezone=request.timezone)
            
            # Format the time
            formatted_time = local_time.strftime('%b %d, %Y at %I:%M %p')
            messages.success(request, f"Message scheduled for {formatted_time}")
            
            # Redirect to the appropriate page
            if thread:
                return redirect('thread_detail', work_item_pk=work_item.pk, thread_pk=thread.pk)
            else:
                return redirect('work_item_detail', pk=work_item.pk)
    else:
        # Suggest a good default time - work hours next day or after weekend
        import datetime
        from django.utils import timezone
        
        now = timezone.now()
        suggestion = now + datetime.timedelta(days=1)
        
        # If it's Friday, schedule for Monday
        if suggestion.weekday() >= 4:  # Friday(4), Saturday(5) or Sunday(6)
            # Add days to get to Monday
            days_to_add = 7 - suggestion.weekday() + 1 if suggestion.weekday() == 6 else 8 - suggestion.weekday()
            suggestion = now + datetime.timedelta(days=days_to_add)
        
        # Set to 9 AM
        suggestion = suggestion.replace(hour=9, minute=0, second=0, microsecond=0)
        
        # Initialize form with suggested time
        form = ScheduledMessageForm(
            sender=request.user,
            work_item=work_item,
            thread=thread,
            parent_message=parent_message,
            initial={'scheduled_time': suggestion}
        )
    
    context = {
        'form': form,
        'work_item': work_item,
        'thread': thread,
        'parent_message': parent_message,
        'title': 'Schedule Message'
    }
    return render(request, 'workspace/schedule_message_form.html', context)

@login_required
def my_scheduled_messages(request):
    """View to list and manage all scheduled messages for the current user"""
    # Get all pending scheduled messages
    scheduled_messages = ScheduledMessage.objects.filter(
        sender=request.user,
        is_sent=False
    ).order_by('scheduled_time')
    
    # Get all sent scheduled messages (limited to recent ones)
    sent_messages = ScheduledMessage.objects.filter(
        sender=request.user,
        is_sent=True
    ).order_by('-sent_at')[:20]  # Limit to 20 most recent
    
    context = {
        'pending_messages': scheduled_messages,
        'sent_messages': sent_messages,
    }
    return render(request, 'workspace/my_scheduled_messages.html', context)

@login_required
def cancel_scheduled_message(request, pk):
    """View to cancel a scheduled message"""
    message = get_object_or_404(ScheduledMessage, pk=pk, sender=request.user, is_sent=False)
    
    if request.method == 'POST':
        # Store info for success message
        work_item_title = message.work_item.title
        thread_title = message.thread.title if message.thread else None
        scheduled_time = message.scheduled_time
        
        # Delete the message
        message.delete()
        
        # Success message
        messages.success(request, f"Scheduled message for {scheduled_time.strftime('%b %d at %I:%M %p')} has been cancelled.")
        
        # Redirect back to scheduled messages list
        return redirect('my_scheduled_messages')
    
    context = {
        'message': message,
    }
    return render(request, 'workspace/cancel_scheduled_message.html', context)

@login_required
def edit_scheduled_message(request, pk):
    """View to edit a scheduled message"""
    message = get_object_or_404(ScheduledMessage, pk=pk, sender=request.user, is_sent=False)
    
    if request.method == 'POST':
        form = ScheduledMessageForm(
            request.POST, 
            instance=message,
            sender=request.user,
            work_item=message.work_item,
            thread=message.thread,
            parent_message=message.parent_message
        )
        
        if form.is_valid():
            form.save()
            messages.success(request, "Scheduled message has been updated.")
            return redirect('my_scheduled_messages')
    else:
        form = ScheduledMessageForm(
            instance=message,
            sender=request.user,
            work_item=message.work_item,
            thread=message.thread,
            parent_message=message.parent_message
        )
    
    context = {
        'form': form,
        'message': message,
        'title': 'Edit Scheduled Message'
    }
    return render(request, 'workspace/schedule_message_form.html', context)


@csrf_exempt
@require_POST
@login_required
def mark_message_read(request, message_id):
    """API endpoint to mark a message as read"""
    try:
        message = get_object_or_404(Message, pk=message_id)
        thread = message.thread
        work_item = message.work_item
        
        # Check if user has access to this message
        if (thread and not thread.user_can_access(request.user)) or \
           (not thread and work_item.owner != request.user and request.user not in work_item.collaborators.all()):
            return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)
        
        # Skip if user is the message author
        if message.user == request.user:
            return JsonResponse({'status': 'success', 'message': 'Skipped own message'})
        
        # Check if user has disabled sharing read receipts
        try:
            user_preferences = request.user.notification_preferences
            if not user_preferences.share_read_receipts:
                # Still track internally that user has seen the message, but don't create visible receipt
                return JsonResponse({'status': 'success', 'message': 'Read receipts disabled by user'})
        except AttributeError:
            # If no preferences exist, use default behavior (share receipts)
            pass
        
        # Create read receipt (ignore if already exists)
        try:
            receipt, created = MessageReadReceipt.objects.get_or_create(
                message=message,
                user=request.user
            )
            
            if created:
                return JsonResponse({'status': 'success', 'message': 'Marked as read'})
            else:
                return JsonResponse({'status': 'success', 'message': 'Already read'})
                
        except IntegrityError:
            # Handle race condition
            return JsonResponse({'status': 'success', 'message': 'Already read (concurrent)'})
            
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# Update the get_message_read_status view in workspace/views.py

@login_required
def get_message_read_status(request, message_id):
    """API endpoint to get read status of a message"""
    try:
        message = get_object_or_404(Message, pk=message_id)
        thread = message.thread
        work_item = message.work_item
        
        # Check if user has access to this message
        if (thread and not thread.user_can_access(request.user)) or \
           (not thread and work_item.owner != request.user and request.user not in work_item.collaborators.all()):
            return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)
        
        # Only message author can see read receipts
        if message.user != request.user:
            return JsonResponse({'status': 'error', 'message': 'Only the author can see read receipts'}, status=403)
        
        # Get read receipts
        receipts = message.read_receipts.all().select_related('user')
        
        # Get list of users who have access but haven't read
        if thread:
            participants = thread.get_participants()
        else:
            participants = list(work_item.collaborators.all())
            participants.append(work_item.owner)
        
        # Remove message author and users who have read
        readers = [receipt.user for receipt in receipts]
        participants = [p for p in participants if p != message.user and p not in readers]
        
        # Filter out users who have disabled sharing read receipts
        from django.db.models import Q
        users_not_sharing = User.objects.filter(
            Q(notification_preferences__share_read_receipts=False) | 
            Q(notification_preferences__isnull=True)
        ).values_list('id', flat=True)
        
        # Format response
        response = {
            'status': 'success',
            'read_by': [
                {
                    'username': receipt.user.username,
                    'read_at': receipt.read_at.isoformat(),
                    'user_id': receipt.user.id
                }
                for receipt in receipts if receipt.user.id not in users_not_sharing
            ],
            'pending': [
                {
                    'username': user.username,
                    'user_id': user.id
                }
                for user in participants if user.id not in users_not_sharing
            ],
            'total_read': len(receipts),
            'total_pending': len(participants),
            'note': 'Some users may have disabled sharing read receipts'
        }
        
        return JsonResponse(response)
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# Optional: Bulk marker for thread read status
@csrf_exempt
@require_POST
@login_required
def mark_thread_read(request, thread_id):
    """Mark all messages in a thread as read"""
    try:
        thread = get_object_or_404(Thread, pk=thread_id)
        
        # Check if user has access to this thread
        if not thread.user_can_access(request.user):
            return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)
        
        # Get all messages in thread not authored by current user
        messages = Message.objects.filter(thread=thread).exclude(user=request.user)
        
        # Mark all as read
        read_count = 0
        for message in messages:
            try:
                receipt, created = MessageReadReceipt.objects.get_or_create(
                    message=message,
                    user=request.user
                )
                if created:
                    read_count += 1
            except IntegrityError:
                # Skip if already exists
                pass
        
        return JsonResponse({
            'status': 'success', 
            'message': f'Marked {read_count} messages as read',
            'read_count': read_count
        })
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def create_slow_channel(request, work_item_pk):
    """View to create a new slow channel for a work item"""
    work_item = get_object_or_404(WorkItem, pk=work_item_pk)
    
    # Check if user has permission to create channels in this work item
    if work_item.owner != request.user and request.user not in work_item.collaborators.all():
        messages.error(request, "You don't have permission to create channels in this work item.")
        return redirect('work_item_detail', pk=work_item.pk)
    
    if request.method == 'POST':
        form = SlowChannelForm(request.POST, work_item=work_item, user=request.user)
        participants_form = SlowChannelParticipantsForm(request.POST, work_item=work_item)
        
        if form.is_valid() and participants_form.is_valid():
            try:
                # Save the channel
                channel = form.save()
                
                # Add selected participants
                participants = participants_form.cleaned_data.get('participants', [])
                for participant in participants:
                    channel.participants.add(participant)
                
                # Always make sure creator is a participant
                channel.participants.add(request.user)
                
                messages.success(request, f'Slow channel "{channel.title}" has been created!')
                return redirect('slow_channel_detail', channel_pk=channel.pk)
            except Exception as e:
                # Log the error
                logger.error(f"Error creating slow channel: {str(e)}")
                messages.error(request, f"Error creating slow channel: {str(e)}")
        else:
            # Add form errors as messages for visibility
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            
            for field, errors in participants_form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = SlowChannelForm(work_item=work_item, user=request.user)
        participants_form = SlowChannelParticipantsForm(work_item=work_item)
    
    context = {
        'form': form,
        'participants_form': participants_form,
        'work_item': work_item,
        'title': 'Create Slow Channel'
    }
    return render(request, 'workspace/slow_channel_form.html', context)

@login_required
def update_slow_channel(request, channel_pk):
    """View to update a slow channel"""
    channel = get_object_or_404(SlowChannel, pk=channel_pk)
    work_item = channel.work_item
    
    # Check permissions
    if channel.created_by != request.user and work_item.owner != request.user:
        messages.error(request, "You don't have permission to edit this channel.")
        return redirect('slow_channel_detail', channel_pk=channel.pk)
    
    if request.method == 'POST':
        form = SlowChannelForm(request.POST, instance=channel, work_item=work_item, user=request.user)
        participants_form = SlowChannelParticipantsForm(request.POST, work_item=work_item, channel=channel)
        
        if form.is_valid() and participants_form.is_valid():
            channel = form.save()
            
            # Update participants
            channel.participants.clear()
            participants = participants_form.cleaned_data['participants']
            for participant in participants:
                channel.participants.add(participant)
            
            # Always make sure creator is a participant
            channel.participants.add(channel.created_by)
            
            messages.success(request, f'Slow channel "{channel.title}" has been updated!')
            return redirect('slow_channel_detail', channel_pk=channel.pk)
    else:
        form = SlowChannelForm(instance=channel, work_item=work_item, user=request.user)
        participants_form = SlowChannelParticipantsForm(work_item=work_item, channel=channel)
    
    context = {
        'form': form,
        'participants_form': participants_form,
        'channel': channel,
        'work_item': work_item,
        'title': 'Update Slow Channel'
    }
    return render(request, 'workspace/slow_channel_form.html', context)

@login_required
def slow_channel_detail(request, channel_pk):
    """View to display a slow channel"""
    channel = get_object_or_404(SlowChannel, pk=channel_pk)
    work_item = channel.work_item
    
    # Check if user is a participant
    if request.user not in channel.participants.all():
        messages.error(request, "You're not a participant in this slow channel.")
        return redirect('work_item_detail', pk=work_item.pk)
    
    # Get delivered messages
    messages_list = channel.messages.filter(
        is_delivered=True,
        parent=None  # Only top-level messages
    ).order_by('-created_at')
    
    # For each message, attach its replies
    for message in messages_list:
        message.replies_list = message.replies.filter(is_delivered=True).order_by('created_at')
    
    # Check if user can post based on minimum interval
    can_post = True
    time_until_next_post = None
    
    last_message = SlowChannelMessage.objects.filter(
        channel=channel,
        user=request.user
    ).order_by('-created_at').first()
    
    if last_message:
        time_since_last = timezone.now() - last_message.created_at
        min_interval = channel.min_response_interval
        
        if time_since_last < min_interval:
            can_post = False
            time_left = min_interval - time_since_last
            # Convert to minutes or hours
            minutes_left = round(time_left.total_seconds() / 60)
            
            if minutes_left > 60:
                time_until_next_post = f"{round(minutes_left/60, 1)} hours"
            else:
                time_until_next_post = f"{minutes_left} minutes"
    
    # Process message form
    if request.method == 'POST':
        # Check if it's a reply
        parent_id = request.POST.get('parent_id')
        parent = None
        
        if parent_id:
            parent = get_object_or_404(SlowChannelMessage, pk=parent_id, channel=channel)
            # For replies, we don't enforce the minimum interval
            can_post = True
        
        if can_post:
            form = SlowChannelMessageForm(
                request.POST,
                channel=channel,
                user=request.user,
                parent=parent
            )
            
            if form.is_valid():
                message = form.save()
                
                if parent:
                    messages.success(request, "Your reply has been scheduled and will be delivered soon.")
                else:
                    next_delivery = message.scheduled_delivery
                    formatted_time = next_delivery.strftime('%b %d at %I:%M %p')
                    messages.success(
                        request, 
                        f"Your message has been scheduled for delivery on {formatted_time}. "
                        f"This is a slow channel - messages are intentionally delayed to encourage thoughtful communication."
                    )
                
                return redirect('slow_channel_detail', channel_pk=channel.pk)
        else:
            messages.error(
                request,
                f"Please wait {time_until_next_post} before posting again. "
                f"This channel has a minimum interval of {channel.min_response_interval.total_seconds()/3600} "
                f"hours between messages to encourage thoughtful communication."
            )
    
    # Always have an empty form ready
    form = SlowChannelMessageForm(channel=channel, user=request.user)
    
    context = {
        'channel': channel,
        'work_item': work_item,
        'messages': messages_list,
        'form': form,
        'can_post': can_post,
        'time_until_next_post': time_until_next_post
    }
    return render(request, 'workspace/slow_channel_detail.html', context)

@login_required
def delete_slow_channel(request, channel_pk):
    """View to delete a slow channel"""
    channel = get_object_or_404(SlowChannel, pk=channel_pk)
    work_item = channel.work_item
    
    # Check permissions
    if channel.created_by != request.user and work_item.owner != request.user:
        messages.error(request, "You don't have permission to delete this channel.")
        return redirect('slow_channel_detail', channel_pk=channel.pk)
    
    if request.method == 'POST':
        channel_title = channel.title
        channel.delete()
        messages.success(request, f'Slow channel "{channel_title}" has been deleted!')
        return redirect('work_item_detail', pk=work_item.pk)
    
    context = {
        'channel': channel,
        'work_item': work_item
    }
    return render(request, 'workspace/slow_channel_confirm_delete.html', context)

@login_required
def my_slow_channels(request):
    """View to list all slow channels the user participates in"""
    # Get all channels where user is a participant
    channels = SlowChannel.objects.filter(participants=request.user).order_by('-created_at')
    
    context = {
        'channels': channels
    }
    return render(request, 'workspace/my_slow_channels.html', context)

@login_required
def join_slow_channel(request, channel_pk):
    """View to join a slow channel"""
    channel = get_object_or_404(SlowChannel, pk=channel_pk)
    work_item = channel.work_item
    
    # Check if user has access to work item
    if work_item.owner != request.user and request.user not in work_item.collaborators.all():
        messages.error(request, "You don't have permission to join this channel.")
        return redirect('work_item_detail', pk=work_item.pk)
    
    # Add user as participant
    channel.participants.add(request.user)
    
    messages.success(request, f'You have joined the slow channel "{channel.title}"!')
    return redirect('slow_channel_detail', channel_pk=channel.pk)

@login_required
def leave_slow_channel(request, channel_pk):
    """View to leave a slow channel"""
    channel = get_object_or_404(SlowChannel, pk=channel_pk)
    
    # Can't leave if you're the creator
    if channel.created_by == request.user:
        messages.error(request, "As the creator, you cannot leave this channel.")
        return redirect('slow_channel_detail', channel_pk=channel.pk)
    
    # Remove user as participant
    channel.participants.remove(request.user)
    
    messages.success(request, f'You have left the slow channel "{channel.title}"')
    return redirect('work_item_detail', pk=channel.work_item.pk)

@require_GET
@login_required
def get_online_status_preference(request):
    """API endpoint to get current user's online status preference"""
    try:
        try:
            preferences = request.user.notification_preferences
            show_online_status = preferences.show_online_status
        except:
            show_online_status = False
            
        return JsonResponse({
            'status': 'success',
            'show_online_status': show_online_status
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@require_POST
@login_required
def update_online_status(request):
    """API endpoint to update user's online status"""
    try:
        data = json.loads(request.body)
        status = data.get('status', 'offline')
        
        # Check if user has enabled online status
        try:
            preferences = request.user.notification_preferences
            if not preferences.show_online_status:
                return JsonResponse({'status': 'error', 'message': 'Online status disabled'}, status=400)
        except:
            return JsonResponse({'status': 'error', 'message': 'Preferences not found'}, status=404)
        
        return JsonResponse({
            'status': 'success',
            'online_status': status
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@require_GET
@login_required
def get_user_online_status(request, user_id):
    """API endpoint to get another user's online status"""
    try:
        from django.contrib.auth.models import User
        
        # Get the target user
        user = get_object_or_404(User, pk=user_id)
        
        # Check if target user has enabled online status
        try:
            preferences = user.notification_preferences
            if not preferences.show_online_status:
                return JsonResponse({'status': 'hidden', 'message': 'User has disabled online status'})
        except:
            return JsonResponse({'status': 'unknown', 'message': 'Preferences not found'})
        
        # In a real app, you would fetch the actual status from your storage
        # For simplicity, we'll return a placeholder
        return JsonResponse({
            'status': 'success',
            'online_status': 'unknown',  # In production, this would be 'active', 'away', or 'offline'
            'user_id': user_id,
            'username': user.username
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
@login_required
def get_work_life_balance_preferences(request):
    """API endpoint to get work-life balance preferences for the current user"""
    try:
        try:
            preferences = request.user.notification_preferences
            data = {
                'show_online_status': preferences.show_online_status,
                'share_working_hours': preferences.share_working_hours,
                'away_mode': preferences.away_mode,
                'away_message': preferences.away_message,
                'auto_away_after': preferences.auto_away_after,
                'break_frequency': preferences.break_frequency,
                'work_days': preferences.work_days,
                'work_start_time': preferences.work_start_time.strftime('%H:%M') if preferences.work_start_time else None,
                'work_end_time': preferences.work_end_time.strftime('%H:%M') if preferences.work_end_time else None,
                'lunch_break_start': preferences.lunch_break_start.strftime('%H:%M') if preferences.lunch_break_start else None,
                'lunch_break_duration': preferences.lunch_break_duration
            }
        except:
            # Default values if preferences don't exist
            data = {
                'show_online_status': False,
                'share_working_hours': True,
                'away_mode': False,
                'away_message': '',
                'auto_away_after': 30,
                'break_frequency': 60,
                'work_days': '12345',
                'work_start_time': '09:00',
                'work_end_time': '17:00',
                'lunch_break_start': None,
                'lunch_break_duration': 60
            }
            
        return JsonResponse({
            'status': 'success',
            **data
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)