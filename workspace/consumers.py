import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from .models import WorkItem, Message

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
        try:
            text_data_json = json.loads(text_data)
            message = text_data_json['message']
            user_id = text_data_json['user_id']

            # Save the message to the database
            await self.save_message(user_id, message)
            
            # Send message to room group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'user_id': user_id,
                    'username': await self.get_username(user_id),
                }
            )
        except Exception as e:
            print(f"Error in receive: {str(e)}")

    # Receive message from room group
    async def chat_message(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'message': event['message'],
            'user_id': event['user_id'],
            'username': event['username'],
        }))
    
    @database_sync_to_async
    def save_message(self, user_id, message):
        try:
            user = User.objects.get(id=user_id)
            work_item = WorkItem.objects.get(id=self.work_item_id)
            # Don't try to access a file field here
            message_obj = Message.objects.create(
                user=user,
                work_item=work_item, 
                content=message
                # No file field here!
            )
            return message_obj
        except Exception as e:
            print(f"Error saving message: {str(e)}")
            raise
    
    @database_sync_to_async
    def get_username(self, user_id):
        return User.objects.get(id=user_id).username

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
        self.user = self.scope['user']
        
        if self.user.is_authenticated:
            self.notification_group_name = f'notifications_{self.user.id}'
            
            # Join notification group
            await self.channel_layer.group_add(
                self.notification_group_name,
                self.channel_name
            )
            
            await self.accept()
        else:
            await self.close()
    
    async def disconnect(self, close_code):
        # Leave notification group
        await self.channel_layer.group_discard(
            self.notification_group_name,
            self.channel_name
        )
    
    # Receive message from notification group
    async def notification_message(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'notification': event['notification']
        }))