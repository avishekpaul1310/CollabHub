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
        print(f"WebSocket connected: {self.room_group_name}")

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        print(f"WebSocket disconnected: {self.room_group_name}, code: {close_code}")

    # Receive message from WebSocket
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message = data['message']
            user_id = data['user_id']
            
            print(f"Message received: {message[:20]}... from user {user_id}")

            # Save the message to the database
            message_obj = await self.save_message(user_id, message)

            # Create notifications for all collaborators except the sender
            await self.create_notifications(message_obj, user_id)
            
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
            print(f"Message sent to group: {self.room_group_name}")
            
        except Exception as e:
            print(f"Error in receive method: {str(e)}")
            # Optionally send error message back to client
            await self.send(text_data=json.dumps({
                'error': str(e)
            }))

    # Receive message from room group
    async def chat_message(self, event):
        try:
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
            print(f"Message delivered to client: {message[:20]}...")
            
        except Exception as e:
            print(f"Error in chat_message method: {str(e)}")
    
    @database_sync_to_async
    def save_message(self, user_id, message):
        try:
            user = User.objects.get(pk=user_id)
            work_item = WorkItem.objects.get(pk=self.work_item_id)
            return Message.objects.create(
                work_item=work_item,
                user=user,
                content=message
            )
        except Exception as e:
            print(f"Error saving message: {str(e)}")
            raise
        
    @database_sync_to_async
    def get_username(self, user_id):
        try:
            user = User.objects.get(pk=user_id)
            return user.username
        except User.DoesNotExist:
            return "Unknown User"
        
    @database_sync_to_async
    def create_notifications(self, message_obj, sender_id):
        try:
            sender = User.objects.get(pk=sender_id)
            work_item = message_obj.work_item
            
            # Create notifications for owner and all collaborators except the message sender
            recipients = set()
            if work_item.owner.id != int(sender_id):
                recipients.add(work_item.owner)
            
            collaborators = work_item.collaborators.exclude(id=sender_id)
            recipients.update(collaborators)

            print(f"Creating notifications for {len(recipients)} recipients")
            
            for recipient in recipients:
                Notification.objects.create(
                    user=recipient,
                    message=f"{sender.username} sent a message in '{work_item.title}'",
                    work_item=work_item,
                    notification_type='message'
                )
                print(f"Notification created for {recipient.username}")
        except Exception as e:
            print(f"Error creating notifications: {str(e)}")

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
        
    async def receive(self, text_data):
        """Handle incoming messages from the notification WebSocket"""
        try:
            data = json.loads(text_data)
            # Handle heartbeat messages
            if data.get('type') == 'heartbeat':
                await self.send(text_data=json.dumps({
                    'type': 'heartbeat_response'
                }))
        except Exception as e:
            print(f"Error in notification receive: {str(e)}")

logger = logging.getLogger(__name__)

class ThreadConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.thread_id = self.scope['url_route']['kwargs']['thread_id']
        self.work_item_id = self.scope['url_route']['kwargs']['work_item_id']
        self.room_group_name = f'thread_{self.thread_id}'

        # Join thread group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave thread group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    async def receive(self, text_data):
        data = json.loads(text_data)
        
        # Handle heartbeat messages separately
        if data.get('type') == 'heartbeat':
            # Respond to heartbeat
            await self.send(text_data=json.dumps({
                'type': 'heartbeat_response'
            }))
            return
        
        # Check if message key exists before accessing it
        if 'message' not in data:
            # Log the invalid data format
            print(f"Received invalid data format: {data}")
            # Optionally send an error message back to client
            await self.send(text_data=json.dumps({
                'error': 'Invalid message format. Message key is required.'
            }))
            return
            
        message = data['message']
        user_id = data['user_id']
        parent_id = data.get('parent_id')  # Optional for replies

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
                'type': 'thread_message',
                'message': message,
                'user_id': user_id,
                'username': username,
                'message_id': message_obj.id,
                'parent_id': parent_id,
                'timestamp': timestamp
            }
        )

    # Receive message from room group
    async def thread_message(self, event):
        message = event['message']
        user_id = event['user_id']
        username = event['username']
        timestamp = event['timestamp']
        message_id = event['message_id']
        parent_id = event.get('parent_id')
        
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'message': message,
            'user_id': user_id,
            'username': username,
            'message_id': message_id,
            'parent_id': parent_id,
            'timestamp': timestamp
        }))
    
    @database_sync_to_async
    def save_message(self, user_id, content, parent_id=None):
        user = User.objects.get(pk=user_id)
        work_item = WorkItem.objects.get(pk=self.work_item_id)
        thread = Thread.objects.get(pk=self.thread_id)
        
        # Handle replies
        parent = None
        if parent_id:
            parent = Message.objects.get(pk=parent_id)
        
        # Create message
        message = Message.objects.create(
            work_item=work_item,
            thread=thread,
            user=user,
            content=content,
            parent=parent,
            is_thread_starter=False
        )
        
        # Create notifications for thread participants except the message sender
        self.create_notifications(message, user_id)
        
        return message
        
    @database_sync_to_async
    def get_username(self, user_id):
        user = User.objects.get(pk=user_id)
        return user.username
    
    @database_sync_to_async
    def create_notifications(self, message_obj, sender_id):
        thread = message_obj.thread
        
        # Get participants who should be notified
        participants = thread.get_participants()
        sender = User.objects.get(pk=sender_id)
        
        # Create notifications for participants except sender
        for participant in participants:
            if participant.id != int(sender_id):
                # Check notification preferences before creating
                should_notify = True
                try:
                    prefs = participant.notification_preferences
                    should_notify = prefs.should_notify(message_obj.work_item, thread)
                except Exception:
                    pass  # Default to notifying if preferences check fails
                    
                if should_notify:
                    Notification.objects.create(
                        user=participant,
                        message=f"{sender.username} posted in thread '{thread.title}'",
                        work_item=message_obj.work_item,
                        thread=thread,  # Store thread reference
                        notification_type='message'
                    )