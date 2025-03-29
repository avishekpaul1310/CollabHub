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
    MessageReadReceipt, NotificationPreference, ThreadGroup
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
        
    def test_update_thread_view(self):
        """Test updating a thread through the view."""
        # Login as thread creator
        self.client.login(username='user1', password='password123')
        
        url = reverse('update_thread', args=[self.work_item.id, self.private_thread.id])
        data = {
            'title': 'Updated Thread',
            'is_public': True,  # Changing from private to public
            'allowed_users': []  # No longer needed as thread becomes public
        }
        
        response = self.client.post(url, data)
        
        # Check that thread was updated
        self.private_thread.refresh_from_db()
        self.assertEqual(self.private_thread.title, 'Updated Thread')
        self.assertTrue(self.private_thread.is_public)
        
        # Check redirect
        self.assertRedirects(response, reverse('thread_detail', args=[self.work_item.id, self.private_thread.id]))
    
    def test_thread_permission_checks(self):
        """Test various thread permission scenarios."""
        # Test that non-creator/non-owner can't update thread
        self.client.login(username='user2', password='password123')
        url = reverse('update_thread', args=[self.work_item.id, self.public_thread.id])
        data = {
            'title': 'Should Not Update',
            'is_public': True
        }
        response = self.client.post(url, data)
        
        # Should redirect with error
        self.assertRedirects(response, reverse('thread_detail', args=[self.work_item.id, self.public_thread.id]))
        
        # Check that thread didn't update
        self.public_thread.refresh_from_db()
        self.assertNotEqual(self.public_thread.title, 'Should Not Update')
        
        # Test that work item owner can update anyone's thread
        self.client.login(username='user1', password='password123')
        
        # Create a thread by user2
        thread = Thread.objects.create(
            work_item=self.work_item,
            title='User2 Thread',
            created_by=self.user2,
            is_public=True
        )
        
        url = reverse('update_thread', args=[self.work_item.id, thread.id])
        data = {
            'title': 'Owner Updated Thread',
            'is_public': True
        }
        response = self.client.post(url, data)
        
        # Should succeed
        thread.refresh_from_db()
        self.assertEqual(thread.title, 'Owner Updated Thread')


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
        
        # Form should show error and not create user
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
    
    def test_other_user_cannot_edit_scheduled_message(self):
        """Test that users cannot edit other users' scheduled messages."""
        # Create scheduled message by user1
        scheduled_msg = ScheduledMessage.objects.create(
            sender=self.user1,
            work_item=self.work_item,
            content='User1 message',
            scheduled_time=self.future_time
        )
        
        # Login as user2
        self.client.login(username='user2', password='password123')
        
        # Try to edit user1's message
        url = reverse('edit_scheduled_message', args=[scheduled_msg.id])
        data = {
            'content': 'Hacked message',
            'scheduled_time': self.future_time.strftime('%Y-%m-%dT%H:%M')
        }
        
        # This should fail or redirect
        response = self.client.post(url, data, follow=True)
        
        # Check that the message was not updated
        scheduled_msg.refresh_from_db()
        self.assertEqual(scheduled_msg.content, 'User1 message')
        self.assertNotEqual(scheduled_msg.content, 'Hacked message')