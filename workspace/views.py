from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from .models import WorkItem, Message, Notification, NotificationPreference, ScheduledMessage, MessageReadReceipt
from .forms import WorkItemForm, MessageForm, ThreadForm
from django.db.models import Q
from django.db import IntegrityError
from .models import Thread, FileAttachment
from .forms import FileAttachmentForm, NotificationPreferenceForm, ScheduledMessageForm
import logging

logger = logging.getLogger(__name__)

@login_required
def dashboard(request):
    # Get all items where user is either owner or collaborator
    work_item = WorkItem.objects.filter(
        Q(owner=request.user) | Q(collaborators=request.user)
    ).distinct()
    
    context = {
        'work_item': work_item
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
        
        # Format response
        response = {
            'status': 'success',
            'read_by': [
                {
                    'username': receipt.user.username,
                    'read_at': receipt.read_at.isoformat(),
                    'user_id': receipt.user.id
                }
                for receipt in receipts
            ],
            'pending': [
                {
                    'username': user.username,
                    'user_id': user.id
                }
                for user in participants
            ],
            'total_read': len(receipts),
            'total_pending': len(participants)
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