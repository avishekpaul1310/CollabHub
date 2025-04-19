# Fix for libmagic on Windows
import sys
import os

# Define this before the magic import
if sys.platform.startswith('win'):
    # Try to set the PATH to include the python-magic-bin DLL directory
    try:
        import site
        # Look for the DLL in site-packages
        for site_path in site.getsitepackages():
            magic_bin_path = os.path.join(site_path, 'magic', 'libmagic')
            if os.path.exists(magic_bin_path):
                os.environ['PATH'] = magic_bin_path + os.pathsep + os.environ['PATH']
                break
    except ImportError:
        pass

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from .models import WorkItem, Message, Notification, NotificationPreference, ScheduledMessage, MessageReadReceipt, WorkItemType
from .forms import WorkItemForm, MessageForm, ThreadForm, WorkItemTypeForm
from django.db.models import Q
from django.db import IntegrityError
from .models import Thread, FileAttachment, SlowChannel, SlowChannelMessage
from .forms import FileAttachmentForm, NotificationPreferenceForm, ScheduledMessageForm, SlowChannelForm, SlowChannelParticipantsForm, SlowChannelMessageForm
import logging, json, datetime, random

# Now import magic after setting the PATH
try:
    import magic
except ImportError:
    # Fallback if magic import fails
    import mimetypes
    class MagicFallback:
        def from_file(self, filename, mime=True):
            mimetype, _ = mimetypes.guess_type(filename)
            return mimetype or 'application/octet-stream'
            
        def from_buffer(self, buffer, mime=True):
            # Simple check for common file types based on signatures
            if buffer.startswith(b'%PDF'):
                return 'application/pdf'
            elif buffer.startswith(b'PK\x03\x04'):
                return 'application/zip'
            elif buffer.startswith(b'\xff\xd8\xff'):
                return 'image/jpeg'
            elif buffer.startswith(b'\x89PNG\r\n\x1a\n'):
                return 'image/png'
            else:
                return 'application/octet-stream'
    
    # Create a magic replacement object
    magic = MagicFallback()

from django.utils import timezone
from django.contrib.auth.models import User
from datetime import timedelta
from django.contrib.sessions.models import Session
from django.core.paginator import Paginator  # Add this import at the top

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
    
    # More efficient thread access check using a single database query
    accessible_threads = Thread.objects.filter(
        work_item=work_item
    ).filter(
        Q(is_public=True) | 
        Q(created_by=request.user) | 
        Q(allowed_users=request.user)
    ).distinct()
    
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
        'threads': accessible_threads,
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
    
    # Get messages with pagination
    messages_list = thread.thread_messages.filter(Q(parent=None) | Q(is_thread_starter=True)).order_by('created_at')
    
    # Add pagination
    paginator = Paginator(messages_list, 10)  # Show 10 messages per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # For each message, preload its replies
    for message in page_obj:
        message.replies_list = message.replies.all()[:5]  # Show only 5 most recent replies
        message.has_more_replies = message.replies.count() > 5
    
    # Get the list of participants who can view this thread
    participants = thread.get_participants()
    
    context = {
        'work_item': work_item,
        'thread': thread,
        'messages': page_obj,
        'participants': participants,
        'is_public': thread.is_public,
        'page_obj': page_obj,  # Add paginator object to context for page navigation
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
    
    # Check if user has permission to add files to this work item
    if request.user != work_item.owner and request.user not in work_item.collaborators.all():
        messages.error(request, "You don't have permission to add files to this work item.")
        return redirect('work_item_detail', pk=pk)
    
    if request.method == 'POST' and request.FILES.get('file'):
        uploaded_file = request.FILES['file']
        
        # Simple file size validation - limit to 10MB
        if uploaded_file.size > 10 * 1024 * 1024:
            messages.error(request, "File size too large. Maximum size is 10MB.")
            return redirect('work_item_detail', pk=pk)
        
        # Extension-based validation - no need for magic library
        file_name = uploaded_file.name
        file_extension = os.path.splitext(file_name)[1].lower()
        allowed_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.txt', '.png', '.jpg', '.jpeg', '.ppt', '.pptx']
        
        if file_extension not in allowed_extensions:
            messages.error(request, f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}")
            return redirect('work_item_detail', pk=pk)
        
        # Create the file attachment
        try:
            FileAttachment.objects.create(
                work_item=work_item,
                file=uploaded_file,
                name=file_name,
                uploaded_by=request.user
            )
            messages.success(request, f"File '{file_name}' uploaded successfully.")
            
            # Log success
            logger.info(f"File uploaded: {file_name} to work item {pk} by {request.user.username}")
            
        except Exception as e:
            logger.error(f"Error saving file: {str(e)}")
            messages.error(request, "Error saving file. Please try again.")
        
        return redirect('work_item_detail', pk=pk)
    
    # If not a POST request or no file, just redirect back
    return redirect('work_item_detail', pk=pk)

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
def toggle_mute_thread(request, pk):
    """Ajax view to toggle muting a thread"""
    thread = get_object_or_404(Thread, pk=pk)
    
    # Get or create preferences
    preferences, created = NotificationPreference.objects.get_or_create(user=request.user)
    
    if preferences.muted_threads.filter(id=pk).exists():
        preferences.muted_threads.remove(thread)
        is_muted = False
    else:
        preferences.muted_threads.add(thread)
        is_muted = True
    
    # If this is an AJAX request, return a JSON response
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'is_muted': is_muted})
    
    # Otherwise redirect back to thread detail page
    return redirect('thread_detail', work_item_pk=thread.work_item.pk, thread_pk=thread.pk)

@login_required
def schedule_message(request, work_item_pk, thread_pk=None, parent_message_pk=None):
    """View to schedule a message for future sending"""
    work_item = get_object_or_404(WorkItem, pk=work_item_pk)
    thread = None
    parent_message = None
    
    # Check if this is a thread message
    if thread_pk:
        thread = get_object_or_404(Thread, pk=thread_pk, work_item=work_item)
        
        # Check if user has permission to view this thread
        if not thread.user_can_access(request.user):
            messages.error(request, "You don't have permission to access this thread.")
            return redirect('work_item_detail', pk=work_item.pk)
    
    # Check if this is a reply to a specific message
    if parent_message_pk:
        parent_message = get_object_or_404(Message, pk=parent_message_pk)
        
        # Ensure parent message belongs to the right thread
        if thread and parent_message.thread != thread:
            messages.error(request, "Invalid parent message for this thread.")
            return redirect('thread_detail', work_item_pk=work_item.pk, thread_pk=thread.pk)
    
    if request.method == 'POST':
        form = ScheduledMessageForm(
            request.POST, 
            sender=request.user, 
            work_item=work_item,
            thread=thread,
            parent_message=parent_message
        )
        
        if form.is_valid():
            scheduled_message = form.save()
            messages.success(request, f"Message scheduled for {scheduled_message.scheduled_time.strftime('%Y-%m-%d %H:%M')}")
            
            # Redirect based on context
            if thread:
                return redirect('thread_detail', work_item_pk=work_item.pk, thread_pk=thread.pk)
            else:
                return redirect('work_item_detail', pk=work_item.pk)
    else:
        form = ScheduledMessageForm(
            sender=request.user, 
            work_item=work_item,
            thread=thread,
            parent_message=parent_message
        )
    
    # Set appropriate title based on context
    if parent_message:
        title = "Schedule Reply"
    elif thread:
        title = "Schedule Thread Message"
    else:
        title = "Schedule Message"
    
    context = {
        'form': form,
        'work_item': work_item,
        'thread': thread,
        'parent_message': parent_message,
        'title': title
    }
    
    return render(request, 'workspace/schedule_message_form.html', context)

@login_required
def my_scheduled_messages(request):
    """View to list user's scheduled messages"""
    scheduled_messages = ScheduledMessage.objects.filter(
        sender=request.user,
        is_sent=False
    ).order_by('scheduled_time')
    
    context = {
        'scheduled_messages': scheduled_messages,
        'title': 'My Scheduled Messages'
    }
    
    return render(request, 'workspace/my_scheduled_messages.html', context)

@login_required
def cancel_scheduled_message(request, pk):
    """View to cancel a scheduled message"""
    scheduled_message = get_object_or_404(ScheduledMessage, pk=pk, sender=request.user, is_sent=False)
    
    if request.method == 'POST':
        scheduled_message.delete()
        messages.success(request, "Scheduled message canceled.")
        return redirect('my_scheduled_messages')
        
    context = {
        'scheduled_message': scheduled_message
    }
    
    return render(request, 'workspace/scheduled_message_confirm_delete.html', context)

@login_required
def edit_scheduled_message(request, pk):
    """View to edit a scheduled message"""
    scheduled_message = get_object_or_404(ScheduledMessage, pk=pk, sender=request.user, is_sent=False)
    
    if request.method == 'POST':
        form = ScheduledMessageForm(
            request.POST, 
            instance=scheduled_message,
            sender=request.user,
            work_item=scheduled_message.work_item,
            thread=scheduled_message.thread,
            parent_message=scheduled_message.parent_message
        )
        
        if form.is_valid():
            form.save()
            messages.success(request, "Scheduled message updated.")
            return redirect('my_scheduled_messages')
    else:
        form = ScheduledMessageForm(
            instance=scheduled_message,
            sender=request.user,
            work_item=scheduled_message.work_item,
            thread=scheduled_message.thread,
            parent_message=scheduled_message.parent_message
        )
    
    context = {
        'form': form,
        'scheduled_message': scheduled_message,
        'title': 'Edit Scheduled Message'
    }
    
    return render(request, 'workspace/schedule_message_form.html', context)

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
    work_item = message.work_item  # Get the work item from the message
    thread = message.thread
    
    if request.method == 'POST':
        form = ScheduledMessageForm(
            request.POST, 
            instance=message,
            sender=request.user,
            work_item=work_item,
            thread=thread,
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
            work_item=work_item,
            thread=thread,
            parent_message=message.parent_message
        )
    
    context = {
        'form': form,
        'message': message,
        'work_item': work_item,  # Add this to the context
        'thread': thread,  # Add this to the context
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
        # First try to get from notification preferences
        try:
            preferences = request.user.notification_preferences
            show_online_status = preferences.show_online_status
        except AttributeError:
            # Fall back to the workspace online status if it exists
            try:
                status = request.user.workspace_online_status
                show_online_status = status.status != 'offline'
            except AttributeError:
                # Then try the users app online status
                try:
                    status = request.user.online_status
                    show_online_status = status.status != 'offline'
                except AttributeError:
                    # No status models found, default to False
                    show_online_status = False
            
        return JsonResponse({
            'status': 'success',
            'show_online_status': show_online_status
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

@require_POST
@login_required
def update_online_status(request):
    """API endpoint to update user's online status with work-life balance info"""
    try:
        data = json.loads(request.body)
        status = data.get('status', 'offline')
        message = data.get('message', None)
        
        # Valid status values
        valid_statuses = ['active', 'away', 'offline', 'afk', 'break', 'outside-hours']
        
        if status not in valid_statuses:
            return JsonResponse({'status': 'error', 'message': 'Invalid status'}, status=400)
        
        # Check if user has enabled online status
        try:
            preferences = request.user.notification_preferences
            if not preferences.show_online_status and status != 'offline':
                return JsonResponse({'status': 'error', 'message': 'Online status disabled'}, status=400)
        except:
            return JsonResponse({'status': 'error', 'message': 'Preferences not found'}, status=404)
            
        # Store the status in session for persistence
        request.session['online_status'] = status
        request.session['status_message'] = message
        request.session['status_updated_at'] = timezone.now().isoformat()
        
        # In a real implementation, you might store this in a database model
        # or use a caching system like Redis for better persistence
        
        return JsonResponse({
            'status': 'success',
            'online_status': status,
            'message': message
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def get_user_status(request, user_id):
    """API endpoint to get another user's status, including work-life balance info"""
    try:
        # Get the target user
        user = get_object_or_404(User, pk=user_id)
        
        # Check if target user has enabled online status
        try:
            preferences = user.notification_preferences
            if not preferences.show_online_status:
                return JsonResponse({
                    'status': 'hidden', 
                    'message': 'User has disabled online status'
                })
                
            # Check if they're sharing working hours
            share_working_hours = preferences.share_working_hours
        except:
            return JsonResponse({'status': 'unknown', 'message': 'Preferences not found'})
        
        # Get user's session data
        # In a real implementation, you'd likely use a database or caching system instead
        session_model = Session.objects.filter(
            session_key__in=Session.objects.filter(
                expire_date__gt=timezone.now()
            ).values_list('session_key', flat=True)
        ).order_by('-expire_date').first()
        
        user_status = 'offline'
        status_message = None
        working_hours_info = None
        
        if session_model:
            session_data = session_model.get_decoded()
            if str(user.id) in session_data.get('_auth_user_id', ''):
                user_status = session_data.get('online_status', 'offline')
                status_message = session_data.get('status_message')
        
        # If sharing working hours, include that info
        if share_working_hours:
            working_hours_info = {
                'work_days': preferences.work_days,
                'work_start_time': preferences.work_start_time.strftime('%H:%M') if preferences.work_start_time else None,
                'work_end_time': preferences.work_end_time.strftime('%H:%M') if preferences.work_end_time else None,
                'lunch_break_start': preferences.lunch_break_start.strftime('%H:%M') if preferences.lunch_break_start else None,
                'lunch_break_duration': preferences.lunch_break_duration,
            }
            
            # Check if current time is within user's working hours
            is_working_hours = is_within_working_hours(preferences)
            working_hours_info['currently_working_hours'] = is_working_hours
            
            # If user is active but outside working hours, update status
            if user_status == 'active' and not is_working_hours:
                user_status = 'outside-hours'
                status_message = 'Outside working hours'
        
        return JsonResponse({
            'status': 'success',
            'user_id': user_id,
            'username': user.username,
            'online_status': user_status,
            'status_message': status_message,
            'working_hours': working_hours_info
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def is_within_working_hours(preferences):
    """Helper function to check if current time is within working hours"""
    now = timezone.now()
    
    # Convert to local time if needed
    # For simplicity we're using server time
    
    # Check if current day is a work day
    current_day = str(now.weekday() + 1)  # Django weekday is 0-6, we use 1-7
    if current_day not in preferences.work_days:
        return False
    
    # Check if current time is within work hours
    current_time = now.time()
    if not preferences.work_start_time or not preferences.work_end_time:
        return True  # No time restrictions
    
    # Handle lunch break if specified
    if preferences.lunch_break_start and preferences.lunch_break_duration:
        lunch_end_minutes = (
            preferences.lunch_break_start.hour * 60 + 
            preferences.lunch_break_start.minute + 
            preferences.lunch_break_duration
        ) % (24 * 60)
        
        lunch_end_hour = lunch_end_minutes // 60
        lunch_end_minute = lunch_end_minutes % 60
        lunch_end = datetime.time(lunch_end_hour, lunch_end_minute)
        
        # Check if current time is during lunch break
        if preferences.lunch_break_start <= current_time <= lunch_end:
            return False
    
    # Basic work hours check
    return preferences.work_start_time <= current_time <= preferences.work_end_time

@login_required
def log_work_session(request):
    """API endpoint to log work session for analytics"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            session_type = data.get('type', 'work')  # work, break, meeting
            start_time = data.get('start_time')
            end_time = data.get('end_time')
            notes = data.get('notes', '')
            
            # In a real implementation, save this to a database model
            # For demonstration, we'll just return success
            
            return JsonResponse({
                'status': 'success',
                'message': 'Work session logged successfully'
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
    return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)

@login_required
def get_work_analytics(request):
    """API endpoint to get work analytics data with synthetic data generation"""
    try:
        # Parse date parameters
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        # Parse dates or use defaults (last 7 days)
        try:
            if start_date_str:
                start_date = timezone.datetime.strptime(start_date_str, '%Y-%m-%d').date()
            else:
                start_date = (timezone.now() - timezone.timedelta(days=7)).date()
                
            if end_date_str:
                end_date = timezone.datetime.strptime(end_date_str, '%Y-%m-%d').date()
            else:
                end_date = timezone.now().date()
        except ValueError:
            # Handle invalid date format
            start_date = (timezone.now() - timezone.timedelta(days=7)).date()
            end_date = timezone.now().date()
        
        # Calculate the number of days in the range
        date_delta = (end_date - start_date).days + 1
        date_range = [start_date + timezone.timedelta(days=i) for i in range(date_delta)]
        
        # Generate seed value based on user ID for consistent randomness per user
        import random
        seed = request.user.id * 1000 if request.user.id else 1000
        random.seed(seed)
        
        # Generate synthetic work sessions
        work_sessions = []
        for date in date_range:
            # Check if it's a weekday (0=Monday, 6=Sunday)
            weekday = date.weekday()
            is_weekday = weekday < 5  # Monday through Friday
            
            if is_weekday:
                # Higher work minutes on weekdays
                work_minutes = random.randint(320, 480)  # 5.5 to 8 hours
                break_minutes = random.randint(30, 90)   # 0.5 to 1.5 hours for breaks
                meeting_minutes = random.randint(30, 180)  # 0.5 to 3 hours for meetings
            else:
                # Lower or zero work minutes on weekends
                if random.random() < 0.7:  # 70% chance of no work on weekend
                    work_minutes = 0
                    break_minutes = 0
                    meeting_minutes = 0
                else:
                    work_minutes = random.randint(60, 240)  # 1 to 4 hours if working
                    break_minutes = random.randint(15, 60)  # 15 min to 1 hour for breaks
                    meeting_minutes = random.randint(0, 60)   # 0 to 1 hour for meetings
            
            # Introduce some variation based on date to make the chart less uniform
            variation = (hash(date.isoformat()) % 20) - 10  # -10 to 10 percent
            work_minutes = int(work_minutes * (1 + variation/100))
            
            work_sessions.append({
                'date': date.isoformat(),
                'work_minutes': work_minutes,
                'break_minutes': break_minutes,
                'meeting_minutes': meeting_minutes,
                'is_weekday': is_weekday
            })
        
        # Calculate average work day (only counting days with work)
        work_days = [s for s in work_days if s['work_minutes'] > 0]
        avg_work_minutes = sum(s['work_minutes'] for s in work_days) / max(len(work_days), 1)
        average_work_day = round(avg_work_minutes / 60, 1)  # Convert to hours
        
        # Calculate break compliance
        # Formula: Actual break time / Expected break time (15min per 2 hours)
        expected_break_minutes = sum(max(s['work_minutes'] // 120 * 15, 0) for s in work_sessions)
        actual_break_minutes = sum(s['break_minutes'] for s in work_sessions)
        break_compliance = round((actual_break_minutes / expected_break_minutes * 100) if expected_break_minutes > 0 else 100)
        break_compliance = min(100, max(0, break_compliance))  # Clamp between 0-100
        
        # Calculate communication metrics
        # After-hours communication: Messages sent outside work hours (synthetic)
        messages_after_hours = random.randint(5, 20)
        
        # Determine communication load based on number of messages and meetings
        meeting_hours = sum(s['meeting_minutes'] for s in work_sessions) / 60
        message_count = random.randint(20, 100)  # Synthetic message count
        
        if meeting_hours > 15 or message_count > 80:
            communication_load = 'high'
        elif meeting_hours > 8 or message_count > 50:
            communication_load = 'moderate'
        else:
            communication_load = 'low'
        
        # Generate hourly communication pattern
        # More messages during 9-11am and 1-3pm, fewer during lunch and after hours
        hourly_pattern = []
        for hour in range(24):
            if 9 <= hour < 12:
                # Morning peak
                count = random.randint(15, 25)
            elif 12 <= hour < 13:
                # Lunch dip
                count = random.randint(5, 10)
            elif 13 <= hour < 17:
                # Afternoon
                count = random.randint(10, 20)
            elif 17 <= hour < 19:
                # After work but still some activity
                count = random.randint(3, 8)
            else:
                # Night/early morning
                count = random.randint(0, 3)
            hourly_pattern.append(count)
        
        # Generate response time distribution
        # Format: [% in <5min, % in 5-15min, % in 15-30min, % in 30-60min, % in 1-2hrs, % in 2+hrs]
        response_distribution = [15, 25, 30, 20, 8, 2]  # Percentages adding up to 100
        
        # Peak hour identification
        peak_hour_start = 9 + hourly_pattern[9:17].index(max(hourly_pattern[9:17]))
        peak_hour_end = peak_hour_start + 1
        
        # Format for display
        peak_hour_start_str = f"{peak_hour_start}:00"
        peak_hour_end_str = f"{peak_hour_end}:00"
        
        # Build work percentages
        total_minutes = sum(s['work_minutes'] + s['break_minutes'] + s['meeting_minutes'] for s in work_sessions)
        if total_minutes > 0:
            work_percent = round(sum(s['work_minutes'] for s in work_sessions) / total_minutes * 100)
            break_percent = round(sum(s['break_minutes'] for s in work_sessions) / total_minutes * 100)
            meeting_percent = round(sum(s['meeting_minutes'] for s in work_sessions) / total_minutes * 100)
        else:
            work_percent = 75
            break_percent = 15
            meeting_percent = 10
        
        # Prepare insights based on the data
        insights = []
        
        # Work-life balance insight
        weekday_sessions = [s for s in work_sessions if s['is_weekday']]
        weekend_sessions = [s for s in work_sessions if not s['is_weekday']]
        weekend_work_minutes = sum(s['work_minutes'] for s in weekend_sessions)
        
        if weekend_work_minutes > 0:
            insights.append({
                'type': 'weekend_work',
                'message': f"You worked {weekend_work_minutes//60} hours on weekends in this period. Consider setting stricter work-life boundaries.",
                'sentiment': 'warning'
            })
        
        # Break compliance insight
        if break_compliance < 70:
            insights.append({
                'type': 'break_compliance',
                'message': "You're taking fewer breaks than recommended. Regular breaks can help maintain productivity and reduce fatigue.",
                'sentiment': 'warning'
            })
        elif break_compliance > 90:
            insights.append({
                'type': 'break_compliance',
                'message': "You're doing a great job taking regular breaks! This helps maintain productivity and wellbeing.",
                'sentiment': 'positive'
            })
        
        # After-hours communication insight
        if messages_after_hours > 10:
            insights.append({
                'type': 'after_hours',
                'message': f"You sent {messages_after_hours} messages outside working hours. Consider using scheduled messages instead.",
                'sentiment': 'warning'
            })
        elif messages_after_hours < 5:
            insights.append({
                'type': 'after_hours',
                'message': "You're doing well at maintaining boundaries by limiting after-hours communication.",
                'sentiment': 'positive'
            })
        
        # Package all data for the response
        data = {
            'work_sessions': work_sessions,
            'average_work_day': average_work_day,
            'break_compliance': break_compliance,
            'messages_after_hours': messages_after_hours,
            'communication_load': communication_load,
            'hourly_pattern': hourly_pattern,
            'response_distribution': response_distribution,
            'peak_communication_time': f"{peak_hour_start_str} - {peak_hour_end_str}",
            'work_percent': work_percent,
            'break_percent': break_percent,
            'meeting_percent': meeting_percent,
            'insights': insights,
            'is_synthetic': True  # Flag to indicate this is synthetic data
        }
        
        return JsonResponse({
            'status': 'success',
            'data': data
        })
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def work_life_analytics(request):
    """View for the Work-Life Analytics Dashboard"""
    # Set default date range (last 7 days)
    end_date = timezone.now().date()
    start_date = end_date - datetime.timedelta(days=7)
    
    context = {
        'default_start_date': start_date,
        'default_end_date': end_date,
    }
    
    return render(request, 'workspace/work_life_analytics.html', context)

@login_required
def record_break_taken(request):
    """API endpoint to record when a user takes a break"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            break_duration = data.get('duration', 5)  # Default 5 minutes
            
            # Record the break in a new model
            # This could be used for analytics later
            
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)

@login_required
def manually_run_scheduled_messages(request):
    """View to manually trigger the scheduled messages task"""
    if not request.user.is_superuser:
        messages.error(request, "This action is only available to superusers.")
        return redirect('dashboard')
    
    try:
        now = timezone.now()
        due_messages = ScheduledMessage.objects.filter(
            is_sent=False, 
            scheduled_time__lte=now
        )
        
        sent_count = 0
        errors = []
        
        for message in due_messages:
            try:
                if message.send():
                    sent_count += 1
                else:
                    errors.append(f"Failed to send message #{message.id}")
            except Exception as e:
                errors.append(f"Error with message #{message.id}: {str(e)}")
        
        if sent_count > 0:
            messages.success(request, f"Successfully sent {sent_count} scheduled messages.")
        else:
            messages.warning(request, "No messages were sent.")
            
        if errors:
            for error in errors[:5]:  # Show first 5 errors
                messages.error(request, error)
    except Exception as e:
        messages.error(request, f"Error sending scheduled messages: {str(e)}")
    
    return redirect('my_scheduled_messages')

@login_required
def remove_collaborator(request, pk, user_id):
    """View to remove a collaborator from a work item"""
    work_item = get_object_or_404(WorkItem, pk=pk)
    
    # Only the owner can remove collaborators
    if work_item.owner != request.user:
        messages.error(request, "Only the work item owner can remove collaborators.")
        return redirect('work_item_detail', pk=work_item.pk)
    
    # Get the collaborator to remove
    collaborator = get_object_or_404(User, pk=user_id)
    
    # Check if user is actually a collaborator
    if collaborator in work_item.collaborators.all():
        # Remove the collaborator
        work_item.collaborators.remove(collaborator)
        messages.success(request, f"{collaborator.username} has been removed as a collaborator.")
    else:
        messages.error(request, f"{collaborator.username} is not a collaborator on this work item.")
    
    return redirect('work_item_detail', pk=work_item.pk)

@login_required
def work_item_types_list(request):
    """View to list and manage work item types"""
    # Get all work item types created by this user
    types = WorkItemType.objects.filter(created_by=request.user)
    
    context = {
        'types': types,
        'title': 'Manage Work Item Types'
    }
    return render(request, 'workspace/work_item_types_list.html', context)

@login_required
def create_work_item_type(request):
    """View to create a new work item type"""
    if request.method == 'POST':
        form = WorkItemTypeForm(request.POST, user=request.user)
        if form.is_valid():
            work_item_type = form.save(commit=False)
            work_item_type.created_by = request.user
            work_item_type.save()
            messages.success(request, f'Work item type "{work_item_type.name}" has been created!')
            return redirect('work_item_types_list')
    else:
        form = WorkItemTypeForm(user=request.user)
    
    context = {
        'form': form,
        'title': 'Create Work Item Type'
    }
    return render(request, 'workspace/work_item_type_form.html', context)

@login_required
def update_work_item_type(request, pk):
    """View to update an existing work item type"""
    work_item_type = get_object_or_404(WorkItemType, pk=pk, created_by=request.user)
    
    if request.method == 'POST':
        form = WorkItemTypeForm(request.POST, instance=work_item_type, user=request.user)
        if form.is_valid():
            work_item_type = form.save()
            messages.success(request, f'Work item type "{work_item_type.name}" has been updated!')
            return redirect('work_item_types_list')
    else:
        form = WorkItemTypeForm(instance=work_item_type, user=request.user)
    
    context = {
        'form': form,
        'work_item_type': work_item_type,
        'title': 'Update Work Item Type'
    }
    return render(request, 'workspace/work_item_type_form.html', context)

@login_required
def delete_work_item_type(request, pk):
    """View to delete a work item type"""
    work_item_type = get_object_or_404(WorkItemType, pk=pk, created_by=request.user)
    
    # Check if this type is being used by any work items
    work_items_using_type = work_item_type.work_items.count()
    
    if request.method == 'POST':
        if work_items_using_type > 0 and not request.POST.get('confirm_deletion'):
            messages.error(request, 
                f'Cannot delete "{work_item_type.name}" because it is used by {work_items_using_type} work items. '
                f'Please confirm deletion to reassign these work items to a default type.')
            return redirect('delete_work_item_type', pk=work_item_type.pk)
        
        # If deletion is confirmed and work items are using this type, reassign them
        if work_items_using_type > 0:
            # Find or create a default type to reassign work items to
            default_type, created = WorkItemType.objects.get_or_create(
                name='Task',
                created_by=request.user,
                defaults={'color': 'info', 'icon': 'fa-tasks'}
            )
            
            # Reassign work items to the default type
            work_item_type.work_items.update(item_type=default_type)
            
            messages.info(request, 
                f'Reassigned {work_items_using_type} work items from "{work_item_type.name}" to "{default_type.name}"')
        
        # Now delete the type
        type_name = work_item_type.name
        work_item_type.delete()
        messages.success(request, f'Work item type "{type_name}" has been deleted!')
        return redirect('work_item_types_list')
    
    context = {
        'work_item_type': work_item_type,
        'work_items_using_type': work_items_using_type,
        'title': 'Delete Work Item Type'
    }
    return render(request, 'workspace/work_item_type_confirm_delete.html', context)

@require_GET
@login_required
def get_notifications_ajax(request):
    """API endpoint to get the latest notifications for the current user via AJAX"""
    try:
        # Get the 5 most recent notifications
        recent_notifications = request.user.notifications.all()[:5]
        
        # Format the notifications for JSON response
        notifications_data = []
        for notification in recent_notifications:
            notifications_data.append({
                'id': notification.id,
                'message': notification.message,
                'is_read': notification.is_read,
                'work_item_id': notification.work_item.pk if notification.work_item else None,
                'thread_id': notification.thread.pk if notification.thread else None,
                'notification_type': notification.notification_type,
                'time_since': timesince(notification.created_at)
            })
        
        # Mark these notifications as read
        recent_notifications.filter(is_read=False).update(is_read=True)
        
        # Count remaining unread notifications
        unread_count = request.user.notifications.filter(is_read=False).count()
        
        return JsonResponse({
            'success': True,
            'notifications': notifications_data,
            'unread_count': unread_count
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
