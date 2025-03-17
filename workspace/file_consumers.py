import json
import base64
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.files.base import ContentFile
from django.contrib.auth.models import User
from .models import WorkItem, Message

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
    
    # Receive file data from WebSocket
    async def receive(self, text_data):
        data = json.loads(text_data)
        file_data = data['file_data']
        file_name = data['file_name']
        username = data['username']
        user_id = data['user_id']
        
        # Save file to database
        message = await self.save_file(user_id, file_name, file_data)
        
        # Send file info to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'file_message',
                'file_url': message.file.url if message.file else '',
                'file_name': file_name,
                'username': username
            }
        )
    
    # Receive file info from room group
    async def file_message(self, event):
        file_url = event['file_url']
        file_name = event['file_name']
        username = event['username']
        
        # Send file info to WebSocket
        await self.send(text_data=json.dumps({
            'file_url': file_url,
            'file_name': file_name,
            'username': username
        }))
    
    @database_sync_to_async
    def save_file(self, user_id, file_name, file_data):
        user = User.objects.get(id=user_id)
        work_item = WorkItem.objects.get(id=self.work_item_id)
        
        # Convert base64 to file content
        format, imgstr = file_data.split(';base64,')
        ext = file_name.split('.')[-1]
        file_content = ContentFile(base64.b64decode(imgstr), name=file_name)
        
        # Create message with file
        message = Message.objects.create(
            user=user,
            work_item=work_item,
            content=f"Shared a file: {file_name}",
            file=file_content
        )
        
        return message