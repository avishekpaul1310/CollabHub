from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from .models import WorkItem, Message, Notification, NotificationPreference
from .forms import WorkItemForm, MessageForm
from django.db.models import Q
from .models import FileAttachment
from .forms import FileAttachmentForm, NotificationPreferenceForm

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
    messages = work_item.messages.all()  # Don't filter by file field
    
    # If you have a separate file model:
    files = work_item.files.all() if hasattr(work_item, 'files') else []
    
    context = {
        'work_item': work_item,
        'messages': messages,
        'files': files
    }
    return render(request, 'workspace/work_item_detail.html', context)


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