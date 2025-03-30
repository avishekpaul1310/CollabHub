from django.test import TestCase, Client, TransactionTestCase, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from datetime import timedelta
import datetime
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
from workspace.consumers import ChatConsumer, ThreadConsumer, NotificationConsumer
import workspace.routing


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
        
        # Check thread messages relationship
        self.assertEqual(self.reply1.parent, self.message1)
        self.assertIn(self.reply1, self.message1.replies.all())
        
        # Check reply count property
        self.assertEqual(self.message1.reply_count, 1)
        
    def test_private_thread_unauthorized_access(self):
        """Test that unauthorized users cannot access private threads."""
        # Login as non-allowed user
        self.client.login(username='user3', password='password123')
        
        url = reverse('thread_detail', args=[self.work_item.id, self.private_thread.id])
        response = self.client.get(url)
        
        # Only check if initial URL matches, not the final destination
        self.assertEqual(response.url, reverse('work_item_detail', args=[self.work_item.id]))
    
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


class MessageReadReceiptTests(TestCase):
    """Tests for message read receipts."""
    
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
        
        # Create message
        self.message = Message.objects.create(
            work_item=self.work_item,
            user=self.user1,
            content='Test message'
        )
        
        # Create read receipt
        self.receipt = MessageReadReceipt.objects.create(
            message=self.message,
            user=self.user2,
            read_at=timezone.now()
        )
        
        # Create client and login
        self.client = Client()
        self.client.login(username='user1', password='password123')
    
    def test_mark_message_read_view(self):
        """Test marking a message as read via API."""
        url = reverse('mark_message_read', args=[self.message.id])
        
        # Log in as user2
        self.client.login(username='user2', password='password123')
        
        # Send request
        response = self.client.post(url, {}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        # Check response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        
        # Check that receipt exists (we deleted the previous one)
        self.assertEqual(MessageReadReceipt.objects.filter(message=self.message, user=self.user2).count(), 1)
        
    def test_get_message_read_status(self):
        """Test getting read status of a message."""
        url = reverse('get_message_read_status', args=[self.message.id])
        
        # Send request
        response = self.client.get(url)
        
        # Check response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        
        # Check that read receipts are included
        self.assertEqual(len(data['read_by']), 1)
        self.assertEqual(data['read_by'][0]['username'], self.user2.username)
        
        # Check pending list (empty in this case, user1 is the author)
        self.assertEqual(len(data['pending']), 0)
    
    def test_mark_thread_read(self):
        """Test marking all messages in a thread as read."""
        # Create a thread
        thread = Thread.objects.create(
            work_item=self.work_item,
            title='Test Thread',
            created_by=self.user1,
            is_public=True
        )
        
        # Create messages in thread
        message1 = Message.objects.create(
            work_item=self.work_item,
            thread=thread,
            user=self.user1,
            content='Thread message 1',
            is_thread_starter=True
        )
        
        message2 = Message.objects.create(
            work_item=self.work_item,
            thread=thread,
            user=self.user1,
            content='Thread message 2'
        )
        
        # Log in as user2
        self.client.login(username='user2', password='password123')
        
        # Mark thread as read
        url = reverse('mark_thread_read', args=[thread.id])
        response = self.client.post(url, {}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        # Check response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        
        # Check that receipts were created for both messages
        self.assertTrue(MessageReadReceipt.objects.filter(message=message1, user=self.user2).exists())
        self.assertTrue(MessageReadReceipt.objects.filter(message=message2, user=self.user2).exists())
    
    def test_read_receipt_disabled_by_preference(self):
        """Test that read receipts are not created when disabled in preferences."""
        # Create another message
        message = Message.objects.create(
            work_item=self.work_item,
            user=self.user1,
            content='Another test message'
        )
        
        # Disable read receipts for user2
        prefs = self.user2.notification_preferences
        prefs.share_read_receipts = False
        prefs.save()
        
        # Log in as user2
        self.client.login(username='user2', password='password123')
        
        # Mark message as read
        url = reverse('mark_message_read', args=[message.id])
        response = self.client.post(url, {}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        # Check response
        self.assertEqual(response.status_code, 200)
        
        # No receipt should be created
        self.assertFalse(MessageReadReceipt.objects.filter(message=message, user=self.user2).exists())
    
    def test_non_author_cannot_see_read_status(self):
        """Test that only the message author can see read receipts."""
        # Log in as user2 (not the author)
        self.client.login(username='user2', password='password123')
        
        # Try to get read status
        url = reverse('get_message_read_status', args=[self.message.id])
        response = self.client.get(url)
        
        # Should return forbidden
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
            description='For thoughtful discussions',
            type='reflection',
            work_item=self.work_item,
            created_by=self.user1,
            message_frequency='daily',
            delivery_time=timezone.now().time(),
            min_response_interval=timedelta(hours=4)
        )
        self.slow_channel.participants.add(self.user1, self.user2)
        
        # Create client
        self.client = Client()
    
    def test_slow_channel_creation(self):
        """Test that slow channel can be created with proper attributes."""
        self.assertEqual(self.slow_channel.title, 'Test Slow Channel')
        self.assertEqual(self.slow_channel.work_item, self.work_item)
        self.assertEqual(self.slow_channel.created_by, self.user1)
        self.assertEqual(self.slow_channel.message_frequency, 'daily')
        self.assertEqual(self.slow_channel.min_response_interval, timedelta(hours=4))
        self.assertEqual(self.slow_channel.participants.count(), 2)
    
    def test_create_slow_channel_view(self):
        """Test creating a slow channel through the view."""
        # Login as user1
        self.client.login(username='user1', password='password123')
        
        url = reverse('create_slow_channel', args=[self.work_item.id])
        data = {
            'title': 'New Slow Channel',
            'description': 'A new channel for slow communication',
            'type': 'ideation',
            'message_frequency': 'weekly',
            'delivery_time': '09:00',
            'min_response_interval': '12',  # 12 hours
            'custom_days': ['1', '3', '5'],  # Mon, Wed, Fri
            'participants': [self.user2.id]
        }
        
        response = self.client.post(url, data)
        
        # Check that channel was created
        self.assertTrue(SlowChannel.objects.filter(title='New Slow Channel').exists())
        channel = SlowChannel.objects.get(title='New Slow Channel')
        
        # Check channel details
        self.assertEqual(channel.work_item, self.work_item)
        self.assertEqual(channel.created_by, self.user1)
        self.assertEqual(channel.type, 'ideation')
        self.assertEqual(channel.message_frequency, 'weekly')
        self.assertEqual(channel.min_response_interval, timedelta(hours=12))
        self.assertEqual(channel.custom_days, '135')  # Mon, Wed, Fri
        
        # Check participants (creator is automatically added)
        self.assertIn(self.user1, channel.participants.all())
        self.assertIn(self.user2, channel.participants.all())
        
        # Check redirect
        self.assertRedirects(response, reverse('slow_channel_detail', args=[channel.id]))
    
    def test_slow_channel_detail_view(self):
        """Test the slow channel detail view."""
        # Create a message in the channel
        message = SlowChannelMessage.objects.create(
            channel=self.slow_channel,
            user=self.user1,
            content='Test slow message',
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
        
        # Check that message is in context
        messages_list = response.context['messages']
        self.assertIn(message, messages_list)
    
    def test_slow_channel_message_creation(self):
        """Test creating a message in a slow channel."""
        # Login as participant
        self.client.login(username='user1', password='password123')
        
        url = reverse('slow_channel_detail', args=[self.slow_channel.id])
        data = {
            'content': 'New slow channel message',
            'prompt': ''  # No prompt
        }
        
        response = self.client.post(url, data)
        
        # Check redirect back to channel detail
        self.assertRedirects(response, url)
        
        # Check that message was created
        self.assertTrue(SlowChannelMessage.objects.filter(content='New slow channel message').exists())
        message = SlowChannelMessage.objects.get(content='New slow channel message')
        
        # Check message details
        self.assertEqual(message.channel, self.slow_channel)
        self.assertEqual(message.user, self.user1)
        self.assertFalse(message.is_delivered)  # Should not be delivered yet
        self.assertIsNotNone(message.scheduled_delivery)  # Should have scheduled delivery time
    
    @patch('django.utils.timezone.now')
    def test_min_response_interval_enforcement(self, mock_now):
        """Test that minimum response interval is enforced."""
        # Create a message from user1
        mock_now.return_value = timezone.now()
        message = SlowChannelMessage.objects.create(
            channel=self.slow_channel,
            user=self.user1,
            content='First message',
            is_delivered=True,
            delivered_at=mock_now.return_value
        )
        
        # Login as user1
        self.client.login(username='user1', password='password123')
        
        # Try to post again too soon
        url = reverse('slow_channel_detail', args=[self.slow_channel.id])
        data = {
            'content': 'Second message too soon',
            'prompt': ''
        }
        
        # Mock time to be just after the first message
        mock_now.return_value = timezone.now() + timedelta(hours=1)  # Only 1 hour passed, need 4
        
        # This should show form with error and not create message
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SlowChannelMessage.objects.filter(content='Second message too soon').exists())
        
        # Now try after the interval has passed
        mock_now.return_value = timezone.now() + timedelta(hours=5)  # 5 hours passed, more than 4 required
        
        response = self.client.post(url, data)
        
        # Check redirect
        self.assertRedirects(response, url)
        
        # Check that message was created
        self.assertTrue(SlowChannelMessage.objects.filter(content='Second message too soon').exists())
    
    def test_slow_channel_reply(self):
        """Test replying to a message in a slow channel."""
        # Create a message
        parent_message = SlowChannelMessage.objects.create(
            channel=self.slow_channel,
            user=self.user1,
            content='Parent message',
            is_delivered=True,
            delivered_at=timezone.now() - timedelta(hours=1)
        )
        
        # Login as user2
        self.client.login(username='user2', password='password123')
        
        # Post a reply
        url = reverse('slow_channel_detail', args=[self.slow_channel.id])
        data = {
            'content': 'Reply to parent',
            'parent_id': parent_message.id
        }
        
        response = self.client.post(url, data)
        
        # Check redirect
        self.assertRedirects(response, url)
        
        # Check that reply was created
        self.assertTrue(SlowChannelMessage.objects.filter(content='Reply to parent').exists())
        reply = SlowChannelMessage.objects.get(content='Reply to parent')
        
        # Check reply details
        self.assertEqual(reply.parent, parent_message)
        self.assertEqual(reply.user, self.user2)
    
    def test_non_participant_cannot_access_channel(self):
        """Test that non-participants cannot access a slow channel."""
        # Create a user who is not a participant
        non_participant = User.objects.create_user(
            username='nonparticipant',
            email='non@example.com',
            password='password123'
        )
        
        # Login as non-participant
        self.client.login(username='nonparticipant', password='password123')
        
        # Try to access channel
        url = reverse('slow_channel_detail', args=[self.slow_channel.id])
        response = self.client.get(url)
        
        # Should redirect to work item detail with error
        self.assertRedirects(response, reverse('work_item_detail', args=[self.work_item.id]))
    
    def test_join_leave_slow_channel(self):
        """Test joining and leaving a slow channel."""
        # Create a user who is not a participant but has access to work item
        new_user = User.objects.create_user(
            username='newuser',
            email='new@example.com',
            password='password123'
        )
        self.work_item.collaborators.add(new_user)
        
        # Login as new user
        self.client.login(username='newuser', password='password123')
        
        # Join channel
        url = reverse('join_slow_channel', args=[self.slow_channel.id])
        response = self.client.get(url)
        
        # Check redirect
        self.assertRedirects(response, reverse('slow_channel_detail', args=[self.slow_channel.id]))
        
        # Check that user is now a participant
        self.slow_channel.refresh_from_db()
        self.assertIn(new_user, self.slow_channel.participants.all())
        
        # Leave channel
        url = reverse('leave_slow_channel', args=[self.slow_channel.id])
        response = self.client.get(url)
        
        # Check redirect
        self.assertRedirects(response, reverse('work_item_detail', args=[self.work_item.id]))
        
        # Check that user is no longer a participant
        self.slow_channel.refresh_from_db()
        self.assertNotIn(new_user, self.slow_channel.participants.all())
    
    def test_mark_slow_channel_message_delivered(self):
        """Test marking a slow channel message as delivered."""
        # Create an undelivered message
        message = SlowChannelMessage.objects.create(
            channel=self.slow_channel,
            user=self.user1,
            content='Message to deliver',
            is_delivered=False,
            scheduled_delivery=timezone.now() - timedelta(hours=1)  # Due in the past
        )
        
        # Mark as delivered
        message.mark_delivered()
        
        # Check that message was marked as delivered
        message.refresh_from_db()
        self.assertTrue(message.is_delivered)
        self.assertIsNotNone(message.delivered_at)
    
    def test_get_prompts_list(self):
        """Test getting prompts list from a slow channel."""
        # Add some prompts
        self.slow_channel.reflection_prompts = "What went well?\nWhat could be improved?\nWhat did you learn?"
        self.slow_channel.save()
        
        # Get prompts list
        prompts = self.slow_channel.get_prompts_list()
        
        # Check prompts
        self.assertEqual(len(prompts), 3)
        self.assertIn('What went well?', prompts)
        self.assertIn('What could be improved?', prompts)
        self.assertIn('What did you learn?', prompts)
    
    def test_get_next_delivery_time(self):
        """Test calculating the next delivery time for a slow channel."""
        # Set channel to daily delivery at 9 AM
        self.slow_channel.message_frequency = 'daily'
        self.slow_channel.delivery_time = datetime.time(9, 0)
        self.slow_channel.save()
        
        # Mock current time to be 8 AM
        with patch('django.utils.timezone.now') as mock_now:
            mock_date = timezone.now().replace(hour=8, minute=0)
            mock_now.return_value = mock_date
            
            # Next delivery should be today at 9 AM
            next_delivery = self.slow_channel.get_next_delivery_time()
            self.assertEqual(next_delivery.hour, 9)
            self.assertEqual(next_delivery.minute, 0)
            self.assertEqual(next_delivery.date(), mock_date.date())
        
        # Mock current time to be 10 AM
        with patch('django.utils.timezone.now') as mock_now:
            mock_date = timezone.now().replace(hour=10, minute=0)
            mock_now.return_value = mock_date
            
            # Next delivery should be tomorrow at 9 AM
            next_delivery = self.slow_channel.get_next_delivery_time()
            self.assertEqual(next_delivery.hour, 9)
            self.assertEqual(next_delivery.minute, 0)
            expected_date = (mock_date + timedelta(days=1)).date()
            self.assertEqual(next_delivery.date(), expected_date)


class NotificationTests(TestCase):
    """Tests for notification functionality."""
    
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
        
        # Create notifications
        self.notification1 = Notification.objects.create(
            user=self.user1,
            message='Test notification 1',
            work_item=self.work_item,
            notification_type='message'
        )
        
        self.notification2 = Notification.objects.create(
            user=self.user2,
            message='Test notification 2',
            work_item=self.work_item,
            notification_type='update'
        )
        
        # Create client
        self.client = Client()
    
    @patch('workspace.signals.send_notification')
    def test_message_notification_creation(self, mock_send):
        """Test that a notification is created when a message is created."""
        # Create a message
        message = Message.objects.create(
            work_item=self.work_item,
            user=self.user1,
            content='Test message'
        )
        
        # Check that send_notification was called
        self.assertTrue(mock_send.called)
        
        # Check that notification was created for owner
        notifications = Notification.objects.filter(
            user=self.user1,
            work_item=self.work_item,
            notification_type='message'
        )
        self.assertTrue(notifications.exists())
    
    @patch('workspace.signals.send_notification')
    def test_file_upload_notification(self, mock_send):
        """Test that a notification is created when a file is uploaded."""
        # Create a file upload
        file_content = b'test file content'
        test_file = SimpleUploadedFile('test_file.txt', file_content, content_type='text/plain')
        
        file_attachment = FileAttachment.objects.create(
            work_item=self.work_item,
            file=test_file,
            name='test_file.txt',
            uploaded_by=self.user2
        )
        
        # Check that send_notification was called
        self.assertTrue(mock_send.called)
    
    def test_notification_should_notify_based_on_dnd(self):
        """Test that notifications respect DND settings."""
        # Set up user preferences
        prefs = self.user1.notification_preferences
        prefs.dnd_enabled = True
        prefs.dnd_start_time = timezone.now().time()  # Current time
        prefs.dnd_end_time = (timezone.now() + timedelta(hours=2)).time()  # 2 hours from now
        prefs.save()
        
        # Should not notify during DND
        self.assertFalse(prefs.should_notify())
    
    def test_notification_should_notify_based_on_mute(self):
        """Test that notifications respect muted work items."""
        # Mute the work item
        prefs = self.user1.notification_preferences
        prefs.muted_channels.add(self.work_item)
        
        # Should not notify for muted work item
        self.assertFalse(prefs.should_notify(self.work_item))
    
    def test_mark_notification_read_on_work_item_visit(self):
        """Test that notifications are marked as read when visiting the work item."""
        # Create unread notifications
        notification = Notification.objects.create(
            user=self.user1,
            message='Test notification for auto-read',
            work_item=self.work_item,
            notification_type='message',
            is_read=False
        )
        
        # Login as user1
        self.client.login(username='user1', password='password123')
        
        # Visit work item detail
        url = reverse('work_item_detail', args=[self.work_item.id])
        response = self.client.get(url)
        
        # Check that notification was marked as read
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
    
    def test_notification_preference_creation(self):
        """Test that notification preferences are created for a new user."""
        # Create a new user
        new_user = User.objects.create_user(
            username='newuser',
            email='new@example.com',
            password='password123'
        )
        
        # Check that preferences were created
        self.assertTrue(hasattr(new_user, 'notification_preferences'))
        self.assertIsInstance(new_user.notification_preferences, NotificationPreference)


class WebSocketTests(TransactionTestCase):
    """Tests for WebSocket consumers."""
    
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
    
    @patch('workspace.consumers.database_sync_to_async')
    async def test_chat_consumer_connect(self, mock_sync_to_async):
        """Test ChatConsumer connection."""
        # Create application
        application = URLRouter(workspace.routing.websocket_urlpatterns)
        
        # Connect to WebSocket
        communicator = WebsocketCommunicator(application, f'/ws/chat/{self.work_item.id}/')
        
        # Add user to scope
        communicator.scope['user'] = self.user1
        
        connected, subprotocol = await communicator.connect()
        
        # Check connection successful
        self.assertTrue(connected)
        
        # Close
        await communicator.disconnect()
    
    @patch('workspace.consumers.ChatConsumer.channel_layer.group_send')
    @patch('workspace.consumers.database_sync_to_async')
    async def test_chat_consumer_receive(self, mock_sync_to_async, mock_group_send):
        """Test ChatConsumer message handling."""
        # Set up mock
        mock_message = MagicMock()
        mock_message.id = 1
        mock_message.created_at = timezone.now()
        mock_sync_to_async.return_value.return_value = mock_message
        
        # Create application
        application = URLRouter(workspace.routing.websocket_urlpatterns)
        
        # Connect to WebSocket
        communicator = WebsocketCommunicator(application, f'/ws/chat/{self.work_item.id}/')
        
        # Add user to scope
        communicator.scope['user'] = self.user1
        
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)
        
        # Send message
        message_data = {
            'message': 'Test WebSocket message',
            'user_id': self.user1.id,
            'username': self.user1.username
        }
        await communicator.send_json_to(message_data)
        
        # Check that group_send was called
        self.assertTrue(mock_group_send.called)
        
        # Close
        await communicator.disconnect()
    
    @patch('workspace.consumers.ThreadConsumer.channel_layer.group_send')
    @patch('workspace.consumers.database_sync_to_async')
    async def test_thread_consumer_receive(self, mock_sync_to_async, mock_group_send):
        """Test ThreadConsumer message handling."""
        # Set up mocks
        mock_check_access = MagicMock(return_value=True)
        mock_sync_to_async.return_value = mock_check_access
        
        # Create application
        application = URLRouter(workspace.routing.websocket_urlpatterns)
        
        # Connect to WebSocket
        communicator = WebsocketCommunicator(application, f'/ws/thread/{self.thread.id}/')
        
        # Add user to scope
        communicator.scope['user'] = self.user1
        
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)
        
        # Send message
        message_data = {
            'message': 'Test thread message',
            'user_id': self.user1.id,
            'thread_id': self.thread.id
        }
        await communicator.send_json_to(message_data)
        
        # Check that group_send was called
        self.assertTrue(mock_group_send.called)
        
        # Close
        await communicator.disconnect()
    
    @patch('workspace.consumers.NotificationConsumer.channel_layer.group_send')
    async def test_notification_consumer_connect(self, mock_group_send):
        """Test NotificationConsumer connection."""
        # Create application
        application = URLRouter(workspace.routing.websocket_urlpatterns)
        
        # Connect to WebSocket
        communicator = WebsocketCommunicator(application, '/ws/notifications/')
        
        # Add user to scope
        communicator.scope['user'] = self.user1
        
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)
        
        # Close
        await communicator.disconnect()


class ManagementCommandTests(TestCase):
    """Tests for management commands."""
    
    def setUp(self):
        # Create users
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='password123'
        )
        
        # Create work item
        self.work_item = WorkItem.objects.create(
            title='Test Work Item',
            description='Test description',
            type='task',
            owner=self.user1
        )
        
        # Create scheduled message due now
        self.due_message = ScheduledMessage.objects.create(
            sender=self.user1,
            work_item=self.work_item,
            content='Due scheduled message',
            scheduled_time=timezone.now() - timedelta(minutes=5),
            is_sent=False
        )
        
        # Create future scheduled message
        self.future_message = ScheduledMessage.objects.create(
            sender=self.user1,
            work_item=self.work_item,
            content='Future scheduled message',
            scheduled_time=timezone.now() + timedelta(hours=1),
            is_sent=False
        )
        
        # Create slow channel
        self.slow_channel = SlowChannel.objects.create(
            title='Test Slow Channel',
            description='For testing',
            type='reflection',
            work_item=self.work_item,
            created_by=self.user1,
            message_frequency='daily',
            delivery_time=timezone.now().time()
        )
        self.slow_channel.participants.add(self.user1)
        
        # Create slow channel message due now
        self.due_slow_message = SlowChannelMessage.objects.create(
            channel=self.slow_channel,
            user=self.user1,
            content='Due slow message',
            scheduled_delivery=timezone.now() - timedelta(minutes=5),
            is_delivered=False
        )
    
    @patch('workspace.models.ScheduledMessage.send')
    def test_send_scheduled_messages_command(self, mock_send):
        """Test send_scheduled_messages management command."""
        # Setup mock to return True
        mock_send.return_value = True
        
        from django.core.management import call_command
        from io import StringIO
        
        # Call command with redirected stdout
        out = StringIO()
        call_command('send_scheduled_messages', stdout=out)
        
        # Check output
        output = out.getvalue()
        self.assertIn('Found 1 scheduled messages to send', output)
        self.assertIn('sent successfully', output)
        
        # Check that only due message was processed
        mock_send.assert_called_once()
        
        # Check that it was called on the due message
        self.assertEqual(mock_send.call_args[0][0], self.due_message)
    
    @patch('workspace.models.SlowChannelMessage.mark_delivered')
    def test_deliver_slow_channel_messages_command(self, mock_mark_delivered):
        """Test deliver_slow_channel_messages management command."""
        from django.core.management import call_command
        from io import StringIO
        
        # Call command with redirected stdout
        out = StringIO()
        call_command('deliver_slow_channel_messages', stdout=out)
        
        # Check output
        output = out.getvalue()
        self.assertIn('Found 1 slow channel messages to deliver', output)
        
        # Check that mark_delivered was called
        mock_mark_delivered.assert_called_once()


class ContextProcessorTests(TestCase):
    """Tests for context processors."""
    
    def setUp(self):
        # Create a user with notifications
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        
        # Create a work item
        self.work_item = WorkItem.objects.create(
            title='Test Work Item',
            description='Test description',
            type='task',
            owner=self.user
        )
        
        # Create unread notifications
        for i in range(3):
            Notification.objects.create(
                user=self.user,
                message=f'Test notification {i}',
                work_item=self.work_item,
                notification_type='message',
                is_read=False
            )
        
        # Create read notification
        Notification.objects.create(
            user=self.user,
            message='Read notification',
            work_item=self.work_item,
            notification_type='message',
            is_read=True
        )
        
        # Create client
        self.client = Client()
    
    def test_notifications_processor(self):
        """Test the notifications context processor."""
        # Login
        self.client.login(username='testuser', password='password123')
        
        # Get a page
        response = self.client.get(reverse('dashboard'))
        
        # Check that unread notifications count is in context
        self.assertEqual(response.context['unread_notifications_count'], 3)
    
    def test_notifications_processor_unauthenticated(self):
        """Test the notifications processor for unauthenticated users."""
        # Get a page without logging in
        response = self.client.get(reverse('login'))
        
        # Check that unread notifications count is 0
        self.assertEqual(response.context['unread_notifications_count'], 0)