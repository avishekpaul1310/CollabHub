from django.test import TestCase
from django.contrib.auth.models import User
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
import json

from collabhub.asgi import application
from workspace.models import WorkItem, Message, FileAttachment, Notification


class ChatConsumerTests(TestCase):
    """Tests for the ChatConsumer WebSocket consumer."""
    
    async def test_connect_to_valid_room(self):
        """Test connecting to a valid chat room."""
        # Set up test data
        user = await database_sync_to_async(User.objects.create_user)(
            username='testuser', password='password123')
        work_item = await database_sync_to_async(WorkItem.objects.create)(
            title='Test Item', description='Test description', type='task', owner=user)
        
        # Connect to the chat room
        communicator = WebsocketCommunicator(
            application, f"/ws/chat/{work_item.id}/")
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
            application, f"/ws/chat/{work_item.id}/")
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
        self.assertEqual(response['user_id'], user.id)
        self.assertEqual(response['username'], user.username)
        
        # Disconnect
        await communicator.disconnect()
    
    async def test_message_stored_in_database(self):
        """Test that messages sent via WebSocket are stored in the database."""
        # Set up test data
        user = await database_sync_to_async(User.objects.create_user)(
            username='testuser', password='password123')
        work_item = await database_sync_to_async(WorkItem.objects.create)(
            title='Test Item', description='Test description', type='task', owner=user)
        
        # Connect to the chat room
        communicator = WebsocketCommunicator(
            application, f"/ws/chat/{work_item.id}/")
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        
        # Send a message
        await communicator.send_json_to({
            'message': 'Test database storage',
            'user_id': user.id,
            'username': user.username
        })
        
        # Wait for message to be processed
        await communicator.receive_json_from()
        
        # Check database for the message
        message_exists = await database_sync_to_async(
            lambda: Message.objects.filter(
                work_item=work_item,
                user=user,
                content='Test database storage'
            ).exists()
        )()
        
        self.assertTrue(message_exists)
        
        # Disconnect
        await communicator.disconnect()
    
    async def test_notification_created(self):
        """Test that notifications are created when messages are sent."""
        # Set up users - one sender, one receiver
        sender = await database_sync_to_async(User.objects.create_user)(
            username='sender', password='password123')
        receiver = await database_sync_to_async(User.objects.create_user)(
            username='receiver', password='password123')
        
        # Create work item with sender as owner and receiver as collaborator
        work_item = await database_sync_to_async(WorkItem.objects.create)(
            title='Test Item', description='Test description', type='task', owner=receiver)
        
        # Connect to the chat room
        communicator = WebsocketCommunicator(
            application, f"/ws/chat/{work_item.id}/")
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        
        # Send a message from sender
        await communicator.send_json_to({
            'message': 'Test notification',
            'user_id': sender.id,
            'username': sender.username
        })
        
        # Wait for message to be processed
        await communicator.receive_json_from()
        
        # Check if notification was created for receiver
        notification_exists = await database_sync_to_async(
            lambda: Notification.objects.filter(
                user=receiver,
                work_item=work_item,
                notification_type='message'
            ).exists()
        )()
        
        self.assertTrue(notification_exists)
        
        # Disconnect
        await communicator.disconnect()


class FileUploadTests(TestCase):
    """Tests for file uploads in work items."""
    
    def setUp(self):
        self.client.force_login(User.objects.create_user('testuser', 'test@example.com', 'password123'))
        self.work_item = WorkItem.objects.create(
            title='Test Item',
            description='Test description',
            type='task',
            owner=User.objects.get(username='testuser')
        )
        self.upload_url = reverse('upload_file', args=[self.work_item.id])
    
    def test_file_upload(self):
        """Test uploading a file to a work item."""
        # Create a test file
        file_content = b'Test file content'
        test_file = SimpleUploadedFile('test_file.txt', file_content)
        
        # Upload the file
        response = self.client.post(self.upload_url, {'file': test_file})
        
        # Verify redirect back to work item
        self.assertRedirects(response, reverse('work_item_detail', args=[self.work_item.id]))
        
        # Verify file was created in database
        self.assertTrue(FileAttachment.objects.filter(
            work_item=self.work_item,
            name='test_file.txt'
        ).exists())


class NotificationTests(TestCase):
    """Tests for the notification system."""
    
    def setUp(self):
        self.user1 = User.objects.create_user('user1', 'user1@example.com', 'password123')
        self.user2 = User.objects.create_user('user2', 'user2@example.com', 'password123')
        self.work_item = WorkItem.objects.create(
            title='Test Item',
            description='Test description',
            type='project',
            owner=self.user1
        )
        self.work_item.collaborators.add(self.user2)
    
    def test_notification_created_on_message(self):
        """Test that notifications are created when a message is added."""
        # Login as user2
        self.client.login(username='user2', password='password123')
        
        # Create a message manually (not through WebSocket)
        message = Message.objects.create(
            work_item=self.work_item,
            user=self.user2,
            content='Test notification message'
        )
        
        # Check that a notification was created for user1 (owner)
        self.assertTrue(Notification.objects.filter(
            user=self.user1,
            work_item=self.work_item,
            notification_type='message'
        ).exists())
    
    def test_notification_mark_as_read(self):
        """Test marking notifications as read."""
        # Create a notification
        notification = Notification.objects.create(
            user=self.user1,
            message='Test notification',
            work_item=self.work_item,
            notification_type='message'
        )
        
        # Login as user1
        self.client.login(username='user1', password='password123')
        
        # Mark notification as read
        response = self.client.get(reverse('mark_notification_read', args=[notification.id]))
        
        # Verify redirect
        self.assertRedirects(response, reverse('notifications_list'))
        
        # Verify notification is marked as read
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
    
    def test_mark_all_notifications_read(self):
        """Test marking all notifications as read."""
        # Create multiple notifications
        Notification.objects.create(
            user=self.user1,
            message='Test notification 1',
            work_item=self.work_item,
            notification_type='message'
        )
        Notification.objects.create(
            user=self.user1,
            message='Test notification 2',
            work_item=self.work_item,
            notification_type='update'
        )
        
        # Login as user1
        self.client.login(username='user1', password='password123')
        
        # Mark all notifications as read
        response = self.client.get(reverse('mark_all_read'))
        
        # Verify redirect
        self.assertRedirects(response, reverse('notifications_list'))
        
        # Verify all notifications are marked as read
        self.assertEqual(Notification.objects.filter(user=self.user1, is_read=False).count(), 0)