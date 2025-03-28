import json
import logging
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
        

logger = logging.getLogger(__name__)

class ThreadConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.thread_id = self.scope['url_route']['kwargs']['thread_id']
        self.user = self.scope["user"]
        
        # Check if the user has access to this thread
        has_access = await self.check_thread_access()
        if not has_access:
            await self.close(code=4003)  # Access denied
            logger.warning(f"User {self.user.username} denied access to thread {self.thread_id}")
            return
            
        self.room_group_name = f'thread_{self.thread_id}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
        logger.info(f"User {self.user.username} connected to thread {self.thread_id}")

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        logger.info(f"User {self.user.username} disconnected from thread {self.thread_id}, code: {close_code}")

    # Receive message from WebSocket
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message = data['message']
            user_id = data['user_id']
            parent_id = data.get('parent_id')  # For threaded replies
            
            logger.info(f"Received message from user {user_id} in thread {self.thread_id}")
            
            # Verify the user still has access to the thread
            has_access = await self.check_thread_access()
            if not has_access:
                # Don't process messages if user doesn't have access
                logger.warning(f"User {user_id} denied message send access to thread {self.thread_id}")
                return
            
            # Save the message to the database
            message_obj = await self.save_message(user_id, message, parent_id)
            logger.info(f"Saved message ID {message_obj.id} to database")
            
            # Format timestamp for display
            timestamp = message_obj.created_at.strftime("%Y-%m-%d %H:%M:%S")
            
            # Get username
            username = await self.get_username(user_id)
            
            # Get reply count if this is a new parent message
            reply_count = 0
            if not parent_id:
                reply_count = await self.get_reply_count(message_obj.id)
            
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
                    'parent_id': parent_id,
                    'is_thread_starter': message_obj.is_thread_starter,
                    'reply_count': reply_count
                }
            )
            logger.info(f"Sent message to group {self.room_group_name}")
            
            # Create notifications for thread members
            await self.create_thread_notifications(message_obj, user_id)
            
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)
            # Send error notification to the sender but don't disconnect
            try:
                await self.send(text_data=json.dumps({
                    'error': str(e),
                    'message': "An error occurred sending your message. Please try again."
                }))
            except:
                # If we can't even send the error message, just log it
                logger.error("Could not send error notification to client")

    # Receive message from room group
    async def chat_message(self, event):
        try:
            # Send message to WebSocket
            await self.send(text_data=json.dumps({
                'message': event.get('message', ''),
                'user_id': event.get('user_id', ''),
                'username': event.get('username', ''),
                'timestamp': event.get('timestamp', ''),
                'message_id': event.get('message_id', ''),
                'parent_id': event.get('parent_id', None),
                'is_thread_starter': event.get('is_thread_starter', False),
                'reply_count': event.get('reply_count', 0)
            }))
        except Exception as e:
            logger.error(f"Error sending message to client: {str(e)}", exc_info=True)
    
    @database_sync_to_async
    def save_message(self, user_id, message, parent_id=None):
        user = User.objects.get(pk=user_id)
        thread = Thread.objects.get(pk=self.thread_id)
        work_item = thread.work_item  # Get the work_item from the thread
        
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
        
        # Create and return the message
        msg = Message.objects.create(
            thread=thread,
            work_item=work_item,  # This was missing before
            user=user,
            content=message,
            parent=parent,
            is_thread_starter=is_thread_starter
        )
        
        return msg
    
    @database_sync_to_async    
    def get_reply_count(self, message_id):
        """Get the reply count for a message"""
        try:
            message = Message.objects.get(pk=message_id)
            return message.replies.count()
        except Message.DoesNotExist:
            return 0
        
    @database_sync_to_async
    def get_username(self, user_id):
        user = User.objects.get(pk=user_id)
        return user.username
    
    @database_sync_to_async
    def check_thread_access(self):
        """Check if the current user has access to this thread"""
        try:
            thread = Thread.objects.get(pk=self.thread_id)
            return thread.user_can_access(self.scope["user"])
        except Thread.DoesNotExist:
            return False
    
    @database_sync_to_async
    def create_thread_notifications(self, message_obj, sender_id):
        """Create notifications for thread participants except the sender"""
        thread = message_obj.thread
        work_item = thread.work_item
        sender = User.objects.get(pk=sender_id)
        
        # Get all users who should be notified (thread participants)
        recipients = set()
        
        if thread.is_public:
            # For public threads, notify all work item collaborators and owner
            if work_item.owner.id != int(sender_id):
                recipients.add(work_item.owner)
            
            for collaborator in work_item.collaborators.all():
                if collaborator.id != int(sender_id):
                    recipients.add(collaborator)
        else:
            # For private threads, ONLY notify explicitly allowed users
            for user in thread.allowed_users.all():
                if user.id != int(sender_id):
                    recipients.add(user)
            
            # Always include thread creator
            if thread.created_by.id != int(sender_id):
                recipients.add(thread.created_by)
                
            # Include work item owner only if they are explicitly allowed
            if work_item.owner.id != int(sender_id) and (
                work_item.owner in thread.allowed_users.all() or 
                work_item.owner == thread.created_by
            ):
                recipients.add(work_item.owner)
        
        # Create notifications for each recipient
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