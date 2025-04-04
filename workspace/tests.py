from django.test import TestCase, Client, RequestFactory
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.db.models import Q
from django.http import JsonResponse
from django.contrib.sessions.models import Session
from django.contrib.messages import get_messages
from unittest.mock import patch, MagicMock, call, ANY
import unittest
import datetime
import json

from workspace.models import (
    WorkItem, Message, Thread, ThreadGroup, FileAttachment, Notification, NotificationPreference,
    MessageReadReceipt, SlowChannel, SlowChannelMessage, ScheduledMessage, BreakEvent,
    ThreadMessage, UserOnlineStatus
)
from workspace.forms import (
    WorkItemForm, MessageForm, FileAttachmentForm, NotificationPreferenceForm, 
    ThreadForm, ScheduledMessageForm, SlowChannelForm, SlowChannelMessageForm
)
from workspace.views import (
    dashboard, work_item_detail, create_work_item, update_work_item, delete_work_item,
    thread_detail, create_thread, update_thread, upload_file, notifications_list,
    mark_notification_read, mark_all_read, notification_preferences,
    schedule_message, my_scheduled_messages, mark_message_read, get_message_read_status,
    slow_channel_detail, create_slow_channel, update_slow_channel
)


class BreakEventModelTests(TestCase):
    """Tests for BreakEvent model"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword'
        )
        
        self.start_time = timezone.now() - datetime.timedelta(minutes=15)
        self.break_event = BreakEvent.objects.create(
            user=self.user,
            start_time=self.start_time
        )
    
    def test_break_event_creation(self):
        """Test creating a BreakEvent"""
        self.assertEqual(self.break_event.user, self.user)
        self.assertEqual(self.break_event.start_time, self.start_time)
        self.assertIsNone(self.break_event.end_time)
        self.assertIsNone(self.break_event.duration)
        self.assertFalse(self.break_event.completed)
    
    def test_calculate_duration(self):
        """Test the calculate_duration method"""
        # Initially no end time
        self.assertIsNone(self.break_event.calculate_duration())
        
        # Set end time and calculate duration
        end_time = self.start_time + datetime.timedelta(minutes=10)
        self.break_event.end_time = end_time
        self.break_event.save()
        
        # Duration should be 10 minutes in seconds
        expected_duration = 10 * 60  # 10 minutes in seconds
        self.assertEqual(self.break_event.calculate_duration(), expected_duration)


class MessageReadReceiptModelTests(TestCase):
    """Tests for MessageReadReceipt model"""
    
    def setUp(self):
        """Set up test data"""
        self.sender = User.objects.create_user(
            username='sender',
            email='sender@example.com',
            password='senderpassword'
        )
        
        self.reader = User.objects.create_user(
            username='reader',
            email='reader@example.com',
            password='readerpassword'
        )
        
        self.work_item = WorkItem.objects.create(
            title='Test Work Item',
            description='This is a test work item',
            type='task',
            owner=self.sender
        )
        self.work_item.collaborators.add(self.reader)
        
        self.message = Message.objects.create(
            work_item=self.work_item,
            user=self.sender,
            content='Test message'
        )
        
        self.read_receipt = MessageReadReceipt.objects.create(
            message=self.message,
            user=self.reader,
            read_duration=datetime.timedelta(seconds=30)
        )
    
    def test_read_receipt_creation(self):
        """Test creating a MessageReadReceipt"""
        self.assertEqual(self.read_receipt.message, self.message)
        self.assertEqual(self.read_receipt.user, self.reader)
        self.assertEqual(self.read_receipt.read_duration, datetime.timedelta(seconds=30))
        self.assertFalse(self.read_receipt.has_responded)
    
    def test_read_receipt_str_representation(self):
        """Test the string representation of MessageReadReceipt"""
        expected = f"{self.reader.username} read message {self.message.id} at {self.read_receipt.read_at}"
        self.assertEqual(str(self.read_receipt), expected)
    
    def test_read_receipt_ordering(self):
        """Test that read receipts are ordered by read_at (oldest first)"""
        # Create a second read receipt with older time
        older_time = timezone.now() - datetime.timedelta(hours=1)
        older_receipt = MessageReadReceipt.objects.create(
            message=self.message,
            user=self.sender,  # Using sender as another reader for test purposes
            read_duration=datetime.timedelta(seconds=15)
        )
        # Update the read_at to an older time
        MessageReadReceipt.objects.filter(pk=older_receipt.pk).update(read_at=older_time)
        
        # Create a third read receipt with newer time
        newer_receipt = MessageReadReceipt.objects.create(
            message=self.message,
            user=User.objects.create_user('another', 'another@example.com', 'anotherpass')
        )
        
        # Get receipts ordered by default ordering
        receipts = MessageReadReceipt.objects.filter(message=self.message)
        
        # Should be ordered by read_at (oldest first)
        self.assertEqual(receipts[0], older_receipt)
        self.assertEqual(receipts[1], self.read_receipt)
        self.assertEqual(receipts[2], newer_receipt)
    
    def test_read_receipt_unique_constraint(self):
        """Test that a user can only have one read receipt per message"""
        # Attempt to create a duplicate receipt
        with self.assertRaises(Exception):  # Could be IntegrityError or ValidationError
            MessageReadReceipt.objects.create(
                message=self.message,
                user=self.reader
            )


class UserOnlineStatusTests(TestCase):
    """Tests for UserOnlineStatus model"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword'
        )
        
        self.status = UserOnlineStatus.objects.create(
            user=self.user,
            status='online',
            status_message='Working on tests'
        )
    
    def test_online_status_creation(self):
        """Test creating a UserOnlineStatus"""
        self.assertEqual(self.status.user, self.user)
        self.assertEqual(self.status.status, 'online')
        self.assertEqual(self.status.status_message, 'Working on tests')
        self.assertEqual(self.status.device_info, {})
    
    def test_online_status_str_representation(self):
        """Test the string representation of UserOnlineStatus"""
        expected = f"{self.user.username}: online"
        self.assertEqual(str(self.status), expected)
    
    def test_update_status(self):
        """Test the update_status method"""
        # Update with new status
        self.status.update_status('away', 'Taking a break', 'test_session_key')
        
        # Status should be updated
        self.assertEqual(self.status.status, 'away')
        self.assertEqual(self.status.status_message, 'Taking a break')
        
        # Device info should be updated
        self.assertIn('test_session_key', self.status.device_info)
        device_info = self.status.device_info['test_session_key']
        self.assertEqual(device_info['status'], 'away')
        self.assertIn('last_active', device_info)


class ReadReceiptViewTests(TestCase):
    """Tests for read receipt views"""
    
    def setUp(self):
        """Set up test data and client"""
        self.client = Client()
        
        self.sender = User.objects.create_user(
            username='sender',
            email='sender@example.com',
            password='senderpassword'
        )
        
        self.reader = User.objects.create_user(
            username='reader',
            email='reader@example.com',
            password='readerpassword'
        )
        
        self.work_item = WorkItem.objects.create(
            title='Test Work Item',
            description='This is a test work item',
            type='task',
            owner=self.sender
        )
        self.work_item.collaborators.add(self.reader)
        
        self.message = Message.objects.create(
            work_item=self.work_item,
            user=self.sender,
            content='Test message'
        )
        
        self.thread = Thread.objects.create(
            title='Test Thread',
            work_item=self.work_item,
            created_by=self.sender,
            is_public=True
        )
        
        self.thread_message = Message.objects.create(
            work_item=self.work_item,
            thread=self.thread,
            user=self.sender,
            content='Test thread message'
        )
        
        self.notification_pref, created = NotificationPreference.objects.get_or_create(
        user=self.reader,
        defaults={
            'share_read_receipts': True
        }
    )
    
    # If it already existed, update it
        if not created:
            self.notification_pref.share_read_receipts = True
            self.notification_pref.save()
        
        # URLs
        self.mark_read_url = reverse('mark_message_read', args=[self.message.pk])
        self.get_read_status_url = reverse('get_message_read_status', args=[self.message.pk])
        self.mark_thread_read_url = reverse('mark_thread_read', args=[self.thread.pk])
    
    def test_mark_message_read_view(self):
        """Test marking a message as read"""
        self.client.login(username='reader', password='readerpassword')
        
        response = self.client.post(self.mark_read_url)
        
        # Should return success JSON
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        
        # Should create a read receipt
        self.assertTrue(
            MessageReadReceipt.objects.filter(
                message=self.message, 
                user=self.reader
            ).exists()
        )

    def test_mark_message_read_view_own_message(self):
        """Test marking your own message as read (should be skipped)"""
        self.client.login(username='sender', password='senderpassword')
        
        response = self.client.post(self.mark_read_url)
        
        # Should return success JSON
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['message'], 'Skipped own message')
        
        # Should NOT create a read receipt
        self.assertFalse(
            MessageReadReceipt.objects.filter(
                message=self.message, 
                user=self.sender
            ).exists()
        )
    
    def test_mark_message_read_view_receipts_disabled(self):
        """Test marking a message as read when read receipts are disabled"""
        # Disable read receipts for reader
        prefs = NotificationPreference.objects.get(user=self.reader)
        prefs.share_read_receipts = False
        prefs.save()
        
        self.client.login(username='reader', password='readerpassword')
        
        response = self.client.post(self.mark_read_url)
        
        # Should return success JSON
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['message'], 'Read receipts disabled by user')
    
    def test_get_message_read_status_view(self):
        """Test getting read status for a message"""
        # First create a read receipt
        receipt = MessageReadReceipt.objects.create(
            message=self.message,
            user=self.reader
        )
        
        # Log in as the message author
        self.client.login(username='sender', password='senderpassword')
        
        response = self.client.get(self.get_read_status_url)
        
        # Should return success JSON with read info
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        
        # Should include reader in read_by
        read_by_usernames = [reader['username'] for reader in data['read_by']]
        self.assertIn('reader', read_by_usernames)
        
        # Should include total counts
        self.assertEqual(data['total_read'], 1)
    
    def test_get_message_read_status_view_not_author(self):
        """Test that only the author can get read status"""
        self.client.login(username='reader', password='readerpassword')
        
        response = self.client.get(self.get_read_status_url)
        
        # Should return error JSON
        self.assertEqual(response.status_code, 403)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'error')
    
    def test_mark_thread_read_view(self):
        """Test marking all messages in a thread as read"""
        # Add another message to the thread
        second_message = Message.objects.create(
            work_item=self.work_item,
            thread=self.thread,
            user=self.sender,
            content='Second thread message'
        )
        
        self.client.login(username='reader', password='readerpassword')
        
        response = self.client.post(self.mark_thread_read_url)
        
        # Should return success JSON
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['read_count'], 2)
        
        # Should create read receipts for both messages
        self.assertTrue(
            MessageReadReceipt.objects.filter(
                message=self.thread_message, 
                user=self.reader
            ).exists()
        )
        self.assertTrue(
            MessageReadReceipt.objects.filter(
                message=second_message, 
                user=self.reader
            ).exists()
        )


class WebSocketConsumerTests(TestCase):
    """Tests for WebSocket consumers"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword'
        )
        
        self.collaborator = User.objects.create_user(
            username='collaborator',
            email='collab@example.com',
            password='collabpassword'
        )
        
        self.work_item = WorkItem.objects.create(
            title='Test Work Item',
            description='This is a test work item',
            type='task',
            owner=self.user
        )
        self.work_item.collaborators.add(self.collaborator)
        
        self.thread = Thread.objects.create(
            title='Test Thread',
            work_item=self.work_item,
            created_by=self.user,
            is_public=True
        )
    
    @patch('workspace.consumers.ChatConsumer.channel_layer')
    @patch('workspace.consumers.ChatConsumer.accept')
    @patch('workspace.consumers.async_to_sync')
    def test_chat_consumer_connect(self, mock_async_to_sync, mock_accept, mock_channel_layer):
        """Test ChatConsumer connect method"""
        from workspace.consumers import ChatConsumer
        
        # Mock async_to_sync to just return the function
        mock_async_to_sync.side_effect = lambda f: f
        
        # Create a mock scope
        scope = {
            'url_route': {'kwargs': {'work_item_id': self.work_item.id}}
        }
        
        # Create the consumer
        consumer = ChatConsumer()
        consumer.scope = scope
        
        # Call connect
        consumer.connect()
        
        # Should accept the connection
        mock_accept.assert_called_once()
        
        # Should add to the group
        group_name = f'chat_{self.work_item.id}'
        mock_channel_layer.group_add.assert_called_with(
            group_name,
            consumer.channel_name
        )
    
    @patch('workspace.consumers.ChatConsumer.channel_layer')
    @patch('workspace.consumers.Message.objects.create')
    @patch('workspace.consumers.async_to_sync')
    def test_chat_consumer_receive(
        self, mock_async_to_sync, mock_create_message, mock_channel_layer
    ):
        """Test ChatConsumer receive method"""
        from workspace.consumers import ChatConsumer
        
        # Mock the created message
        mock_message = MagicMock()
        mock_message.created_at.strftime.return_value = '2025-01-01 12:00:00'
        mock_create_message.return_value = mock_message
        
        # Mock async_to_sync to just return the function
        mock_async_to_sync.side_effect = lambda f: f
        
        # Create a mock scope
        scope = {
            'url_route': {'kwargs': {'work_item_id': self.work_item.id}}
        }
        
        # Create the consumer
        consumer = ChatConsumer()
        consumer.scope = scope
        consumer.channel_name = 'test_channel'
        consumer.room_group_name = f'chat_{self.work_item.id}'
        
        # Create message data
        message_data = json.dumps({
            'message': 'Test message',
            'user_id': self.user.id
        })
        
        # Call receive
        consumer.receive(text_data=message_data)
        
        # Should create a message
        mock_create_message.assert_called_with(
            work_item=self.work_item,
            user=ANY,  # We can't directly compare User objects in the mock
            content='Test message'
        )
        
        # Should broadcast to the group
        mock_channel_layer.group_send.assert_called_with(
            f'chat_{self.work_item.id}',
            {
                'type': 'chat_message',
                'message': 'Test message',
                'user_id': self.user.id,
                'username': ANY,
                'timestamp': ANY
            }
        )
    
    @patch('workspace.consumers.ThreadConsumer.channel_layer')
    @patch('workspace.consumers.Message.objects.create')
    @patch('workspace.consumers.async_to_sync')
    def test_thread_consumer_receive(
        self, mock_async_to_sync, mock_create_message, mock_channel_layer
    ):
        """Test ThreadConsumer receive method"""
        from workspace.consumers import ThreadConsumer
        
        # Mock the created message
        mock_message = MagicMock()
        mock_message.created_at.strftime.return_value = '2025-01-01 12:00:00'
        mock_message.id = 123
        mock_create_message.return_value = mock_message
        
        # Mock async_to_sync to just return the function
        mock_async_to_sync.side_effect = lambda f: f
        
        # Create a mock scope
        scope = {
            'url_route': {
                'kwargs': {
                    'work_item_id': self.work_item.id,
                    'thread_id': self.thread.id
                }
            }
        }
        
        # Create the consumer
        consumer = ThreadConsumer()
        consumer.scope = scope
        consumer.channel_name = 'test_channel'
        consumer.room_group_name = f'thread_{self.thread.id}'
        
        # Mock save_message method to return our mock message
        consumer.save_message = MagicMock(return_value=mock_message)
        
        # Create message data
        message_data = json.dumps({
            'message': 'Test thread message',
            'user_id': self.user.id
        })
        
        # Call receive
        consumer.receive(text_data=message_data)
        
        # Should save the message
        consumer.save_message.assert_called_with(
            self.user.id, 'Test thread message', None
        )
        
        # Should broadcast to the group
        mock_channel_layer.group_send.assert_called_with(
            f'thread_{self.thread.id}',
            {
                'type': 'thread_message',
                'message': 'Test thread message',
                'user_id': self.user.id,
                'username': ANY,
                'message_id': 123,
                'parent_id': None,
                'timestamp': ANY
            }
        )
    
    @patch('workspace.consumers.NotificationConsumer.channel_layer')
    @patch('workspace.consumers.async_to_sync')
    def test_notification_consumer_notification_message(
        self, mock_async_to_sync, mock_channel_layer
    ):
        """Test NotificationConsumer notification_message method"""
        from workspace.consumers import NotificationConsumer
        
        # Mock async_to_sync to just return the function
        mock_async_to_sync.side_effect = lambda f: f
        
        # Create mock scope with authenticated user
        scope = {
            'user': self.user
        }
        
        # Create a notification event
        event = {
            'message': 'Test notification',
            'count': 3
        }
        
        # Create the consumer
        consumer = NotificationConsumer()
        consumer.scope = scope
        
        # Mock the send method
        consumer.send = MagicMock()
        
        # Mock check_notification_preferences to return True
        consumer.check_notification_preferences = MagicMock(return_value=True)
        
        # Call notification_message
        consumer.notification_message(event)
        
        # Should send notification to WebSocket
        consumer.send.assert_called_with(text_data=ANY)
        
        # Check the JSON content
        called_args = consumer.send.call_args[1]['text_data']
        data = json.loads(called_args)
        self.assertEqual(data['type'], 'notification')
        self.assertEqual(data['message'], 'Test notification')
        self.assertEqual(data['count'], 3)
    
    @patch('workspace.consumers.FileConsumer.channel_layer')
    @patch('workspace.consumers.async_to_sync')
    def test_file_consumer_receive(self, mock_async_to_sync, mock_channel_layer):
        """Test FileConsumer receive method"""
        from workspace.consumers import FileConsumer
        
        # Mock async_to_sync to just return the function
        mock_async_to_sync.side_effect = lambda f: f
        
        # Create a mock scope
        scope = {
            'url_route': {'kwargs': {'work_item_id': self.work_item.id}}
        }
        
        # Create the consumer
        consumer = FileConsumer()
        consumer.scope = scope
        consumer.channel_name = 'test_channel'
        consumer.room_group_name = f'file_{self.work_item.id}'
        
        # Create file data
        file_data = json.dumps({
            'message': 'Shared a file',
            'user_id': self.user.id,
            'username': 'testuser',
            'file_name': 'test.txt'
        })
        
        # Call receive
        consumer.receive(text_data=file_data)
        
        # Should broadcast to the group
        mock_channel_layer.group_send.assert_called_with(
            f'file_{self.work_item.id}',
            {
                'type': 'file_message',
                'message': 'Shared a file',
                'user_id': self.user.id,
                'username': ANY,
                'file_name': 'test.txt'
            }
        )


class CeleryTaskTests(TestCase):
    """Tests for Celery tasks"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword'
        )
        
        self.work_item = WorkItem.objects.create(
            title='Test Work Item',
            description='This is a test work item',
            type='task',
            owner=self.user
        )
        
        # Set scheduled time to be in the past
        self.past_time = timezone.now() - datetime.timedelta(hours=1)
        
        self.scheduled_message = ScheduledMessage.objects.create(
            sender=self.user,
            work_item=self.work_item,
            content='This is a scheduled message',
            scheduled_time=self.past_time,
            is_sent=False
        )
        
        # Create a slow channel
        self.slow_channel = SlowChannel.objects.create(
            title='Reflection Channel',
            description='For team reflections',
            type='reflection',
            work_item=self.work_item,
            created_by=self.user,
            message_frequency='daily'
        )
        self.slow_channel.participants.add(self.user)
        
        # Create a slow channel message scheduled for delivery
        self.sc_message = SlowChannelMessage.objects.create(
            channel=self.slow_channel,
            user=self.user,
            content='This is a slow channel message',
            scheduled_delivery=self.past_time,
            is_delivered=False
        )
    
    @patch('workspace.models.Message.objects.create')
    def test_send_scheduled_messages_task(self, mock_create_message):
        """Test task to send scheduled messages"""
        from workspace.tasks import send_scheduled_messages
        
        # Mock the created message
        mock_message = MagicMock()
        mock_create_message.return_value = mock_message
        
        # Run the task
        result = send_scheduled_messages()
        
        # Should be successful and send 1 message
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['sent'], 1)
        self.assertEqual(result['failed'], 0)
        
        # Message should be marked as sent
        self.scheduled_message.refresh_from_db()
        self.assertTrue(self.scheduled_message.is_sent)
        self.assertIsNotNone(self.scheduled_message.sent_at)
        
        # A Message should have been created
        mock_create_message.assert_called_once()
    
    @patch('workspace.models.Notification.objects.create')
    def test_deliver_slow_channel_messages_task(self, mock_create_notification):
        """Test task to deliver slow channel messages"""
        from workspace.tasks import deliver_slow_channel_messages
        
        # Mock the created notification
        mock_notification = MagicMock()
        mock_create_notification.return_value = mock_notification
        
        # Run the task
        result = deliver_slow_channel_messages()
        
        # Should be successful and deliver 1 message
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['delivered'], 1)
        self.assertEqual(result['failed'], 0)
        
        # Message should be marked as delivered
        self.sc_message.refresh_from_db()
        self.assertTrue(self.sc_message.is_delivered)
        self.assertIsNotNone(self.sc_message.delivered_at)
    
    @patch('workspace.models.SlowChannel.get_next_delivery_time')
    def test_schedule_new_message_delivery_task(self, mock_next_delivery):
        """Test task to schedule new message delivery"""
        from workspace.tasks import schedule_new_message_delivery
        
        # Mock next delivery time
        delivery_time = timezone.now() + datetime.timedelta(hours=1)
        mock_next_delivery.return_value = delivery_time
        
        # Create a new message without scheduled delivery
        message = SlowChannelMessage.objects.create(
            channel=self.slow_channel,
            user=self.user,
            content='New message for scheduling',
            is_delivered=False
        )
        
        # Run the task
        result = schedule_new_message_delivery(message.id)
        
        # Should be successful
        self.assertEqual(result['status'], 'success')
        
        # Message should have scheduled delivery time
        message.refresh_from_db()
        self.assertEqual(message.scheduled_delivery, delivery_time)


class ScheduledTaskManagementCommandTests(TestCase):
    """Tests for management commands related to scheduled tasks"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword'
        )
        
        self.work_item = WorkItem.objects.create(
            title='Test Work Item',
            description='This is a test work item',
            type='task',
            owner=self.user
        )
        
        # Set scheduled time to be in the past
        self.past_time = timezone.now() - datetime.timedelta(hours=1)
        
        self.scheduled_message = ScheduledMessage.objects.create(
            sender=self.user,
            work_item=self.work_item,
            content='This is a scheduled message',
            scheduled_time=self.past_time,
            is_sent=False
        )
        
        # Create a slow channel
        self.slow_channel = SlowChannel.objects.create(
            title='Reflection Channel',
            description='For team reflections',
            type='reflection',
            work_item=self.work_item,
            created_by=self.user,
            message_frequency='daily'
        )
        self.slow_channel.participants.add(self.user)
        
        # Create a slow channel message scheduled for delivery
        self.sc_message = SlowChannelMessage.objects.create(
            channel=self.slow_channel,
            user=self.user,
            content='This is a slow channel message',
            scheduled_delivery=self.past_time,
            is_delivered=False
        )
    
    @patch('workspace.management.commands.send_scheduled_messages.ScheduledMessage.send')
    def test_send_scheduled_messages_command(self, mock_send):
        """Test the send_scheduled_messages management command"""
        # Mock the send method
        mock_send.return_value = MagicMock()
        
        # Call the command
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command('send_scheduled_messages', stdout=out)
        
        # Check command output
        output = out.getvalue()
        self.assertIn('Found 1 scheduled messages to send', output)
        self.assertIn('1 sent successfully', output)
        
        # Send should have been called once
        mock_send.assert_called_once()
    
    @patch('workspace.management.commands.deliver_slow_channel_messages.SlowChannelMessage.mark_delivered')
    def test_deliver_slow_channel_messages_command(self, mock_mark_delivered):
        """Test the deliver_slow_channel_messages management command"""
        # Call the command
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command('deliver_slow_channel_messages', stdout=out)
        
        # Check command output
        output = out.getvalue()
        self.assertIn('Found 1 slow channel messages to deliver', output)
        self.assertIn('1 delivered successfully', output)
        
        # mark_delivered should have been called once
        mock_mark_delivered.assert_called_once()


class NotificationHandlingTests(TestCase):
    """Tests for notification handling logic"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword'
        )
        
        self.work_item = WorkItem.objects.create(
            title='Test Work Item',
            description='This is a test work item',
            type='task',
            owner=self.user
        )
        
        # Instead of creating a new preference, get or update the existing one
        self.notification_pref, created = NotificationPreference.objects.get_or_create(
            user=self.user,
            defaults={
                'dnd_enabled': True,
                'dnd_start_time': datetime.time(22, 0),
                'dnd_end_time': datetime.time(8, 0),
                'notification_mode': 'all'
            }
        )
        
        # If it already existed, update it
        if not created:
            self.notification_pref.dnd_enabled = True
            self.notification_pref.dnd_start_time = datetime.time(22, 0)
            self.notification_pref.dnd_end_time = datetime.time(8, 0)
            self.notification_pref.notification_mode = 'all'
            self.notification_pref.save()
        
        self.notification = Notification.objects.create(
            user=self.user,
            message='Test notification',
            work_item=self.work_item,
            notification_type='message',
            priority='normal'
        )
    
    @patch('workspace.models.timezone')
    @patch('workspace.signals._deliver_notification')
    def test_send_notification_normal_hours(self, mock_deliver, mock_timezone):
        """Test sending notifications during normal hours"""
        from workspace.signals import send_notification
        
        # Mock time to be during normal hours (2 PM)
        mock_time = MagicMock()
        mock_time.time.return_value = datetime.time(14, 0)
        mock_timezone.localtime.return_value = mock_time
        
        # Send the notification
        send_notification(self.notification)
        
        # Should deliver immediately
        mock_deliver.assert_called_once_with(self.notification)
    
    @patch('workspace.models.timezone')
    @patch('workspace.signals._deliver_notification')
    def test_send_notification_dnd_hours(self, mock_deliver, mock_timezone):
        """Test sending notifications during DND hours"""
        from workspace.signals import send_notification
        
        # Mock time to be during DND hours (11 PM)
        mock_time = MagicMock()
        mock_time.time.return_value = datetime.time(23, 0)
        mock_timezone.localtime.return_value = mock_time
        
        # Send the notification
        send_notification(self.notification)
        
        # Should not deliver
        mock_deliver.assert_not_called()
        
        # Notification should be marked as delayed
        self.notification.refresh_from_db()
        self.assertTrue(self.notification.is_delayed)
    
    @patch('workspace.signals._deliver_notification')
    def test_send_notification_urgent(self, mock_deliver):
        """Test sending urgent notifications (bypass DND)"""
        from workspace.signals import send_notification
        
        # Make notification urgent
        self.notification.priority = 'urgent'
        self.notification.save()
        
        # Send the notification
        send_notification(self.notification)
        
        # Should deliver even during DND
        mock_deliver.assert_called_once_with(self.notification)
    
    @patch('workspace.signals._deliver_notification')
    def test_send_notification_muted_work_item(self, mock_deliver):
        """Test sending notifications for muted work item"""
        from workspace.signals import send_notification
        
        # Mute the work item
        self.notification_pref.muted_channels.add(self.work_item)
        
        # Send the notification
        send_notification(self.notification)
        
        # Should not deliver
        mock_deliver.assert_not_called()
        
        # Notification should be marked as from muted source
        self.notification.refresh_from_db()
        self.assertTrue(self.notification.is_from_muted)
    
    @patch('workspace.signals._deliver_notification')
    def test_send_notification_focus_mode(self, mock_deliver):
        """Test sending notifications in focus mode"""
        from workspace.signals import send_notification
        
        # Enable focus mode
        self.notification_pref.focus_mode = True
        self.notification_pref.save()
        
        # Add sample focus user and work item
        other_user = User.objects.create_user('other', 'other@example.com', 'otherpass')
        focus_work_item = WorkItem.objects.create(
            title='Focus Work Item',
            type='task',
            owner=self.user
        )
        
        self.notification_pref.focus_users.add(other_user)
        self.notification_pref.focus_work_items.add(focus_work_item)
        
        # Create a notification from non-focus source
        non_focus_notif = Notification.objects.create(
            user=self.user,
            message='Non-focus notification',
            work_item=self.work_item,  # Not a focus work item
            notification_type='message'
        )
        
        # Send the notification
        send_notification(non_focus_notif)
        
        # Should not deliver
        mock_deliver.assert_not_called()
        
        # Notification should be marked as filtered by focus mode
        non_focus_notif.refresh_from_db()
        self.assertTrue(non_focus_notif.is_focus_filtered)
        
        # Create a notification from focus source
        focus_notif = Notification.objects.create(
            user=self.user,
            message='Focus notification',
            work_item=focus_work_item,  # Focus work item
            notification_type='message'
        )
        
        # Reset mock
        mock_deliver.reset_mock()
        
        # Send the notification
        send_notification(focus_notif)
        
        # Should deliver
        mock_deliver.assert_called_once_with(focus_notif)


if __name__ == '__main__':
    unittest.main()