import pytest
from django.test import TestCase
from django.contrib.auth.models import User
from channels.testing import WebsocketCommunicator, ChannelsLiveServerTestCase
from channels.routing import URLRouter
from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from django.urls import reverse, re_path
import json

from workspace.consumers import ChatConsumer
from workspace.models import WorkItem, Message, FileAttachment, Notification


class ChatConsumerTestCase(ChannelsLiveServerTestCase):
    """Test case for the chat WebSocket consumer.
    
    Using ChannelsLiveServerTestCase runs an actual ASGI server during tests.
    """
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Set up channels routing for tests only
        cls.application = AuthMiddlewareStack(
            URLRouter([
                re_path(r'ws/chat/(?P<work_item_id>\w+)/$', ChatConsumer.as_asgi()),
            ])
        )
    
    async def test_connect_to_valid_room(self):
        """Test connecting to a valid chat room."""
        # Set up test data
        user = await database_sync_to_async(User.objects.create_user)(
            username='testuser', password='password123')
        work_item = await database_sync_to_async(WorkItem.objects.create)(
            title='Test Item', description='Test description', type='task', owner=user)
        
        # Connect to the chat room
        communicator = WebsocketCommunicator(
            self.application, f"/ws/chat/{work_item.id}/")
        connected, _ = await communicator.connect()
        
        # Verify connection succeeded
        self.assertTrue(connected)
        
        # Disconnect
        await communicator.disconnect()
    
    async def test_send_receive_message(self):
        """Test sending and receiving messages in a chat room."""
        # Set up test data
        user = await database_sync_to_async(User.objects.create_user)(
            username='testuser', password='password123')
        work_item = await database_sync_to_async(WorkItem.objects.create)(
            title='Test Item', description='Test description', type='task', owner=user)
        
        # Connect to the chat room
        communicator = WebsocketCommunicator(
            self.application, f"/ws/chat/{work_item.id}/")
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        
        # Send a message
        await communicator.send_json_to({
            'message': 'Hello, world!',
            'user_id': user.id,
            'username': user.username
        })
        
        # Receive the response message
        response = await communicator.receive_json_from()
        
        # Verify message was received correctly
        self.assertEqual(response['message'], 'Hello, world!')
        self.assertEqual(response['user_id'], str(user.id))  # Note: may be converted to string in JSON
        self.assertEqual(response['username'], user.username)
        
        # Disconnect
        await communicator.disconnect()


class SimpleWorkspaceTestCase(TestCase):
    """Regular TestCase for non-WebSocket tests."""
    
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@example.com', 'password123')
        self.client.login(username='testuser', password='password123')
        self.work_item = WorkItem.objects.create(
            title='Test Item',
            description='Test description',
            type='task',
            owner=self.user
        )
    
    def test_work_item_creation(self):
        """Test creating a work item."""
        self.assertEqual(self.work_item.title, 'Test Item')
        self.assertEqual(self.work_item.owner, self.user)
    
    def test_work_item_detail_view(self):
        """Test the work item detail view."""
        response = self.client.get(reverse('work_item_detail', args=[self.work_item.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'workspace/work_item_detail.html')
        self.assertEqual(response.context['work_item'], self.work_item)
    
    def test_message_creation(self):
        """Test creating a message manually."""
        message = Message.objects.create(
            work_item=self.work_item,
            user=self.user,
            content='Test message'
        )
        self.assertEqual(message.content, 'Test message')
        self.assertEqual(message.user, self.user)
        self.assertEqual(message.work_item, self.work_item)
    
    def test_notification_creation(self):
        """Test creating a notification."""
        notification = Notification.objects.create(
            user=self.user,
            message='Test notification',
            work_item=self.work_item,
            notification_type='message'
        )
        self.assertEqual(notification.message, 'Test notification')
        self.assertEqual(notification.user, self.user)
        self.assertEqual(notification.work_item, self.work_item)
        self.assertEqual(notification.notification_type, 'message')
        self.assertFalse(notification.is_read)
    
    def test_file_upload(self):
        """Test uploading a file."""
        upload_url = reverse('upload_file', args=[self.work_item.id])
        with open('manage.py', 'rb') as file:
            response = self.client.post(upload_url, {'file': file})
        
        # Check redirect to work item detail
        self.assertRedirects(response, reverse('work_item_detail', args=[self.work_item.id]))
        
        # Check file was created
        self.assertTrue(FileAttachment.objects.filter(work_item=self.work_item).exists())