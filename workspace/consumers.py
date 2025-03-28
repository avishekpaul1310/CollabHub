import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from .models import WorkItem, Message, Notification, NotificationPreference, Thread
from django.utils import timezone
import datetime

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.work_item_id = self.scope['url_route']['kwargs']['work_item_id']
        self.room_group_name = f'chat_{self.work_item_id}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data['message']
        user_id = data['user_id']

        # Save the message to the database
        message_obj = await self.save_message(user_id, message)

        # Create notifications for all collaborators except the sender
        # await self.create_notifications(message_obj, user_id)
        
        # Format timestamp for display
        timestamp = message_obj.created_at.strftime("%Y-%m-%d %H:%M:%S")
        
        # Get username
        username = await self.get_username(user_id)
        
        # Send message to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'user_id': user_id,
                'username': username,
                'timestamp': timestamp
            }
        )

    # Receive message from room group
    async def chat_message(self, event):
        message = event['message']
        user_id = event['user_id']
        username = event['username']
        timestamp = event['timestamp']
        
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'message': message,
            'user_id': user_id,
            'username': username,
            'timestamp': timestamp
        }))
    
    @database_sync_to_async
    def save_message(self, user_id, message):
        user = User.objects.get(pk=user_id)
        work_item = WorkItem.objects.get(pk=self.work_item_id)
        return Message.objects.create(
            work_item=work_item,
            user=user,
            content=message
        )
        
    @database_sync_to_async
    def get_username(self, user_id):
        user = User.objects.get(pk=user_id)
        return user.username
        
    """@database_sync_to_async
    def create_notifications(self, message_obj, sender_id):
        sender = User.objects.get(pk=sender_id)
        work_item = message_obj.work_item
        
        # Create notifications for owner and all collaborators except the message sender
        recipients = set([work_item.owner] + list(work_item.collaborators.all()))
        
        for recipient in recipients:
            # Don't notify the sender
            if recipient.id != int(sender_id):
                Notification.objects.create(
                    user=recipient,
                    message=f"{sender.username} sent a message in '{work_item.title}'",
                    work_item=work_item,
                    notification_type='message'
                )"""

class FileConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.work_item_id = self.scope['url_route']['kwargs']['work_item_id']
        self.room_group_name = f'file_{self.work_item_id}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Basic implementation for file notifications
    # You'll expand this for file sharing functionality
    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message = text_data_json.get('message', '')
            user_id = text_data_json.get('user_id', '')
            file_name = text_data_json.get('file_name', '')

            # Send file notification to room group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'file_message',
                    'message': message,
                    'user_id': user_id,
                    'username': await self.get_username(user_id),
                    'file_name': file_name,
                }
            )
        except Exception as e:
            print(f"Error in file receive: {str(e)}")

    async def file_message(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'message': event['message'],
            'user_id': event['user_id'],
            'username': event['username'],
            'file_name': event['file_name'],
        }))
    
    @database_sync_to_async
    def get_username(self, user_id):
        try:
            return User.objects.get(id=user_id).username
        except:
            return "Unknown User"
        
# Add this to your existing consumers.py

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        
        # Create a personal notification group for this user
        self.notification_group_name = f'notifications_{self.user.id}'
        
        # Join notification group
        await self.channel_layer.group_add(
            self.notification_group_name,
            self.channel_name
        )
        
        await self.accept()
    
    async def disconnect(self, close_code):
        # Leave notification group
        await self.channel_layer.group_discard(
            self.notification_group_name,
            self.channel_name
        )
    
    # Custom method to send notification to client
    async def notification_message(self, event):
        # Check if user should receive this notification based on preferences
        user = self.scope["user"]
        
        try:
            # Use database_sync_to_async since we're in an async context
            should_notify = await self.check_notification_preferences(user)
            if not should_notify:
                return  # Skip sending if user shouldn't be notified
        except Exception:
            pass  # If there's an error checking preferences, continue with notification
        
        # Send notification to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'message': event['message'],
            'count': event['count']
        }))
    
    @database_sync_to_async
    def check_notification_preferences(self, user):
        try:
            preferences = user.notification_preferences
            return preferences.should_notify()
        except (AttributeError, NotificationPreference.DoesNotExist):
            return True  # Default to showing notifications
        
class ThreadConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.thread_id = self.scope['url_route']['kwargs']['thread_id']
        self.room_group_name = f'thread_{self.thread_id}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data['message']
        user_id = data['user_id']
        parent_id = data.get('parent_id')  # For threaded replies
        
        # Save the message to the database
        message_obj = await self.save_message(user_id, message, parent_id)
        
        # Format timestamp for display
        timestamp = message_obj.created_at.strftime("%Y-%m-%d %H:%M:%S")
        
        # Get username
        username = await self.get_username(user_id)
        
        # Send message to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'user_id': user_id,
                'username': username,
                'timestamp': timestamp,
                'message_id': message_obj.id,
                'parent_id': message_obj.parent_id,
                'is_thread_starter': message_obj.is_thread_starter,
                'reply_count': message_obj.reply_count
            }
        )
        
        # Create notifications for thread members
        await self.create_thread_notifications(message_obj, user_id)

    # Receive message from room group
    async def chat_message(self, event):
        message = event['message']
        user_id = event['user_id']
        username = event['username']
        timestamp = event['timestamp']
        message_id = event.get('message_id')
        parent_id = event.get('parent_id')
        is_thread_starter = event.get('is_thread_starter', False)
        reply_count = event.get('reply_count', 0)
        
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'message': message,
            'user_id': user_id,
            'username': username,
            'timestamp': timestamp,
            'message_id': message_id,
            'parent_id': parent_id,
            'is_thread_starter': is_thread_starter,
            'reply_count': reply_count
        }))
    
    @database_sync_to_async
    def save_message(self, user_id, message, parent_id=None):
        user = User.objects.get(pk=user_id)
        thread = Thread.objects.get(pk=self.thread_id)
        
        # Set up parent message if this is a reply
        parent = None
        is_thread_starter = False
        
        if parent_id:
            try:
                parent = Message.objects.get(pk=parent_id)
                # If parent already has a parent, use the original parent
                if parent.parent:
                    parent = parent.parent
            except Message.DoesNotExist:
                pass
        else:
            # Mark as thread starter if it's a top-level message
            is_thread_starter = True
        
        return Message.objects.create(
            thread=thread,
            user=user,
            content=message,
            parent=parent,
            is_thread_starter=is_thread_starter
        )
        
    @database_sync_to_async
    def get_username(self, user_id):
        user = User.objects.get(pk=user_id)
        return user.username
    
    @database_sync_to_async
    def create_thread_notifications(self, message_obj, sender_id):
        """Create notifications for thread participants except the sender"""
        thread = message_obj.thread
        work_item = thread.work_item
        sender = User.objects.get(pk=sender_id)
        
        # Get all users who should be notified (thread participants)
        recipients = set()
        
        # Add work item owner
        if work_item.owner.id != int(sender_id):
            recipients.add(work_item.owner)
        
        # Add work item collaborators
        for collaborator in work_item.collaborators.all():
            if collaborator.id != int(sender_id):
                recipients.add(collaborator)
        
        # Add thread allowed users (for private threads)
        for user in thread.allowed_users.all():
            if user.id != int(sender_id):
                recipients.add(user)
        
        # Create notifications
        for recipient in recipients:
            # Check if user has notification preferences
            try:
                preferences = recipient.notification_preferences
                if not preferences.should_notify():
                    continue
            except (AttributeError, NotificationPreference.DoesNotExist):
                pass  # Continue with notification if no preferences exist
                
            Notification.objects.create(
                user=recipient,
                message=f"{sender.username} posted in '{thread.title}' (in '{work_item.title}')",
                work_item=work_item,
                notification_type='message'
            )