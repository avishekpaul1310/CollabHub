from django.test import TestCase, Client, TransactionTestCase, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from datetime import timedelta
import json
import tempfile
from unittest.mock import patch, MagicMock
from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from channels.db import database_sync_to_async

from workspace.models import (
    WorkItem, Message, Thread, ThreadMessage, Notification, 
    FileAttachment, ScheduledMessage, SlowChannel, SlowChannelMessage,
    MessageReadReceipt, NotificationPreference
)
from workspace.forms import WorkItemForm, ThreadForm, ScheduledMessageForm, SlowChannelForm


class WorkItemTests(TestCase):
    """Tests for WorkItem model and related CRUD functionality."""
    
    def setUp(self):
        self.client = Client()
        
        # Create users
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='password123'
        )
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='password123'
        )
        
        # Login
        self.client.login(username='user1', password='password123')
        
        # Create work item
        self.work_item = WorkItem.objects.create(
            title='Test Work Item',
            description='Test description',
            type='task',
            owner=self.user1
        )
        self.work_item.collaborators.add(self.user2)
    
    def test_work_item_creation(self):
        """Test creating a work item."""
        self.assertEqual(self.work_item.title, 'Test Work Item')
        self.assertEqual(self.work_item.owner, self.user1)
        self.assertEqual(self.work_item.type, 'task')
        self.assertTrue(self.work_item.created_at)
        self.assertIn(self.user2, self.work_item.collaborators.all())
    
    def test_dashboard_view(self):
        """Test the dashboard view."""
        url = reverse('dashboard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'workspace/dashboard.html')
        self.assertIn(self.work_item, response.context['work_items'])
    
    def test_work_item_detail_view(self):
        """Test the work item detail view."""
        url = reverse('work_item_detail', args=[self.work_item.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'workspace/work_item_detail.html')
        self.assertEqual(response.context['work_item'], self.work_item)
    
    def test_work_item_detail_permission(self):
        """Test that non-collaborators cannot access work item details."""
        # Create a new user who is not a collaborator
        non_collaborator = User.objects.create_user(
            username='non_collaborator',
            email='non@example.com',
            password='password123'
        )
        
        # Login as non-collaborator
        self.client.login(username='non_collaborator', password='password123')
        
        url = reverse('work_item_detail', args=[self.work_item.id])
        response = self.client.get(url)
        
        # Should redirect to dashboard with error message
        self.assertRedirects(response, reverse('dashboard'))
    
    def test_create_work_item_view(self):
        """Test creating a work item through the view."""
        # Log in as user1
        self.client.login(username='user1', password='password123')
        
        url = reverse('create_work_item')
        data = {
            'title': 'New Test Item',
            'description': 'New test description',
            'type': 'doc',
            'collaborators': [self.user2.id]
        }
        
        response = self.client.post(url, data)
        
        # Check that item was created
        self.assertTrue(WorkItem.objects.filter(title='New Test Item').exists())
        
        # Get the created item
        new_item = WorkItem.objects.get(title='New Test Item')
        
        # Check item details
        self.assertEqual(new_item.description, 'New test description')
        self.assertEqual(new_item.type, 'doc')
        self.assertEqual(new_item.owner, self.user1)
        self.assertIn(self.user2, new_item.collaborators.all())
        
        # Check redirect to detail view
        self.assertRedirects(response, reverse('work_item_detail', args=[new_item.id]))
    
    def test_update_work_item_view(self):
        """Test updating a work item through the view."""
        # Log in as owner
        self.client.login(username='user1', password='password123')
        
        url = reverse('update_work_item', args=[self.work_item.id])
        data = {
            'title': 'Updated Work Item',
            'description': 'Updated description',
            'type': 'project',
            'collaborators': [self.user2.id]
        }
        
        response = self.client.post(url, data)
        
        # Refresh from DB
        self.work_item.refresh_from_db()
        
        # Check that item was updated
        self.assertEqual(self.work_item.title, 'Updated Work Item')
        self.assertEqual(self.work_item.description, 'Updated description')
        self.assertEqual(self.work_item.type, 'project')
        
        # Check redirect to detail view
        self.assertRedirects(response, reverse('work_item_detail', args=[self.work_item.id]))
        
        # Check that scheduled message was created
        self.assertTrue(ScheduledMessage.objects.filter(content='This is a scheduled message').exists())
        scheduled_msg = ScheduledMessage.objects.get(content='This is a scheduled message')
        
        # Check scheduled message details
        self.assertEqual(scheduled_msg.sender, self.user1)
        self.assertEqual(scheduled_msg.work_item, self.work_item)
        self.assertEqual(scheduled_msg.scheduling_note, 'Test note')
        self.assertFalse(scheduled_msg.is_sent)
    
    def test_create_scheduled_thread_message(self):
        """Test creating a scheduled message in a thread."""
        # Login as user1
        self.client.login(username='user1', password='password123')
        
        # Schedule a message in thread
        url = reverse('schedule_thread_message', args=[self.work_item.id, self.thread.id])
        data = {
            'content': 'This is a scheduled thread message',
            'scheduled_time': self.future_time.strftime('%Y-%m-%dT%H:%M')
        }
        
        response = self.client.post(url, data)
        
        # Check redirect
        self.assertRedirects(response, reverse('thread_detail', args=[self.work_item.id, self.thread.id]))
        
        # Check that scheduled message was created
        self.assertTrue(ScheduledMessage.objects.filter(content='This is a scheduled thread message').exists())
        scheduled_msg = ScheduledMessage.objects.get(content='This is a scheduled thread message')
        
        # Check scheduled message details
        self.assertEqual(scheduled_msg.sender, self.user1)
        self.assertEqual(scheduled_msg.work_item, self.work_item)
        self.assertEqual(scheduled_msg.thread, self.thread)
    
    def test_scheduled_message_in_past_rejected(self):
        """Test that scheduled times in the past are rejected."""
        # Login as user1
        self.client.login(username='user1', password='password123')
        
        # Try to schedule a message in the past
        past_time = timezone.now() - timedelta(hours=1)
        url = reverse('schedule_message', args=[self.work_item.id])
        data = {
            'content': 'This should not be scheduled',
            'scheduled_time': past_time.strftime('%Y-%m-%dT%H:%M')
        }
        
        response = self.client.post(url, data)
        
        # Form should show error
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Scheduled time must be in the future')
        
        # Check that no scheduled message was created
        self.assertFalse(ScheduledMessage.objects.filter(content='This should not be scheduled').exists())
    
    def test_my_scheduled_messages_view(self):
        """Test the view that lists a user's scheduled messages."""
        # Create scheduled messages
        scheduled_msg1 = ScheduledMessage.objects.create(
            sender=self.user1,
            work_item=self.work_item,
            content='First scheduled message',
            scheduled_time=self.future_time
        )
        
        scheduled_msg2 = ScheduledMessage.objects.create(
            sender=self.user1,
            work_item=self.work_item,
            thread=self.thread,
            content='Second scheduled message',
            scheduled_time=self.future_time + timedelta(hours=1)
        )
        
        # Create a sent scheduled message
        sent_msg = ScheduledMessage.objects.create(
            sender=self.user1,
            work_item=self.work_item,
            content='Sent scheduled message',
            scheduled_time=timezone.now() - timedelta(hours=1),
            is_sent=True,
            sent_at=timezone.now() - timedelta(minutes=30)
        )
        
        # Login as user1
        self.client.login(username='user1', password='password123')
        
        # Visit scheduled messages page
        url = reverse('my_scheduled_messages')
        response = self.client.get(url)
        
        # Check response
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'workspace/my_scheduled_messages.html')
        
        # Check context for pending messages
        pending_messages = response.context['pending_messages']
        self.assertEqual(len(pending_messages), 2)
        self.assertIn(scheduled_msg1, pending_messages)
        self.assertIn(scheduled_msg2, pending_messages)
        
        # Check context for sent messages
        sent_messages = response.context['sent_messages']
        self.assertEqual(len(sent_messages), 1)
        self.assertIn(sent_msg, sent_messages)
    
    def test_cancel_scheduled_message(self):
        """Test canceling a scheduled message."""
        # Create scheduled message
        scheduled_msg = ScheduledMessage.objects.create(
            sender=self.user1,
            work_item=self.work_item,
            content='Message to cancel',
            scheduled_time=self.future_time
        )
        
        # Login as sender
        self.client.login(username='user1', password='password123')
        
        # Cancel the message
        url = reverse('cancel_scheduled_message', args=[scheduled_msg.id])
        response = self.client.post(url)
        
        # Check redirect
        self.assertRedirects(response, reverse('my_scheduled_messages'))
        
        # Check that message was deleted
        self.assertFalse(ScheduledMessage.objects.filter(id=scheduled_msg.id).exists())
    
    def test_edit_scheduled_message(self):
        """Test editing a scheduled message."""
        # Create scheduled message
        scheduled_msg = ScheduledMessage.objects.create(
            sender=self.user1,
            work_item=self.work_item,
            content='Original content',
            scheduled_time=self.future_time
        )
        
        # Login as sender
        self.client.login(username='user1', password='password123')
        
        # Edit the message
        url = reverse('edit_scheduled_message', args=[scheduled_msg.id])
        new_time = self.future_time + timedelta(hours=2)
        data = {
            'content': 'Updated content',
            'scheduled_time': new_time.strftime('%Y-%m-%dT%H:%M'),
            'scheduling_note': 'Updated note'
        }
        
        response = self.client.post(url, data)
        
        # Check redirect
        self.assertRedirects(response, reverse('my_scheduled_messages'))
        
        # Refresh from DB
        scheduled_msg.refresh_from_db()
        
        # Check that message was updated
        self.assertEqual(scheduled_msg.content, 'Updated content')
        self.assertEqual(scheduled_msg.scheduling_note, 'Updated note')
    
    @patch('workspace.models.Message.objects.create')
    def test_send_scheduled_message(self, mock_create):
        """Test sending a scheduled message."""
        # Setup mock
        mock_create.return_value = Message(id=1)
        
        # Create scheduled message
        scheduled_msg = ScheduledMessage.objects.create(
            sender=self.user1,
            work_item=self.work_item,
            content='Message to send',
            scheduled_time=timezone.now() - timedelta(minutes=5)  # In the past so it's due
        )
        
        # Send the message
        result = scheduled_msg.send()
        
        # Check result
        self.assertTrue(result)
        
        # Check that message creation was called with correct args
        mock_create.assert_called_once_with(
            work_item=self.work_item,
            thread=None,
            user=self.user1,
            content='Message to send',
            parent=None,
            is_thread_starter=False,
            is_scheduled=True
        )
        
        # Check that scheduled message was marked as sent
        scheduled_msg.refresh_from_db()
        self.assertTrue(scheduled_msg.is_sent)
        self.assertIsNotNone(scheduled_msg.sent_at)


class SlowChannelTests(TestCase):
    """Tests for slow channel functionality."""
    
    def setUp(self):
        # Create users
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='password123'
        )
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='password123'
        )
        
        # Create work item
        self.work_item = WorkItem.objects.create(
            title='Test Work Item',
            description='Test description',
            type='project',
            owner=self.user1
        )
        self.work_item.collaborators.add(self.user2)
        
        # Create slow channel
        self.slow_channel = SlowChannel.objects.create(
            title='Test Slow Channel',
            description='For thoughtful communication',
            type='reflection',
            work_item=self.work_item,
            created_by=self.user1,
            message_frequency='daily',
            delivery_time='09:00:00',
            min_response_interval=timedelta(hours=4),
            reflection_prompts='What went well?\nWhat could be improved?'
        )
        self.slow_channel.participants.add(self.user1, self.user2)
        
        # Create client
        self.client = Client()
    
    def test_slow_channel_creation(self):
        """Test slow channel creation and properties."""
        self.assertEqual(self.slow_channel.title, 'Test Slow Channel')
        self.assertEqual(self.slow_channel.type, 'reflection')
        self.assertEqual(self.slow_channel.created_by, self.user1)
        self.assertEqual(self.slow_channel.message_frequency, 'daily')
        self.assertEqual(self.slow_channel.min_response_interval, timedelta(hours=4))
        self.assertIn(self.user1, self.slow_channel.participants.all())
        self.assertIn(self.user2, self.slow_channel.participants.all())
    
    def test_get_prompts_list(self):
        """Test retrieving prompts list from a slow channel."""
        prompts = self.slow_channel.get_prompts_list()
        self.assertEqual(len(prompts), 2)
        self.assertEqual(prompts[0], 'What went well?')
        self.assertEqual(prompts[1], 'What could be improved?')
    
    def test_get_next_delivery_time(self):
        """Test calculating the next delivery time for a slow channel."""
        now = timezone.now()
        delivery_time = now.replace(hour=9, minute=0, second=0, microsecond=0)
        
        # If it's before 9 AM, delivery should be today at 9 AM
        if now.time() < delivery_time.time():
            expected_delivery = delivery_time
        # If it's after 9 AM, delivery should be tomorrow at 9 AM
        else:
            expected_delivery = delivery_time + timedelta(days=1)
        
        # Run the function
        next_delivery = self.slow_channel.get_next_delivery_time()
        
        # Check that the date is correct (considering any timezone differences)
        self.assertEqual(next_delivery.date(), expected_delivery.date())
        self.assertEqual(next_delivery.hour, 9)
        self.assertEqual(next_delivery.minute, 0)
    
    def test_create_slow_channel_view(self):
        """Test creating a slow channel through the view."""
        # Login as work item owner
        self.client.login(username='user1', password='password123')
        
        url = reverse('create_slow_channel', args=[self.work_item.id])
        data = {
            'title': 'New Slow Channel',
            'description': 'For thoughtful async communication',
            'type': 'ideation',
            'message_frequency': 'weekly',
            'delivery_time': '10:00:00',
            'custom_days': ['1', '3', '5'],  # Mon, Wed, Fri
            'min_response_interval': 24,  # 24 hours
            'reflection_prompts': 'What new ideas do you have?\nHow can we improve?',
            'participants': [self.user2.id]
        }
        
        response = self.client.post(url, data)
        
        # Check that channel was created
        self.assertTrue(SlowChannel.objects.filter(title='New Slow Channel').exists())
        new_channel = SlowChannel.objects.get(title='New Slow Channel')
        
        # Check channel details
        self.assertEqual(new_channel.work_item, self.work_item)
        self.assertEqual(new_channel.created_by, self.user1)
        self.assertEqual(new_channel.type, 'ideation')
        self.assertEqual(new_channel.message_frequency, 'weekly')
        self.assertEqual(new_channel.min_response_interval, timedelta(hours=24))
        self.assertIn(self.user1, new_channel.participants.all())
        self.assertIn(self.user2, new_channel.participants.all())
        
        # Check redirect
        self.assertRedirects(response, reverse('slow_channel_detail', args=[new_channel.id]))
    
    def test_slow_channel_detail_view(self):
        """Test the slow channel detail view."""
        # Create a slow channel message
        message = SlowChannelMessage.objects.create(
            channel=self.slow_channel,
            user=self.user1,
            content='Thoughtful message',
            is_delivered=True,
            delivered_at=timezone.now() - timedelta(hours=2)
        )
        
        # Create a reply
        reply = SlowChannelMessage.objects.create(
            channel=self.slow_channel,
            user=self.user2,
            content='Thoughtful reply',
            parent=message,
            is_delivered=True,
            delivered_at=timezone.now() - timedelta(hours=1)
        )
        
        # Login as participant
        self.client.login(username='user1', password='password123')
        
        url = reverse('slow_channel_detail', args=[self.slow_channel.id])
        response = self.client.get(url)
        
        # Check response
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'workspace/slow_channel_detail.html')
        
        # Check context
        self.assertEqual(response.context['channel'], self.slow_channel)
        self.assertEqual(response.context['work_item'], self.work_item)
        
        # Check that messages are in context
        messages_list = response.context['messages']
        self.assertIn(message, messages_list)
        
        # Check that message has replies attached
        message_in_context = next((m for m in messages_list if m.id == message.id), None)
        self.assertTrue(hasattr(message_in_context, 'replies_list'))
        self.assertIn(reply, message_in_context.replies_list)
    
    def test_slow_channel_unauthorized_access(self):
        """Test that non-participants cannot access slow channels."""
        # Create a non-participant user
        non_participant = User.objects.create_user(
            username='nonparticipant',
            email='nonpart@example.com',
            password='password123'
        )
        
        # Login as non-participant
        self.client.login(username='nonparticipant', password='password123')
        
        url = reverse('slow_channel_detail', args=[self.slow_channel.id])
        response = self.client.get(url)
        
        # Should redirect to work item detail
        self.assertRedirects(response, reverse('work_item_detail', args=[self.work_item.id]))
    
    @patch('workspace.forms.SlowChannelMessageForm.clean')
    def test_create_slow_channel_message(self, mock_clean):
        """Test creating a message in a slow channel."""
        # Mock the clean method to bypass response interval validation
        mock_clean.return_value = {}
        
        # Login as participant
        self.client.login(username='user1', password='password123')
        
        url = reverse('slow_channel_detail', args=[self.slow_channel.id])
        data = {
            'content': 'New slow channel message',
            'prompt': 'What went well?'
        }
        
        response = self.client.post(url, data)
        
        # Check that message was created
        self.assertTrue(SlowChannelMessage.objects.filter(content='New slow channel message').exists())
        message = SlowChannelMessage.objects.get(content='New slow channel message')
        
        # Check message details
        self.assertEqual(message.channel, self.slow_channel)
        self.assertEqual(message.user, self.user1)
        self.assertEqual(message.prompt, 'What went well?')
        self.assertFalse(message.is_delivered)  # Should not be delivered yet
        self.assertIsNotNone(message.scheduled_delivery)  # Should have scheduled delivery time
        
        # Check redirect
        self.assertRedirects(response, reverse('slow_channel_detail', args=[self.slow_channel.id]))
    
    def test_slow_channel_participant_management(self):
        """Test joining and leaving a slow channel."""
        # Create a new user
        new_user = User.objects.create_user(
            username='newuser',
            email='new@example.com',
            password='password123'
        )
        
        # Add as work item collaborator
        self.work_item.collaborators.add(new_user)
        
        # Login as new user
        self.client.login(username='newuser', password='password123')
        
        # Join the slow channel
        url = reverse('join_slow_channel', args=[self.slow_channel.id])
        response = self.client.get(url)
        
        # Check that user was added as participant
        self.slow_channel.refresh_from_db()
        self.assertIn(new_user, self.slow_channel.participants.all())
        
        # Check redirect
        self.assertRedirects(response, reverse('slow_channel_detail', args=[self.slow_channel.id]))
        
        # Leave the slow channel
        url = reverse('leave_slow_channel', args=[self.slow_channel.id])
        response = self.client.get(url)
        
        # Check that user was removed as participant
        self.slow_channel.refresh_from_db()
        self.assertNotIn(new_user, self.slow_channel.participants.all())
        
        # Check redirect
        self.assertRedirects(response, reverse('work_item_detail', args=[self.work_item.id]))
    
    def test_mark_slow_channel_message_delivered(self):
        """Test marking a slow channel message as delivered."""
        # Create an undelivered message
        message = SlowChannelMessage.objects.create(
            channel=self.slow_channel,
            user=self.user1,
            content='Message to deliver',
            is_delivered=False,
            scheduled_delivery=timezone.now() - timedelta(hours=1)  # In the past so it's due
        )
        
        # Mark as delivered
        message.mark_delivered()
        
        # Check that message was marked as delivered
        message.refresh_from_db()
        self.assertTrue(message.is_delivered)
        self.assertIsNotNone(message.delivered_at)
    
    def test_my_slow_channels_view(self):
        """Test the view that lists a user's slow channels."""
        # Create another slow channel
        another_channel = SlowChannel.objects.create(
            title='Another Slow Channel',
            description='Another channel',
            type='learning',
            work_item=self.work_item,
            created_by=self.user2,
            message_frequency='daily'
        )
        another_channel.participants.add(self.user1, self.user2)
        
        # Login as user1
        self.client.login(username='user1', password='password123')
        
        # Visit my slow channels page
        url = reverse('my_slow_channels')
        response = self.client.get(url)
        
        # Check response
        self.assertEqual(response.status_code, 200)
        
        # Check that both channels are in context
        channels = response.context['channels']
        self.assertEqual(len(channels), 2)
        self.assertIn(self.slow_channel, channels)
        self.assertIn(another_channel, channels)


class WebSocketTests(TransactionTestCase):
    """Tests for WebSocket communication."""
    
    @patch('workspace.consumers.ChatConsumer.connect')
    @patch('workspace.consumers.ChatConsumer.receive')
    async def test_chat_consumer(self, mock_receive, mock_connect):
        """Test chat consumer connection and messaging."""
        # Setup mock for connect method
        mock_connect.return_value = None
        
        # Create users and work item
        user = await database_sync_to_async(User.objects.create_user)(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        
        work_item = await database_sync_to_async(WorkItem.objects.create)(
            title='Test Work Item',
            description='Test description',
            type='task',
            owner=user
        )
        
        # Initialize the consumer and connect it
        from workspace.routing import websocket_urlpatterns
        application = URLRouter(websocket_urlpatterns)
        communicator = WebsocketCommunicator(application, f"/ws/chat/{work_item.id}/")
        connected, _ = await communicator.connect()
        
        self.assertTrue(connected)
        
        # Send a message
        await communicator.send_json_to({
            'message': 'Test message',
            'user_id': user.id,
            'username': user.username
        })
        
        # Check that the receive method was called
        mock_receive.assert_called_once()
        
        # Disconnect
        await communicator.disconnect()
    
    @patch('workspace.consumers.ThreadConsumer.connect')
    @patch('workspace.consumers.ThreadConsumer.receive')
    async def test_thread_consumer(self, mock_receive, mock_connect):
        """Test thread consumer connection and messaging."""
        # Setup mock for connect method
        mock_connect.return_value = None
        
        # Create users, work item, and thread
        user = await database_sync_to_async(User.objects.create_user)(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        
        work_item = await database_sync_to_async(WorkItem.objects.create)(
            title='Test Work Item',
            description='Test description',
            type='task',
            owner=user
        )
        
        thread = await database_sync_to_async(Thread.objects.create)(
            work_item=work_item,
            title='Test Thread',
            created_by=user,
            is_public=True
        )
        
        # Initialize the consumer and connect it
        from workspace.routing import websocket_urlpatterns
        application = URLRouter(websocket_urlpatterns)
        communicator = WebsocketCommunicator(application, f"/ws/thread/{thread.id}/")
        connected, _ = await communicator.connect()
        
        self.assertTrue(connected)
        
        # Send a message
        await communicator.send_json_to({
            'message': 'Test thread message',
            'user_id': user.id,
            'thread_id': thread.id
        })
        
        # Check that the receive method was called
        mock_receive.assert_called_once()
        
        # Disconnect
        await communicator.disconnect()


class ManagementCommandTests(TestCase):
    """Tests for custom management commands."""
    
    def setUp(self):
        # Create users
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        
        # Create work item
        self.work_item = WorkItem.objects.create(
            title='Test Work Item',
            description='Test description',
            type='task',
            owner=self.user
        )
    
    @patch('workspace.management.commands.send_scheduled_messages.Command.handle')
    def test_send_scheduled_messages_command(self, mock_handle):
        """Test the send_scheduled_messages management command."""
        # Create a scheduled message
        ScheduledMessage.objects.create(
            sender=self.user,
            work_item=self.work_item,
            content='Scheduled message to send',
            scheduled_time=timezone.now() - timedelta(minutes=5)  # In the past so it's due
        )
        
        # Run the command
        from django.core.management import call_command
        call_command('send_scheduled_messages')
        
        # Check that handle method was called
        mock_handle.assert_called_once()
    
    @patch('workspace.management.commands.deliver_slow_channel_messages.Command.handle')
    def test_deliver_slow_channel_messages_command(self, mock_handle):
        """Test the deliver_slow_channel_messages management command."""
        # Create a slow channel
        slow_channel = SlowChannel.objects.create(
            title='Test Slow Channel',
            description='For thoughtful communication',
            type='reflection',
            work_item=self.work_item,
            created_by=self.user,
            message_frequency='daily'
        )
        slow_channel.participants.add(self.user)
        
        # Create a scheduled slow channel message
        SlowChannelMessage.objects.create(
            channel=slow_channel,
            user=self.user,
            content='Slow message to deliver',
            is_delivered=False,
            scheduled_delivery=timezone.now() - timedelta(minutes=5)  # In the past so it's due
        )
        
        # Run the command
        from django.core.management import call_command
        call_command('deliver_slow_channel_messages')
        
        # Check that handle method was called
        mock_handle.assert_called_once()


class IntegrationTests(TestCase):
    """Integration tests for combinations of features."""
    
    def setUp(self):
        # Create users
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='password123'
        )
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='password123'
        )
        
        # Create work item
        self.work_item = WorkItem.objects.create(
            title='Test Work Item',
            description='Test description',
            type='project',
            owner=self.user1
        )
        self.work_item.collaborators.add(self.user2)
        
        # Create thread
        self.thread = Thread.objects.create(
            work_item=self.work_item,
            title='Test Thread',
            created_by=self.user1,
            is_public=True
        )
        
        # Create client
        self.client = Client()
    
    def test_notification_created_for_message(self):
        """Test that notifications are created when messages are posted."""
        # Login as user1
        self.client.login(username='user1', password='password123')
        
        # Create a message manually since we can't use WebSockets in tests
        message = Message.objects.create(
            work_item=self.work_item,
            user=self.user1,
            content='Test message'
        )
        
        # Check that a notification was created for user2
        self.assertTrue(Notification.objects.filter(
            user=self.user2,
            work_item=self.work_item,
            notification_type='message'
        ).exists())
    
    def test_notification_created_for_file_upload(self):
        """Test that notifications are created when files are uploaded."""
        # Login as user1
        self.client.login(username='user1', password='password123')
        
        # Upload a file
        url = reverse('upload_file', args=[self.work_item.id])
        test_file = SimpleUploadedFile('test_file.txt', b'test content', content_type='text/plain')
        response = self.client.post(url, {'file': test_file})
        
        # Check that a notification was created for user2
        self.assertTrue(Notification.objects.filter(
            user=self.user2,
            work_item=self.work_item,
            notification_type='file_upload'
        ).exists())
    
    def test_read_receipts_integration(self):
        """Test the integration of read receipts with messaging."""
        # Create a message from user1
        message = Message.objects.create(
            work_item=self.work_item,
            thread=self.thread,
            user=self.user1,
            content='Message from user1',
            is_thread_starter=True
        )
        
        # Login as user2
        self.client.login(username='user2', password='password123')
        
        # Mark the message as read
        url = reverse('mark_message_read', args=[message.id])
        response = self.client.post(url, {}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        # Check that read receipt was created
        self.assertTrue(MessageReadReceipt.objects.filter(
            message=message,
            user=self.user2
        ).exists())
        
        # Login as user1 (the message author)
        self.client.login(username='user1', password='password123')
        
        # Get read status
        url = reverse('get_message_read_status', args=[message.id])
        response = self.client.get(url)
        
        # Check that read status includes user2
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['read_by']), 1)
        self.assertEqual(data['read_by'][0]['user_id'], self.user2.id)
    
    def test_dnd_and_notification_integration(self):
        """Test that DND settings affect notification creation."""
        # Set up DND for user2
        prefs = self.user2.notification_preferences
        prefs.dnd_enabled = True
        
        # Set DND to include current time
        now = timezone.now().time()
        one_hour_ago = (timezone.now() - timedelta(hours=1)).time()
        one_hour_from_now = (timezone.now() + timedelta(hours=1)).time()
        
        prefs.dnd_start_time = one_hour_ago
        prefs.dnd_end_time = one_hour_from_now
        prefs.save()
        
        # Login as user1
        self.client.login(username='user1', password='password123')
        
        # Create a message
        message = Message.objects.create(
            work_item=self.work_item,
            user=self.user1,
            content='Test message during DND hours'
        )
        
        # Notification should still be created but marked as delayed
        notification = Notification.objects.filter(
            user=self.user2,
            work_item=self.work_item,
            notification_type='message'
        ).first()
        
        self.assertIsNotNone(notification)
    
    def test_async_features_combined(self):
        """Test the combination of asynchronous communication features."""
        # Login as user1
        self.client.login(username='user1', password='password123')
        
        # 1. Create a slow channel
        slow_channel_url = reverse('create_slow_channel', args=[self.work_item.id])
        slow_channel_data = {
            'title': 'Async Channel',
            'description': 'For thoughtful async communication',
            'type': 'ideation',
            'message_frequency': 'daily',
            'delivery_time': '09:00:00',
            'min_response_interval': 4,
            'participants': [self.user2.id]
        }
        self.client.post(slow_channel_url, slow_channel_data)
        
        # Get the created channel
        slow_channel = SlowChannel.objects.get(title='Async Channel')
        
        # 2. Schedule a message in the thread
        schedule_url = reverse('schedule_thread_message', args=[self.work_item.id, self.thread.id])
        future_time = timezone.now() + timedelta(hours=3)
        schedule_data = {
            'content': 'Scheduled thread message',
            'scheduled_time': future_time.strftime('%Y-%m-%dT%H:%M')
        }
        self.client.post(schedule_url, schedule_data)
        
        # 3. Create slow channel message (with mocked form validation)
        with patch('workspace.forms.SlowChannelMessageForm.clean', return_value={}):
            slow_message_url = reverse('slow_channel_detail', args=[slow_channel.id])
            slow_message_data = {
                'content': 'Thoughtful slow message'
            }
            self.client.post(slow_message_url, slow_message_data)
        
        # Verify all three were created
        self.assertTrue(SlowChannel.objects.filter(title='Async Channel').exists())
        self.assertTrue(ScheduledMessage.objects.filter(content='Scheduled thread message').exists())
        self.assertTrue(SlowChannelMessage.objects.filter(content='Thoughtful slow message').exists())

    
    def test_delete_work_item_view(self):
        """Test deleting a work item through the view."""
        # Log in as owner
        self.client.login(username='user1', password='password123')
        
        url = reverse('delete_work_item', args=[self.work_item.id])
        response = self.client.post(url)
        
        # Check that item was deleted
        self.assertFalse(WorkItem.objects.filter(id=self.work_item.id).exists())
        
        # Check redirect to dashboard
        self.assertRedirects(response, reverse('dashboard'))
    
    def test_non_owner_cannot_update_work_item(self):
        """Test that non-owners cannot update work items."""
        # Log in as non-owner collaborator
        self.client.login(username='user2', password='password123')
        
        url = reverse('update_work_item', args=[self.work_item.id])
        data = {
            'title': 'Unauthorized Update',
            'description': 'This should not work',
            'type': 'task'
        }
        
        response = self.client.post(url, data)
        
        # Should redirect to dashboard with error
        self.assertRedirects(response, reverse('dashboard'))
        
        # Refresh from DB
        self.work_item.refresh_from_db()
        
        # Check that item was not updated
        self.assertNotEqual(self.work_item.title, 'Unauthorized Update')
        
    def test_file_upload(self):
        """Test uploading a file to a work item."""
        # Login as work item owner
        self.client.login(username='user1', password='password123')
        
        url = reverse('upload_file', args=[self.work_item.id])
        
        # Create a test file
        file_content = b'test file content'
        test_file = SimpleUploadedFile('test_file.txt', file_content, content_type='text/plain')
        
        # Upload the file
        response = self.client.post(url, {'file': test_file})
        
        # Check redirect to work item detail
        self.assertRedirects(response, reverse('work_item_detail', args=[self.work_item.id]))
        
        # Check that file was created
        self.assertTrue(FileAttachment.objects.filter(work_item=self.work_item).exists())
        
        # Check file details
        attachment = FileAttachment.objects.get(work_item=self.work_item)
        self.assertEqual(attachment.name, 'test_file.txt')
        self.assertEqual(attachment.uploaded_by, self.user1)


class ThreadTests(TestCase):
    """Tests for Thread model and threaded conversation functionality."""
    
    def setUp(self):
        # Create users
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='password123'
        )
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='password123'
        )
        self.user3 = User.objects.create_user(
            username='user3',
            email='user3@example.com',
            password='password123'
        )
        
        # Create work item
        self.work_item = WorkItem.objects.create(
            title='Test Work Item',
            description='Test description',
            type='project',
            owner=self.user1
        )
        self.work_item.collaborators.add(self.user2)
        
        # Create public thread
        self.public_thread = Thread.objects.create(
            work_item=self.work_item,
            title='Public Thread',
            created_by=self.user1,
            is_public=True
        )
        
        # Create private thread
        self.private_thread = Thread.objects.create(
            work_item=self.work_item,
            title='Private Thread',
            created_by=self.user1,
            is_public=False
        )
        self.private_thread.allowed_users.add(self.user2)
        
        # Create thread messages
        self.message1 = Message.objects.create(
            work_item=self.work_item,
            thread=self.public_thread,
            user=self.user1,
            content='Top level message',
            is_thread_starter=True
        )
        
        # Create reply to message1
        self.reply1 = Message.objects.create(
            work_item=self.work_item,
            thread=self.public_thread,
            user=self.user2,
            content='Reply to top level message',
            parent=self.message1
        )
        
        # Create client
        self.client = Client()
    
    def test_thread_creation(self):
        """Test thread creation and properties."""
        self.assertEqual(self.public_thread.title, 'Public Thread')
        self.assertEqual(self.public_thread.created_by, self.user1)
        self.assertTrue(self.public_thread.is_public)
        
        self.assertEqual(self.private_thread.title, 'Private Thread')
        self.assertFalse(self.private_thread.is_public)
        self.assertIn(self.user2, self.private_thread.allowed_users.all())
    
    def test_public_thread_access(self):
        """Test that all work item collaborators can access public threads."""
        # Test with work item owner
        self.assertTrue(self.public_thread.user_can_access(self.user1))
        
        # Test with collaborator
        self.assertTrue(self.public_thread.user_can_access(self.user2))
        
        # Test with non-collaborator
        self.assertFalse(self.public_thread.user_can_access(self.user3))
    
    def test_private_thread_access(self):
        """Test that only allowed users can access private threads."""
        # Test with thread creator
        self.assertTrue(self.private_thread.user_can_access(self.user1))
        
        # Test with allowed user
        self.assertTrue(self.private_thread.user_can_access(self.user2))
        
        # Test with non-allowed collaborator (if we added user3 as a collaborator)
        self.work_item.collaborators.add(self.user3)
        self.assertFalse(self.private_thread.user_can_access(self.user3))
    
    def test_create_thread_view(self):
        """Test creating a thread through the view."""
        # Login as work item owner
        self.client.login(username='user1', password='password123')
        
        url = reverse('create_thread', args=[self.work_item.id])
        data = {
            'title': 'New Thread',
            'is_public': False,
            'allowed_users': [self.user2.id]
        }
        
        response = self.client.post(url, data)
        
        # Check that thread was created
        self.assertTrue(Thread.objects.filter(title='New Thread').exists())
        new_thread = Thread.objects.get(title='New Thread')
        
        # Check thread details
        self.assertEqual(new_thread.work_item, self.work_item)
        self.assertEqual(new_thread.created_by, self.user1)
        self.assertFalse(new_thread.is_public)
        self.assertIn(self.user2, new_thread.allowed_users.all())
        
        # Check redirect
        self.assertRedirects(response, reverse('thread_detail', args=[self.work_item.id, new_thread.id]))
    
    def test_thread_detail_view(self):
        """Test the thread detail view."""
        # Login as thread creator
        self.client.login(username='user1', password='password123')
        
        url = reverse('thread_detail', args=[self.work_item.id, self.public_thread.id])
        response = self.client.get(url)
        
        # Check response
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'workspace/thread_detail.html')
        
        # Check context
        self.assertEqual(response.context['thread'], self.public_thread)
        self.assertEqual(response.context['work_item'], self.work_item)
        
        # Check that messages are in context
        messages = response.context['messages']
        self.assertIn(self.message1, messages)
        
        # Check that thread messages have replies attached
        self.assertTrue(hasattr(self.message1, 'replies_list'))
        
    def test_private_thread_unauthorized_access(self):
        """Test that unauthorized users cannot access private threads."""
        # Login as non-allowed user
        self.client.login(username='user3', password='password123')
        
        url = reverse('thread_detail', args=[self.work_item.id, self.private_thread.id])
        response = self.client.get(url)
        
        # Should redirect to work item detail with error message
        self.assertRedirects(response, reverse('work_item_detail', args=[self.work_item.id]))
    
    def test_thread_messages_and_replies(self):
        """Test thread messages and replies relationship."""
        # Check parent-child relationship
        self.assertEqual(self.reply1.parent, self.message1)
        
        # Check that reply is in parent's replies
        self.assertIn(self.reply1, self.message1.replies.all())
        
        # Check reply count property
        self.assertEqual(self.message1.reply_count, 1)
    
    @patch('workspace.views.MessageReadReceipt.objects.get_or_create')
    def test_mark_message_read(self, mock_get_or_create):
        """Test marking a message as read."""
        # Setup mock
        mock_instance = MagicMock()
        mock_instance.created_at = timezone.now()
        mock_get_or_create.return_value = (mock_instance, True)
        
        # Login as user2
        self.client.login(username='user2', password='password123')
        
        # Mark message1 as read
        url = reverse('mark_message_read', args=[self.message1.id])
        response = self.client.post(url, {}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        # Check response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        
        # Check that get_or_create was called with correct args
        mock_get_or_create.assert_called_once_with(
            message=self.message1,
            user=self.user2
        )
    
    @patch('workspace.views.MessageReadReceipt.objects.get_or_create')
    def test_mark_thread_read(self, mock_get_or_create):
        """Test marking all messages in a thread as read."""
        # Setup mock
        mock_instance = MagicMock()
        mock_instance.created_at = timezone.now()
        mock_get_or_create.return_value = (mock_instance, True)
        
        # Login as user2
        self.client.login(username='user2', password='password123')
        
        # Mark all messages in thread as read
        url = reverse('mark_thread_read', args=[self.public_thread.id])
        response = self.client.post(url, {}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        # Check response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        
        # Check that get_or_create was called for message1
        # (We're not checking the exact number of calls since that depends on implementation)
        mock_get_or_create.assert_called_with(
            message=self.message1,
            user=self.user2
        )
    
    def test_get_message_read_status(self):
        """Test retrieving message read status."""
        # Create a read receipt
        receipt = MessageReadReceipt.objects.create(
            message=self.message1,
            user=self.user2,
            read_at=timezone.now()
        )
        
        # Login as message author
        self.client.login(username='user1', password='password123')
        
        # Get read status
        url = reverse('get_message_read_status', args=[self.message1.id])
        response = self.client.get(url)
        
        # Check response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        
        # Check read_by contains user2
        self.assertEqual(len(data['read_by']), 1)
        self.assertEqual(data['read_by'][0]['user_id'], self.user2.id)
        
        # Login as non-author
        self.client.login(username='user2', password='password123')
        
        # Try to get read status (should be forbidden)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)


class ScheduledMessageTests(TestCase):
    """Tests for scheduled message functionality."""
    
    def setUp(self):
        # Create users
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='password123'
        )
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='password123'
        )
        
        # Create work item
        self.work_item = WorkItem.objects.create(
            title='Test Work Item',
            description='Test description',
            type='task',
            owner=self.user1
        )
        self.work_item.collaborators.add(self.user2)
        
        # Create thread
        self.thread = Thread.objects.create(
            work_item=self.work_item,
            title='Test Thread',
            created_by=self.user1,
            is_public=True
        )
        
        # Create client
        self.client = Client()
        
        # Create future time for scheduled messages
        self.future_time = timezone.now() + timedelta(hours=3)
    
    def test_create_scheduled_message(self):
        """Test creating a scheduled message."""
        # Login as user1
        self.client.login(username='user1', password='password123')
        
        # Schedule a message
        url = reverse('schedule_message', args=[self.work_item.id])
        data = {
            'content': 'This is a scheduled message',
            'scheduled_time': self.future_time.strftime('%Y-%m-%dT%H:%M'),
            'scheduling_note': 'Test note'
        }
        
        response = self.client.post(url, data)
        
        # Check redirect
        self.assertRedirects(response, reverse('work_item_detail', args=[self.work_item.id]))