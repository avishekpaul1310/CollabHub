from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse, re_path
from django.test import Client

from workspace.models import WorkItem, Message, FileAttachment, Notification

# Integrate these tests with your existing ones or replace fully as needed

class WorkItemModelTest(TestCase):
    """Tests for the WorkItem model."""
    
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@example.com', 'password123')
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
        self.assertEqual(self.work_item.type, 'task')
        self.assertTrue(self.work_item.created_at)
    
    def test_work_item_string_representation(self):
        """Test the string representation of a work item."""
        self.assertEqual(str(self.work_item), 'Test Item')


class MessageModelTest(TestCase):
    """Tests for the Message model."""
    
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@example.com', 'password123')
        self.work_item = WorkItem.objects.create(
            title='Test Item',
            description='Test description',
            type='task',
            owner=self.user
        )
        self.message = Message.objects.create(
            work_item=self.work_item,
            user=self.user,
            content='Test message content'
        )
    
    def test_message_creation(self):
        """Test creating a message."""
        self.assertEqual(self.message.content, 'Test message content')
        self.assertEqual(self.message.user, self.user)
        self.assertEqual(self.message.work_item, self.work_item)
        self.assertTrue(self.message.created_at)
    
    def test_message_string_representation(self):
        """Test the string representation of a message."""
        self.assertEqual(str(self.message), 'testuser: Test message co')


class NotificationModelTest(TestCase):
    """Tests for the Notification model."""
    
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@example.com', 'password123')
        self.work_item = WorkItem.objects.create(
            title='Test Item',
            description='Test description',
            type='task',
            owner=self.user
        )
        self.notification = Notification.objects.create(
            user=self.user,
            message='Test notification message',
            work_item=self.work_item,
            notification_type='message'
        )
    
    def test_notification_creation(self):
        """Test creating a notification."""
        self.assertEqual(self.notification.message, 'Test notification message')
        self.assertEqual(self.notification.user, self.user)
        self.assertEqual(self.notification.work_item, self.work_item)
        self.assertEqual(self.notification.notification_type, 'message')
        self.assertFalse(self.notification.is_read)
    
    def test_notification_mark_as_read(self):
        """Test marking a notification as read."""
        self.notification.is_read = True
        self.notification.save()
        
        # Refresh from DB
        self.notification.refresh_from_db()
        self.assertTrue(self.notification.is_read)
    
    def test_notification_string_representation(self):
        """Test the string representation of a notification."""
        self.assertEqual(str(self.notification), 'Notification for testuser: Test notification message')


class FileAttachmentModelTest(TestCase):
    """Tests for the FileAttachment model."""
    
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@example.com', 'password123')
        self.work_item = WorkItem.objects.create(
            title='Test Item',
            description='Test description',
            type='task',
            owner=self.user
        )
    
    def test_file_upload(self):
        """Test uploading a file via view."""
        # Login the user
        self.client.login(username='testuser', password='password123')
        
        # Use an existing file from the project for testing
        with open('manage.py', 'rb') as file:
            response = self.client.post(
                reverse('upload_file', args=[self.work_item.id]),
                {'file': file}
            )
        
        # Check redirect
        self.assertRedirects(response, reverse('work_item_detail', args=[self.work_item.id]))
        
        # Check file was created
        self.assertTrue(FileAttachment.objects.filter(work_item=self.work_item).exists())
        attachment = FileAttachment.objects.get(work_item=self.work_item)
        self.assertEqual(attachment.name, 'manage.py')
        self.assertEqual(attachment.uploaded_by, self.user)


class WorkItemViewsTest(TestCase):
    """Tests for the work item views."""
    
    def setUp(self):
        # Create a user and log them in
        self.user = User.objects.create_user('testuser', 'test@example.com', 'password123')
        self.client.login(username='testuser', password='password123')
        
        # Create a work item
        self.work_item = WorkItem.objects.create(
            title='Test Item',
            description='Test description',
            type='task',
            owner=self.user
        )
    
    def test_dashboard_view(self):
        """Test the dashboard view."""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'workspace/dashboard.html')
        self.assertIn(self.work_item, response.context['work_item'])
    
    def test_work_item_detail_view(self):
        """Test the work item detail view."""
        response = self.client.get(reverse('work_item_detail', args=[self.work_item.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'workspace/work_item_detail.html')
        self.assertEqual(response.context['work_item'], self.work_item)
    
    def test_create_work_item_view(self):
        """Test creating a work item through the view."""
        response = self.client.post(
            reverse('create_work_item'),
            {
                'title': 'New Test Item',
                'description': 'New test description',
                'type': 'doc'
            }
        )
        
        # Check the item was created
        self.assertTrue(WorkItem.objects.filter(title='New Test Item').exists())
        
        # Get the created item
        new_item = WorkItem.objects.get(title='New Test Item')
        
        # Check redirect to detail view
        self.assertRedirects(response, reverse('work_item_detail', args=[new_item.id]))
    
    def test_update_work_item_view(self):
        """Test updating a work item through the view."""
        response = self.client.post(
            reverse('update_work_item', args=[self.work_item.id]),
            {
                'title': 'Updated Test Item',
                'description': 'Updated test description',
                'type': 'project'
            }
        )
        
        # Refresh from DB
        self.work_item.refresh_from_db()
        
        # Check the item was updated
        self.assertEqual(self.work_item.title, 'Updated Test Item')
        self.assertEqual(self.work_item.description, 'Updated test description')
        self.assertEqual(self.work_item.type, 'project')
        
        # Check redirect to detail view
        self.assertRedirects(response, reverse('work_item_detail', args=[self.work_item.id]))
    
    def test_delete_work_item_view(self):
        """Test deleting a work item through the view."""
        response = self.client.post(reverse('delete_work_item', args=[self.work_item.id]))
        
        # Check the item was deleted
        self.assertFalse(WorkItem.objects.filter(id=self.work_item.id).exists())
        
        # Check redirect to dashboard
        self.assertRedirects(response, reverse('dashboard'))


class NotificationViewsTest(TestCase):
    """Tests for notification-related views."""
    
    def setUp(self):
        # Create a user and log them in
        self.user = User.objects.create_user('testuser', 'test@example.com', 'password123')
        self.client.login(username='testuser', password='password123')
        
        # Create a work item
        self.work_item = WorkItem.objects.create(
            title='Test Item',
            description='Test description',
            type='task',
            owner=self.user
        )
        
        # Create some notifications
        self.notification1 = Notification.objects.create(
            user=self.user,
            message='Test notification 1',
            work_item=self.work_item,
            notification_type='message'
        )
        
        self.notification2 = Notification.objects.create(
            user=self.user,
            message='Test notification 2',
            work_item=self.work_item,
            notification_type='update'
        )
    
    def test_notifications_list_view(self):
        """Test the notifications list view."""
        response = self.client.get(reverse('notifications_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'workspace/notifications_list.html')
        self.assertIn(self.notification1, response.context['notifications'])
        self.assertIn(self.notification2, response.context['notifications'])
        self.assertEqual(response.context['unread_count'], 2)
    
    def test_mark_notification_read_view(self):
        """Test marking a notification as read."""
        response = self.client.get(reverse('mark_notification_read', args=[self.notification1.id]))
        
        # Refresh from DB
        self.notification1.refresh_from_db()
        
        # Check the notification was marked as read
        self.assertTrue(self.notification1.is_read)
        
        # Check redirect
        self.assertRedirects(response, reverse('notifications_list'))
    
    def test_mark_all_read_view(self):
        """Test marking all notifications as read."""
        response = self.client.get(reverse('mark_all_read'))
        
        # Refresh from DB
        self.notification1.refresh_from_db()
        self.notification2.refresh_from_db()
        
        # Check both notifications were marked as read
        self.assertTrue(self.notification1.is_read)
        self.assertTrue(self.notification2.is_read)
        
        # Check redirect
        self.assertRedirects(response, reverse('notifications_list'))

# Note: A separate testing approach for WebSocket functionality:
# 
# Testing WebSockets properly requires setting up a more complex environment 
# with proper database configuration. For simple projects, consider these alternatives:
#
# 1. Manually test WebSocket functionality in the application
# 2. Test the consumer methods directly without using WebSocket connections
# 3. Set up a separate test configuration with a PostgreSQL database
#
# Example consumer method test (NOT an integration test):
#
# def test_chat_consumer_save_message():
#     user = User.objects.create_user('testuser', 'test@example.com', 'password123')
#     work_item = WorkItem.objects.create(title='Test', type='task', owner=user)
#     
#     # Directly call the method we want to test
#     from workspace.consumers import ChatConsumer
#     consumer = ChatConsumer()
#     consumer.work_item_id = work_item.id
#     # Call the method directly or test helper methods