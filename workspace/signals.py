from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Message, WorkItem, Notification, FileAttachment
from django.contrib.auth.models import User
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import json

# Get the channel layer for WebSocket communication
channel_layer = get_channel_layer()

# Helper function to send real-time notifications through WebSockets
def send_notification(notification):
    notification_data = {
        'id': notification.id,
        'message': notification.message,
        'work_item_id': notification.work_item.id if notification.work_item else None,
        'created_at': notification.created_at.isoformat(),
        'notification_type': notification.notification_type
    }
    
    async_to_sync(channel_layer.group_send)(
        f'notifications_{notification.user.id}',
        {
            'type': 'notification_message',
            'notification': notification_data
        }
    )

# When a new message is created
@receiver(post_save, sender=Message)
def create_message_notification(sender, instance, created, **kwargs):
    if created:
        # Get all users associated with this work item except the message sender
        users = User.objects.filter(work_item=instance.work_item).exclude(id=instance.user.id).distinct()
        
        collaborators = instance.work_item.collaborators.exclude(id=instance.user.id)
        users = (users | collaborators).distinct()

        for user in users:
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

# When a new file is uploaded - using your FileAttachment model
@receiver(post_save, sender=FileAttachment)
def create_file_upload_notification(sender, instance, created, **kwargs):
    if created:
        # Get all users associated with this work item except the uploader
        users = User.objects.filter(work_item=instance.work_item).exclude(id=instance.uploaded_by.id).distinct()
        
        for user in users:
            notification = Notification.objects.create(
                user=user,
                message=f"{instance.uploaded_by.username} uploaded '{instance.name}' to '{instance.work_item.title}'",
                work_item=instance.work_item,
                notification_type='file_upload'
            )
            send_notification(notification)