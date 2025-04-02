from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Message, WorkItem, Notification, FileAttachment, NotificationPreference
from django.contrib.auth.models import User
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import json
import logging

logger = logging.getLogger(__name__)

# Get the channel layer for WebSocket communication
channel_layer = get_channel_layer()

def send_notification(notification):
    """
    Central function to handle notification sending logic.
    Checks user preferences and sends notifications accordingly.
    """
    user = notification.user
    work_item = notification.work_item
    
    # Handle notification based on priority
    if notification.priority == 'urgent':
        # Urgent notifications bypass DND and work hour settings
        logger.info(f"Sending urgent notification to {user.username}")
        # Send immediately regardless of preferences
        _deliver_notification(notification)
        return
    
    # Check if user should receive notification based on preferences
    try:
        preferences = user.notification_preferences
        
        # Check focus mode - only allow notifications from selected users and work items
        if preferences.focus_mode:
            # Get the user who caused this notification
            notification_sender = notification.get_sender() if hasattr(notification, 'get_sender') else None
            
            # Only allow notifications from selected users and work items
            if (notification_sender and notification_sender not in preferences.focus_users.all() and
                (not work_item or work_item not in preferences.focus_work_items.all())):
                # Save but mark as filtered by focus mode
                notification.is_focus_filtered = True
                notification.save()
                return
        
        # For normal priority, respect DND and working hours
        if notification.priority == 'normal':
            # Skip if the user has DND enabled or if this is outside work hours
            if not preferences.should_notify():
                # Mark the notification as delayed
                notification.is_delayed = True
                notification.save()
                return
        
        # For low priority, we could implement batching or additional delay
        elif notification.priority == 'low':
            # Skip if outside work hours or delay for batch processing
            if not preferences.should_notify():
                notification.is_delayed = True
                notification.save()
                return
            
            # Could implement batching logic here for low priority
            # For now, just mark with a flag that could be used by a batching system
            notification.is_batched = True
            
        # Skip if the user has muted this work item
        if work_item and preferences.muted_channels.filter(id=work_item.id).exists():
            # Save but mark as from muted channel
            notification.is_from_muted = True
            notification.save()
            return
            
        # Check notification mode
        if preferences.notification_mode == 'none':
            notification.save()
            return
            
        if preferences.notification_mode == 'mentions' and not is_user_mentioned(notification.message, user):
            notification.save()
            return
            
    except (AttributeError, NotificationPreference.DoesNotExist):
        pass  # If no preferences exist, continue with notification
    
    # Deliver the notification
    _deliver_notification(notification)

def _deliver_notification(notification):
    """Helper function to deliver a notification via WebSocket"""
    try:
        notification_data = {
            'id': notification.id,
            'message': notification.message,
            'work_item_id': notification.work_item.id if notification.work_item else None,
            'created_at': notification.created_at.isoformat(),
            'notification_type': notification.notification_type,
            'priority': notification.priority
        }
        
        async_to_sync(channel_layer.group_send)(
            f'notifications_{notification.user.id}',
            {
                'type': 'notification_message',
                'message': notification.message,
                'count': Notification.objects.filter(user=notification.user, is_read=False).count(),
                'priority': notification.priority
            }
        )
        
        # Save notification as sent
        notification.is_sent = True
        notification.save()
    except Exception as e:
        # Log the error and still save the notification
        logger.error(f"Error sending notification: {str(e)}")
        notification.save()

def is_user_mentioned(message, user):
    """Check if a user is mentioned in a message using @ notation"""
    return f"@{user.username}" in message

@receiver(post_save, sender=Message)
def create_message_notification(sender, instance, created, **kwargs):
    if created:
        # Skip notifications for threaded messages - these are handled by the ThreadConsumer
        if instance.thread is not None:
            return
            
        # Get the owner if not the message sender
        recipients = set()
        if instance.work_item.owner.id != instance.user.id:
            recipients.add(instance.work_item.owner)
        
        # Add all collaborators except the message sender
        collaborators = instance.work_item.collaborators.exclude(id=instance.user.id)
        recipients.update(collaborators)

        for user in recipients:
            notification = Notification.objects.create(
                user=user,
                message=f"New message from {instance.user.username} in '{instance.work_item.title}'",
                work_item=instance.work_item,
                notification_type='message'
            )
            send_notification(notification)

# When a work item is updated
@receiver(post_save, sender=WorkItem)
def create_workitem_update_notification(sender, instance, created, **kwargs):
    # Skip notifications on creation or if there's no updated_by user
    if not created and hasattr(instance, 'updated_by') and instance.updated_by:
        # Get all users associated with this work item except the one who made the update
        users = User.objects.filter(work_item=instance).exclude(id=instance.updated_by.id).distinct()
        
        for user in users:
            notification = Notification.objects.create(
                user=user,
                message=f"'{instance.title}' was updated by {instance.updated_by.username}",
                work_item=instance,
                notification_type='update'
            )
            send_notification(notification)

@receiver(post_save, sender=FileAttachment)
def create_file_upload_notification(sender, instance, created, **kwargs):
    if created:
        # Get the owner if not the uploader
        recipients = set()
        if instance.work_item.owner.id != instance.uploaded_by.id:
            recipients.add(instance.work_item.owner)
        
        # Add all collaborators except the uploader
        collaborators = instance.work_item.collaborators.exclude(id=instance.uploaded_by.id)
        recipients.update(collaborators)

        for user in recipients:
            notification = Notification.objects.create(
                user=user,
                message=f"{instance.uploaded_by.username} uploaded '{instance.name}' to '{instance.work_item.title}'",
                work_item=instance.work_item,
                notification_type='file_upload'
            )
            send_notification(notification)

@receiver(post_save, sender=User)
def create_notification_preferences(sender, instance, created, **kwargs):
    """Create default notification preferences for new users"""
    if created:
        NotificationPreference.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_notification_preferences(sender, instance, **kwargs):
    """Save notification preferences when user is saved"""
    try:
        instance.notification_preferences.save()
    except NotificationPreference.DoesNotExist:
        NotificationPreference.objects.create(user=instance)