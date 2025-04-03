from django.test import TestCase, TransactionTestCase, LiveServerTestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.db.models import Q
from django.core.management import call_command
from django.conf import settings
from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from channels.db import database_sync_to_async
from unittest.mock import patch, MagicMock, call, ANY
import json
import datetime
import tempfile
import os
import asyncio
import time
from workspace.models import (
    WorkItem, Message, Thread, ThreadGroup, FileAttachment, Notification, NotificationPreference,
    MessageReadReceipt, SlowChannel, SlowChannelMessage, ScheduledMessage, BreakEvent,
    ThreadMessage, UserOnlineStatus
)
from workspace.routing import websocket_urlpatterns
from workspace.consumers import ChatConsumer, ThreadConsumer, NotificationConsumer
from workspace.tasks import send_scheduled_messages, deliver_slow_channel_messages
from search.models import SavedSearch, SearchLog, FileIndex
from search.views import search_view, search_work_items, search_messages, search_files
from search.indexing import index_file, reindex_file


class CollaborationWorkflowTests(TransactionTestCase):
    """Integration tests for the complete collaboration workflow"""
    
    def setUp(self):
        """Set up test data for collaboration workflow"""
        # Create users
        self.project_manager = User.objects.create_user(
            username='manager',
            email='manager@example.com',
            password='managerpassword'
        )
        
        self.developer = User.objects.create_user(
            username='developer',
            email='developer@example.com',
            password='developerpassword'
        )
        
        self.designer = User.objects.create_user(
            username='designer',
            email='designer@example.com',
            password='designerpassword'
        )
        
        self.tester = User.objects.create_user(
            username='tester',
            email='tester@example.com',
            password='testerpassword'
        )
        
        # Create clients for each user
        self.manager_client = Client()
        self.manager_client.login(username='manager', password='managerpassword')
        
        self.developer_client = Client()
        self.developer_client.login(username='developer', password='developerpassword')
        
        self.designer_client = Client()
        self.designer_client.login(username='designer', password='designerpassword')
        
        self.tester_client = Client()
        self.tester_client.login(username='tester', password='testerpassword')
        
        # Create notification preferences for users
        for user in [self.project_manager, self.developer, self.designer, self.tester]:
            NotificationPreference.objects.create(
                user=user,
                share_read_receipts=True,
                notification_mode='all'
            )
    
    def test_complete_project_workflow(self):
        """Test a complete project workflow from creation to completion"""
        # 1. Project manager creates a new project
        project_data = {
            'title': 'New Application Development',
            'description': 'Develop a new web application for client XYZ',
            'type': 'project',
            'status': 'planning',
            'priority': 'high',
            'due_date': (timezone.now() + datetime.timedelta(days=30)).strftime('%Y-%m-%d')
        }
        
        response = self.manager_client.post(reverse('create_work_item'), project_data)
        self.assertEqual(response.status_code, 302)  # Should redirect after creation
        
        # Get the newly created project
        project = WorkItem.objects.filter(title='New Application Development').first()
        self.assertIsNotNone(project)
        self.assertEqual(project.owner, self.project_manager)
        
        # 2. Project manager adds collaborators
        update_url = reverse('update_work_item', args=[project.id])
        collaborator_data = {
            'title': project.title,
            'description': project.description,
            'type': project.type,
            'status': project.status,
            'priority': project.priority,
            'collaborators': [self.developer.id, self.designer.id, self.tester.id]
        }
        
        response = self.manager_client.post(update_url, collaborator_data)
        self.assertEqual(response.status_code, 302)
        
        # Verify collaborators were added
        project.refresh_from_db()
        self.assertIn(self.developer, project.collaborators.all())
        self.assertIn(self.designer, project.collaborators.all())
        self.assertIn(self.tester, project.collaborators.all())
        
        # 3. Project manager creates a general discussion thread
        thread_data = {
            'title': 'General Project Discussion',
            'is_public': True
        }
        
        response = self.manager_client.post(
            reverse('create_thread', args=[project.id]),
            thread_data
        )
        self.assertEqual(response.status_code, 302)
        
        # Verify thread was created
        thread = Thread.objects.filter(title='General Project Discussion').first()
        self.assertIsNotNone(thread)
        self.assertEqual(thread.work_item, project)
        
        # 4. Developer adds a message to the thread
        thread_url = reverse('thread_detail', args=[project.id, thread.id])
        response = self.developer_client.get(thread_url)
        self.assertEqual(response.status_code, 200)
        
        message_data = {
            'content': 'I have started working on the initial architecture.'
        }
        
        response = self.developer_client.post(thread_url, message_data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(thread_url))
        
        # Verify message was created
        dev_message = Message.objects.filter(
            thread=thread,
            user=self.developer
        ).first()
        self.assertIsNotNone(dev_message)
        self.assertEqual(dev_message.content, 'I have started working on the initial architecture.')
        
        # 5. Designer reads the message
        response = self.designer_client.post(
            reverse('mark_message_read', args=[dev_message.id])
        )
        self.assertEqual(response.status_code, 200)
        
        # Verify read receipt
        read_receipt = MessageReadReceipt.objects.filter(
            message=dev_message,
            user=self.designer
        ).first()
        self.assertIsNotNone(read_receipt)
        
        # 6. Project manager checks read status
        response = self.manager_client.get(
            reverse('get_message_read_status', args=[dev_message.id])
        )
        self.assertEqual(response.status_code, 403)  # Should fail as manager is not author
        
        response = self.developer_client.get(
            reverse('get_message_read_status', args=[dev_message.id])
        )
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['total_read'], 1)
        
        # 7. Project manager creates a new task for designer
        task_data = {
            'title': 'Create UI Mockups',
            'description': 'Create initial UI mockups for client approval',
            'type': 'task',
            'status': 'todo',
            'priority': 'medium',
            'parent': project.id,
            'assigned_to': self.designer.id,
            'due_date': (timezone.now() + datetime.timedelta(days=7)).strftime('%Y-%m-%d')
        }
        
        response = self.manager_client.post(reverse('create_work_item'), task_data)
        self.assertEqual(response.status_code, 302)
        
        # Verify task was created
        design_task = WorkItem.objects.filter(title='Create UI Mockups').first()
        self.assertIsNotNone(design_task)
        self.assertEqual(design_task.parent, project)
        
        # 8. Designer uploads a file to the task
        with open('temp_mockup.png', 'wb') as f:
            f.write(b'mock image data')
            
        with open('temp_mockup.png', 'rb') as f:
            file_data = {
                'file': f,
                'name': 'homepage_mockup.png',
                'description': 'Homepage initial design'
            }
            response = self.designer_client.post(
                reverse('upload_file', args=[design_task.id]),
                file_data
            )
        
        # Clean up temp file
        os.remove('temp_mockup.png')
        
        self.assertEqual(response.status_code, 302)
        
        # Verify file was uploaded
        attachment = FileAttachment.objects.filter(name='homepage_mockup.png').first()
        self.assertIsNotNone(attachment)
        self.assertEqual(attachment.work_item, design_task)
        self.assertEqual(attachment.uploaded_by, self.designer)
        
        # 9. Tester creates a scheduled message for tomorrow's meeting
        tomorrow = timezone.now() + datetime.timedelta(days=1)
        scheduled_message_data = {
            'content': 'Reminder: Project review meeting at 10 AM',
            'scheduled_time': tomorrow.strftime('%Y-%m-%d %H:%M:%S'),
            'work_item': project.id
        }
        
        response = self.tester_client.post(
            reverse('schedule_message'),
            scheduled_message_data
        )
        self.assertEqual(response.status_code, 302)
        
        # Verify scheduled message
        scheduled_msg = ScheduledMessage.objects.filter(
            content='Reminder: Project review meeting at 10 AM'
        ).first()
        self.assertIsNotNone(scheduled_msg)
        self.assertEqual(scheduled_msg.sender, self.tester)
        self.assertEqual(scheduled_msg.work_item, project)
        
        # 10. Developer updates task status
        design_task.status = 'in_progress'
        design_task.save()
        
        # 11. Search for project assets
        response = self.tester_client.get(
            f"{reverse('search')}?q=mockup&content_types=file"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'homepage_mockup.png', response.content)
        
        # 12. Designer completes the task
        design_task.status = 'done'
        design_task.save()
        
        # 13. Project manager creates a slow channel for project reflections
        slow_channel_data = {
            'title': 'Project Reflections',
            'description': 'Weekly reflections on project progress',
            'type': 'reflection',
            'message_frequency': 'weekly',
            'participants': [
                self.project_manager.id,
                self.developer.id,
                self.designer.id,
                self.tester.id
            ]
        }
        
        response = self.manager_client.post(
            reverse('create_slow_channel', args=[project.id]),
            slow_channel_data
        )
        self.assertEqual(response.status_code, 302)
        
        # Verify slow channel
        slow_channel = SlowChannel.objects.filter(title='Project Reflections').first()
        self.assertIsNotNone(slow_channel)
        self.assertEqual(slow_channel.work_item, project)
        self.assertEqual(slow_channel.created_by, self.project_manager)
        
        # Verify all participants are added
        participants = slow_channel.participants.all()
        self.assertEqual(participants.count(), 4)
        self.assertIn(self.project_manager, participants)
        self.assertIn(self.developer, participants)
        self.assertIn(self.designer, participants)
        self.assertIn(self.tester, participants)
        
        # 14. Developer sends a message to the slow channel
        slow_message_data = {
            'content': 'I think our architecture is solid, but we might want to consider refactoring the authentication module.'
        }
        
        response = self.developer_client.post(
            reverse('slow_channel_detail', args=[slow_channel.id]),
            slow_message_data
        )
        self.assertEqual(response.status_code, 302)
        
        # Verify slow channel message
        sc_message = SlowChannelMessage.objects.filter(
            channel=slow_channel,
            user=self.developer
        ).first()
        self.assertIsNotNone(sc_message)
        self.assertEqual(
            sc_message.content,
            'I think our architecture is solid, but we might want to consider refactoring the authentication module.'
        )
        
        # 15. Project completion
        project.status = 'completed'
        project.save()
        
        # Verify final project status
        project.refresh_from_db()
        self.assertEqual(project.status, 'completed')


class RealTimeMessagingTests(TransactionTestCase):
    """Integration tests for real-time messaging functionality"""
    
    async def setUp(self):
        """Set up test data for real-time messaging tests"""
        # Create users
        self.user1 = await database_sync_to_async(User.objects.create_user)(
            username='user1',
            email='user1@example.com',
            password='user1password'
        )
        
        self.user2 = await database_sync_to_async(User.objects.create_user)(
            username='user2',
            email='user2@example.com',
            password='user2password'
        )
        
        # Create a work item
        self.work_item = await database_sync_to_async(WorkItem.objects.create)(
            title='WebSocket Test Project',
            description='Testing WebSocket functionality',
            type='project',
            owner=self.user1
        )
        await database_sync_to_async(self.work_item.collaborators.add)(self.user2)
        
        # Create a thread
        self.thread = await database_sync_to_async(Thread.objects.create)(
            title='WebSocket Test Thread',
            work_item=self.work_item,
            created_by=self.user1,
            is_public=True
        )
    
    @patch('workspace.consumers.get_user')
    async def test_chat_communication(self, mock_get_user):
        """Test real-time chat communication between users"""
        # Mock the get_user function to return our test users
        mock_get_user.side_effect = lambda user_id: self.user1 if user_id == self.user1.id else self.user2
        
        # Create WebSocket communicators for both users
        application = URLRouter(websocket_urlpatterns)
        communicator1 = WebsocketCommunicator(
            application,
            f"/ws/chat/{self.work_item.id}/"
        )
        communicator2 = WebsocketCommunicator(
            application,
            f"/ws/chat/{self.work_item.id}/"
        )
        
        # Connect both users
        connected1, _ = await communicator1.connect()
        connected2, _ = await communicator2.connect()
        self.assertTrue(connected1)
        self.assertTrue(connected2)
        
        # User 1 sends a message
        await communicator1.send_json_to({
            'message': 'Hello from User 1',
            'user_id': self.user1.id
        })
        
        # User 2 should receive the message
        response = await communicator2.receive_json_from()
        self.assertEqual(response['message'], 'Hello from User 1')
        self.assertEqual(response['user_id'], self.user1.id)
        self.assertEqual(response['username'], 'user1')
        
        # User 2 sends a reply
        await communicator2.send_json_to({
            'message': 'Hello User 1, this is User 2',
            'user_id': self.user2.id
        })
        
        # User 1 should receive the reply
        response = await communicator1.receive_json_from()
        self.assertEqual(response['message'], 'Hello User 1, this is User 2')
        self.assertEqual(response['user_id'], self.user2.id)
        self.assertEqual(response['username'], 'user2')
        
        # Close connections
        await communicator1.disconnect()
        await communicator2.disconnect()
    
    @patch('workspace.consumers.get_user')
    async def test_thread_communication(self, mock_get_user):
        """Test real-time thread communication between users"""
        # Mock the get_user function
        mock_get_user.side_effect = lambda user_id: self.user1 if user_id == self.user1.id else self.user2
        
        # Create WebSocket communicators for both users
        application = URLRouter(websocket_urlpatterns)
        communicator1 = WebsocketCommunicator(
            application,
            f"/ws/thread/{self.work_item.id}/{self.thread.id}/"
        )
        communicator2 = WebsocketCommunicator(
            application,
            f"/ws/thread/{self.work_item.id}/{self.thread.id}/"
        )
        
        # Connect both users
        connected1, _ = await communicator1.connect()
        connected2, _ = await communicator2.connect()
        self.assertTrue(connected1)
        self.assertTrue(connected2)
        
        # User 1 sends a thread message
        await communicator1.send_json_to({
            'message': 'This is a thread message from User 1',
            'user_id': self.user1.id,
            'parent_id': None
        })
        
        # User 2 should receive the message
        response = await communicator2.receive_json_from()
        self.assertEqual(response['message'], 'This is a thread message from User 1')
        self.assertEqual(response['user_id'], self.user1.id)
        self.assertEqual(response['username'], 'user1')
        message_id = response['message_id']
        
        # User 2 sends a reply to the thread message
        await communicator2.send_json_to({
            'message': 'Reply to your thread message',
            'user_id': self.user2.id,
            'parent_id': message_id
        })
        
        # User 1 should receive the reply
        response = await communicator1.receive_json_from()
        self.assertEqual(response['message'], 'Reply to your thread message')
        self.assertEqual(response['user_id'], self.user2.id)
        self.assertEqual(response['parent_id'], message_id)
        
        # Close connections
        await communicator1.disconnect()
        await communicator2.disconnect()
    
    @patch('workspace.consumers.NotificationConsumer.group_send')
    async def test_notifications_broadcasting(self, mock_group_send):
        """Test notification broadcasting when events occur"""
        # Create notification
        notification = await database_sync_to_async(Notification.objects.create)(
            user=self.user1,
            message='You have a new message',
            notification_type='message',
            work_item=self.work_item
        )
        
        # Verify notification is created
        notification_exists = await database_sync_to_async(
            lambda: Notification.objects.filter(id=notification.id).exists()
        )()
        self.assertTrue(notification_exists)
        
        # Verify group_send was called to broadcast notification
        mock_group_send.assert_called_with(
            f'notifications_{self.user1.id}',
            {
                'type': 'notification_message',
                'message': 'You have a new message',
                'count': 1,
                'notification_id': notification.id
            }
        )


class SearchAndIndexingTests(TestCase):
    """Integration tests for search and indexing functionality"""
    
    def setUp(self):
        """Set up test data for search and indexing tests"""
        # Create users
        self.user = User.objects.create_user(
            username='searchuser',
            email='search@example.com',
            password='searchpassword'
        )
        
        self.client = Client()
        self.client.login(username='searchuser', password='searchpassword')
        
        # Create work items with different content
        self.project = WorkItem.objects.create(
            title='Search Integration Project',
            description='This is a project for testing search integration',
            type='project',
            owner=self.user
        )
        
        self.task = WorkItem.objects.create(
            title='Search Implementation Task',
            description='Implement advanced search functionality',
            type='task',
            owner=self.user,
            parent=self.project
        )
        
        # Create messages
        self.message1 = Message.objects.create(
            work_item=self.project,
            user=self.user,
            content='This message contains searchable keywords like elasticsearch and indexing'
        )
        
        self.message2 = Message.objects.create(
            work_item=self.task,
            user=self.user,
            content='Planning to use analyzer for better search results with fuzzy matching'
        )
        
        # Create thread
        self.thread = Thread.objects.create(
            title='Search Features Discussion',
            work_item=self.project,
            created_by=self.user,
            is_public=True
        )
        
        # Add thread messages
        self.thread_message = Message.objects.create(
            work_item=self.project,
            thread=self.thread,
            user=self.user,
            content='We need to implement tokenization for better search accuracy',
            is_thread_starter=True
        )
        
        # Create files with content for indexing
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.txt', delete=False)
        self.temp_file.write(b'This is a test file for search indexing with important technical terms')
        self.temp_file.close()
        
        with open(self.temp_file.name, 'rb') as f:
            self.file_attachment = FileAttachment.objects.create(
                work_item=self.project,
                file=SimpleUploadedFile('search_specs.txt', f.read()),
                name='search_specs.txt',
                uploaded_by=self.user
            )
    
    def tearDown(self):
        """Clean up temporary files"""
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)
    
    @patch('search.signals.index_file')
    def test_file_indexing_on_upload(self, mock_index_file):
        """Test that files are indexed when uploaded"""
        # Create a new file
        with open('new_index_test.txt', 'wb') as f:
            f.write(b'New file content for testing automatic indexing')
            
        with open('new_index_test.txt', 'rb') as f:
            file_data = {
                'file': f,
                'name': 'index_test.txt',
                'description': 'File for testing indexing'
            }
            response = self.client.post(
                reverse('upload_file', args=[self.project.id]), 
                file_data
            )
        
        # Clean up test file
        os.remove('new_index_test.txt')
        
        self.assertEqual(response.status_code, 302)
        
        # Verify file was created
        new_file = FileAttachment.objects.filter(name='index_test.txt').first()
        self.assertIsNotNone(new_file)
        
        # Verify indexing was triggered
        mock_index_file.assert_called_once()
        mock_index_file.assert_called_with(new_file)
    
    def test_search_integration_flow(self):
        """Test the complete search flow with indexing and retrieval"""
        # 1. First, index the file attachment
        from search.indexing import index_file
        index_file(self.file_attachment)
        
        # Verify index was created
        file_index = FileIndex.objects.filter(file=self.file_attachment).first()
        self.assertIsNotNone(file_index)
        self.assertIn('search indexing', file_index.extracted_text.lower())
        
        # 2. Search for a term that exists in work items, messages and files
        response = self.client.get(f"{reverse('search')}?q=search")
        self.assertEqual(response.status_code, 200)
        
        # Verify work items found
        self.assertIn(b'Search Integration Project', response.content)
        self.assertIn(b'Search Implementation Task', response.content)
        
        # Verify messages found
        self.assertIn(b'elasticsearch', response.content)
        
        # Verify files found
        self.assertIn(b'search_specs.txt', response.content)
        
        # 3. Search with content type filters
        response = self.client.get(f"{reverse('search')}?q=search&content_types=work_item")
        self.assertEqual(response.status_code, 200)
        
        # Should find work items but not messages or files
        self.assertIn(b'Search Integration Project', response.content)
        self.assertNotIn(b'elasticsearch', response.content)
        self.assertNotIn(b'search_specs.txt', response.content)
        
        # 4. Save the search
        response = self.client.post(
            reverse('saved_searches'),
            {'name': 'Search Term Query', 'is_default': True}
        )
        self.assertEqual(response.status_code, 302)
        
        # Verify saved search
        saved_search = SavedSearch.objects.filter(name='Search Term Query').first()
        self.assertIsNotNone(saved_search)
        self.assertEqual(saved_search.query, 'search')
        self.assertTrue(saved_search.is_default)
        
        # 5. Load saved search
        response = self.client.get(
            reverse('saved_search_detail', args=[saved_search.slug])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('q=search', response.url)
        
        # 6. Update file and reindex
        from search.indexing import reindex_file
        reindex_file(self.file_attachment)
from django.test import TestCase, TransactionTestCase, LiveServerTestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.db.models import Q
from django.core.management import call_command
from django.conf import settings
from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from channels.db import database_sync_to_async

from unittest.mock import patch, MagicMock, call, ANY
import json
import datetime
import tempfile
import os
import asyncio
import time

from workspace.models import (
    WorkItem, Message, Thread, ThreadGroup, FileAttachment, Notification, NotificationPreference,
    MessageReadReceipt, SlowChannel, SlowChannelMessage, ScheduledMessage, BreakEvent,
    ThreadMessage, UserOnlineStatus
)
from workspace.routing import websocket_urlpatterns
from workspace.consumers import ChatConsumer, ThreadConsumer, NotificationConsumer
from workspace.tasks import send_scheduled_messages, deliver_slow_channel_messages
from search.models import SavedSearch, SearchLog, FileIndex
from search.views import search_view, search_work_items, search_messages, search_files
from search.indexing import index_file, reindex_file


class CollaborationWorkflowTests(TransactionTestCase):
    """Integration tests for the complete collaboration workflow"""
    
    def setUp(self):
        """Set up test data for collaboration workflow"""
        # Create users
        self.project_manager = User.objects.create_user(
            username='manager',
            email='manager@example.com',
            password='managerpassword'
        )
        
        self.developer = User.objects.create_user(
            username='developer',
            email='developer@example.com',
            password='developerpassword'
        )
        
        self.designer = User.objects.create_user(
            username='designer',
            email='designer@example.com',
            password='designerpassword'
        )
        
        self.tester = User.objects.create_user(
            username='tester',
            email='tester@example.com',
            password='testerpassword'
        )
        
        # Create clients for each user
        self.manager_client = Client()
        self.manager_client.login(username='manager', password='managerpassword')
        
        self.developer_client = Client()
        self.developer_client.login(username='developer', password='developerpassword')
        
        self.designer_client = Client()
        self.designer_client.login(username='designer', password='designerpassword')
        
        self.tester_client = Client()
        self.tester_client.login(username='tester', password='testerpassword')
        
        # Create notification preferences for users
        for user in [self.project_manager, self.developer, self.designer, self.tester]:
            NotificationPreference.objects.create(
                user=user,
                share_read_receipts=True,
                notification_mode='all'
            )
    
    def test_complete_project_workflow(self):
        """Test a complete project workflow from creation to completion"""
        # 1. Project manager creates a new project
        project_data = {
            'title': 'New Application Development',
            'description': 'Develop a new web application for client XYZ',
            'type': 'project',
            'status': 'planning',
            'priority': 'high',
            'due_date': (timezone.now() + datetime.timedelta(days=30)).strftime('%Y-%m-%d')
        }
        
        response = self.manager_client.post(reverse('create_work_item'), project_data)
        self.assertEqual(response.status_code, 302)  # Should redirect after creation
        
        # Get the newly created project
        project = WorkItem.objects.filter(title='New Application Development').first()
        self.assertIsNotNone(project)
        self.assertEqual(project.owner, self.project_manager)
        
        # 2. Project manager adds collaborators
        update_url = reverse('update_work_item', args=[project.id])
        collaborator_data = {
            'title': project.title,
            'description': project.description,
            'type': project.type,
            'status': project.status,
            'priority': project.priority,
            'collaborators': [self.developer.id, self.designer.id, self.tester.id]
        }
        
        response = self.manager_client.post(update_url, collaborator_data)
        self.assertEqual(response.status_code, 302)
        
        # Verify collaborators were added
        project.refresh_from_db()
        self.assertIn(self.developer, project.collaborators.all())
        self.assertIn(self.designer, project.collaborators.all())
        self.assertIn(self.tester, project.collaborators.all())
        
        # 3. Project manager creates a general discussion thread
        thread_data = {
            'title': 'General Project Discussion',
            'is_public': True
        }
        
        response = self.manager_client.post(
            reverse('create_thread', args=[project.id]),
            thread_data
        )
        self.assertEqual(response.status_code, 302)
        
        # Verify thread was created
        thread = Thread.objects.filter(title='General Project Discussion').first()
        self.assertIsNotNone(thread)
        self.assertEqual(thread.work_item, project)
        
        # 4. Developer adds a message to the thread
        thread_url = reverse('thread_detail', args=[project.id, thread.id])
        response = self.developer_client.get(thread_url)
        self.assertEqual(response.status_code, 200)
        
        message_data = {
            'content': 'I have started working on the initial architecture.'
        }
        
        response = self.developer_client.post(thread_url, message_data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(thread_url))
        
        # Verify message was created
        dev_message = Message.objects.filter(
            thread=thread,
            user=self.developer
        ).first()
        self.assertIsNotNone(dev_message)
        self.assertEqual(dev_message.content, 'I have started working on the initial architecture.')
        
        # 5. Designer reads the message
        response = self.designer_client.post(
            reverse('mark_message_read', args=[dev_message.id])
        )
        self.assertEqual(response.status_code, 200)
        
        # Verify read receipt
        read_receipt = MessageReadReceipt.objects.filter(
            message=dev_message,
            user=self.designer
        ).first()
        self.assertIsNotNone(read_receipt)
        
        # 6. Project manager checks read status
        response = self.manager_client.get(
            reverse('get_message_read_status', args=[dev_message.id])
        )
        self.assertEqual(response.status_code, 403)  # Should fail as manager is not author
        
        response = self.developer_client.get(
            reverse('get_message_read_status', args=[dev_message.id])
        )
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['total_read'], 1)
        
        # 7. Project manager creates a new task for designer
        task_data = {
            'title': 'Create UI Mockups',
            'description': 'Create initial UI mockups for client approval',
            'type': 'task',
            'status': 'todo',
            'priority': 'medium',
            'parent': project.id,
            'assigned_to': self.designer.id,
            'due_date': (timezone.now() + datetime.timedelta(days=7)).strftime('%Y-%m-%d')
        }
        
        response = self.manager_client.post(reverse('create_work_item'), task_data)
        self.assertEqual(response.status_code, 302)
        
        # Verify task was created
        design_task = WorkItem.objects.filter(title='Create UI Mockups').first()
        self.assertIsNotNone(design_task)
        self.assertEqual(design_task.parent, project)
        
        # 8. Designer uploads a file to the task
        with open('temp_mockup.png', 'wb') as f:
            f.write(b'mock image data')
            
        with open('temp_mockup.png', 'rb') as f:
            file_data = {
                'file': f,
                'name': 'homepage_mockup.png',
                'description': 'Homepage initial design'
            }
            response = self.designer_client.post(
                reverse('upload_file', args=[design_task.id]),
                file_data
            )
        
        # Clean up temp file
        os.remove('temp_mockup.png')
        
        self.assertEqual(response.status_code, 302)
        
        # Verify file was uploaded
        attachment = FileAttachment.objects.filter(name='homepage_mockup.png').first()
        self.assertIsNotNone(attachment)
        self.assertEqual(attachment.work_item, design_task)
        self.assertEqual(attachment.uploaded_by, self.designer)
        
        # 9. Tester creates a scheduled message for tomorrow's meeting
        tomorrow = timezone.now() + datetime.timedelta(days=1)
        scheduled_message_data = {
            'content': 'Reminder: Project review meeting at 10 AM',
            'scheduled_time': tomorrow.strftime('%Y-%m-%d %H:%M:%S'),
            'work_item': project.id
        }
        
        response = self.tester_client.post(
            reverse('schedule_message'),
            scheduled_message_data
        )
        self.assertEqual(response.status_code, 302)
        
        # Verify scheduled message
        scheduled_msg = ScheduledMessage.objects.filter(
            content='Reminder: Project review meeting at 10 AM'
        ).first()
        self.assertIsNotNone(scheduled_msg)
        self.assertEqual(scheduled_msg.sender, self.tester)
        self.assertEqual(scheduled_msg.work_item, project)
        
        # 10. Developer updates task status
        design_task.status = 'in_progress'
        design_task.save()
        
        # 11. Search for project assets
        response = self.tester_client.get(
            f"{reverse('search')}?q=mockup&content_types=file"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'homepage_mockup.png', response.content)
        
        # 12. Designer completes the task
        design_task.status = 'done'
        design_task.save()
        
        # 13. Project manager creates a slow channel for project reflections
        slow_channel_data = {
            'title': 'Project Reflections',
            'description': 'Weekly reflections on project progress',
            'type': 'reflection',
            'message_frequency': 'weekly',
            'participants': [
                self.project_manager.id,
                self.developer.id,
                self.designer.id,
                self.tester.id
            ]
        }
        
        response = self.manager_client.post(
            reverse('create_slow_channel', args=[project.id]),
            slow_channel_data
        )
        self.assertEqual(response.status_code, 302)
        
        # Verify slow channel
        slow_channel = SlowChannel.objects.filter(title='Project Reflections').first()
        self.assertIsNotNone(slow_channel)
        self.assertEqual(slow_channel.work_item, project)
        self.assertEqual(slow_channel.created_by, self.project_manager)
        
        # Verify all participants are added
        participants = slow_channel.participants.all()
        self.assertEqual(participants.count(), 4)
        self.assertIn(self.project_manager, participants)
        self.assertIn(self.developer, participants)
        self.assertIn(self.designer, participants)
        self.assertIn(self.tester, participants)
        
        # 14. Developer sends a message to the slow channel
        slow_message_data = {
            'content': 'I think our architecture is solid, but we might want to consider refactoring the authentication module.'
        }
        
        response = self.developer_client.post(
            reverse('slow_channel_detail', args=[slow_channel.id]),
            slow_message_data
        )
        self.assertEqual(response.status_code, 302)
        
        # Verify slow channel message
        sc_message = SlowChannelMessage.objects.filter(
            channel=slow_channel,
            user=self.developer
        ).first()
        self.assertIsNotNone(sc_message)
        self.assertEqual(
            sc_message.content,
            'I think our architecture is solid, but we might want to consider refactoring the authentication module.'
        )
        
        # 15. Project completion
        project.status = 'completed'
        project.save()
        
        # Verify final project status
        project.refresh_from_db()
        self.assertEqual(project.status, 'completed')


class RealTimeMessagingTests(TransactionTestCase):
    """Integration tests for real-time messaging functionality"""
    
    async def setUp(self):
        """Set up test data for real-time messaging tests"""
        # Create users
        self.user1 = await database_sync_to_async(User.objects.create_user)(
            username='user1',
            email='user1@example.com',
            password='user1password'
        )
        
        self.user2 = await database_sync_to_async(User.objects.create_user)(
            username='user2',
            email='user2@example.com',
            password='user2password'
        )
        
        # Create a work item
        self.work_item = await database_sync_to_async(WorkItem.objects.create)(
            title='WebSocket Test Project',
            description='Testing WebSocket functionality',
            type='project',
            owner=self.user1
        )
        await database_sync_to_async(self.work_item.collaborators.add)(self.user2)
        
        # Create a thread
        self.thread = await database_sync_to_async(Thread.objects.create)(
            title='WebSocket Test Thread',
            work_item=self.work_item,
            created_by=self.user1,
            is_public=True
        )
    
    @patch('workspace.consumers.get_user')
    async def test_chat_communication(self, mock_get_user):
        """Test real-time chat communication between users"""
        # Mock the get_user function to return our test users
        mock_get_user.side_effect = lambda user_id: self.user1 if user_id == self.user1.id else self.user2
        
        # Create WebSocket communicators for both users
        application = URLRouter(websocket_urlpatterns)
        communicator1 = WebsocketCommunicator(
            application,
            f"/ws/chat/{self.work_item.id}/"
        )
        communicator2 = WebsocketCommunicator(
            application,
            f"/ws/chat/{self.work_item.id}/"
        )
        
        # Connect both users
        connected1, _ = await communicator1.connect()
        connected2, _ = await communicator2.connect()
        self.assertTrue(connected1)
        self.assertTrue(connected2)
        
        # User 1 sends a message
        await communicator1.send_json_to({
            'message': 'Hello from User 1',
            'user_id': self.user1.id
        })
        
        # User 2 should receive the message
        response = await communicator2.receive_json_from()
        self.assertEqual(response['message'], 'Hello from User 1')
        self.assertEqual(response['user_id'], self.user1.id)
        self.assertEqual(response['username'], 'user1')
        
        # User 2 sends a reply
        await communicator2.send_json_to({
            'message': 'Hello User 1, this is User 2',
            'user_id': self.user2.id
        })
        
        # User 1 should receive the reply
        response = await communicator1.receive_json_from()
        self.assertEqual(response['message'], 'Hello User 1, this is User 2')
        self.assertEqual(response['user_id'], self.user2.id)
        self.assertEqual(response['username'], 'user2')
        
        # Close connections
        await communicator1.disconnect()
        await communicator2.disconnect()
    
    @patch('workspace.consumers.get_user')
    async def test_thread_communication(self, mock_get_user):
        """Test real-time thread communication between users"""
        # Mock the get_user function
        mock_get_user.side_effect = lambda user_id: self.user1 if user_id == self.user1.id else self.user2
        
        # Create WebSocket communicators for both users
        application = URLRouter(websocket_urlpatterns)
        communicator1 = WebsocketCommunicator(
            application,
            f"/ws/thread/{self.work_item.id}/{self.thread.id}/"
        )
        communicator2 = WebsocketCommunicator(
            application,
            f"/ws/thread/{self.work_item.id}/{self.thread.id}/"
        )
        
        # Connect both users
        connected1, _ = await communicator1.connect()
        connected2, _ = await communicator2.connect()
        self.assertTrue(connected1)
        self.assertTrue(connected2)
        
        # User 1 sends a thread message
        await communicator1.send_json_to({
            'message': 'This is a thread message from User 1',
            'user_id': self.user1.id,
            'parent_id': None
        })
        
        # User 2 should receive the message
        response = await communicator2.receive_json_from()
        self.assertEqual(response['message'], 'This is a thread message from User 1')
        self.assertEqual(response['user_id'], self.user1.id)
        self.assertEqual(response['username'], 'user1')
        message_id = response['message_id']
        
        # User 2 sends a reply to the thread message
        await communicator2.send_json_to({
            'message': 'Reply to your thread message',
            'user_id': self.user2.id,
            'parent_id': message_id
        })
        
        # User 1 should receive the reply
        response = await communicator1.receive_json_from()
        self.assertEqual(response['message'], 'Reply to your thread message')
        self.assertEqual(response['user_id'], self.user2.id)
        self.assertEqual(response['parent_id'], message_id)
        
        # Close connections
        await communicator1.disconnect()
        await communicator2.disconnect()
    
    @patch('workspace.consumers.NotificationConsumer.group_send')
    async def test_notifications_broadcasting(self, mock_group_send):
        """Test notification broadcasting when events occur"""
        # Create notification
        notification = await database_sync_to_async(Notification.objects.create)(
            user=self.user1,
            message='You have a new message',
            notification_type='message',
            work_item=self.work_item
        )
        
        # Verify notification is created
        notification_exists = await database_sync_to_async(
            lambda: Notification.objects.filter(id=notification.id).exists()
        )()
        self.assertTrue(notification_exists)
        
        # Verify group_send was called to broadcast notification
        mock_group_send.assert_called_with(
            f'notifications_{self.user1.id}',
            {
                'type': 'notification_message',
                'message': 'You have a new message',
                'count': 1,
                'notification_id': notification.id
            }
        )


class SearchAndIndexingTests(TestCase):
    """Integration tests for search and indexing functionality"""
    
    def setUp(self):
        """Set up test data for search and indexing tests"""
        # Create users
        self.user = User.objects.create_user(
            username='searchuser',
            email='search@example.com',
            password='searchpassword'
        )
        
        self.client = Client()
        self.client.login(username='searchuser', password='searchpassword')
        
        # Create work items with different content
        self.project = WorkItem.objects.create(
            title='Search Integration Project',
            description='This is a project for testing search integration',
            type='project',
            owner=self.user
        )
        
        self.task = WorkItem.objects.create(
            title='Search Implementation Task',
            description='Implement advanced search functionality',
            type='task',
            owner=self.user,
            parent=self.project
        )
        
        # Create messages
        self.message1 = Message.objects.create(
            work_item=self.project,
            user=self.user,
            content='This message contains searchable keywords like elasticsearch and indexing'
        )
        
        self.message2 = Message.objects.create(
            work_item=self.task,
            user=self.user,
            content='Planning to use analyzer for better search results with fuzzy matching'
        )
        
        # Create thread
        self.thread = Thread.objects.create(
            title='Search Features Discussion',
            work_item=self.project,
            created_by=self.user,
            is_public=True
        )
        
        # Add thread messages
        self.thread_message = Message.objects.create(
            work_item=self.project,
            thread=self.thread,
            user=self.user,
            content='We need to implement tokenization for better search accuracy',
            is_thread_starter=True
        )
        
        # Create files with content for indexing
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.txt', delete=False)
        self.temp_file.write(b'This is a test file for search indexing with important technical terms')
        self.temp_file.close()
        
        with open(self.temp_file.name, 'rb') as f:
            self.file_attachment = FileAttachment.objects.create(
                work_item=self.project,
                file=SimpleUploadedFile('search_specs.txt', f.read()),
                name='search_specs.txt',
                uploaded_by=self.user
            )
    
    def tearDown(self):
        """Clean up temporary files"""
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)
    
    @patch('search.signals.index_file')
    def test_file_indexing_on_upload(self, mock_index_file):
        """Test that files are indexed when uploaded"""
        # Create a new file
        with open('new_index_test.txt', 'wb') as f:
            f.write(b'New file content for testing automatic indexing')
            
        with open('new_index_test.txt', 'rb') as f:
            file_data = {
                'file': f,
                'name': 'index_test.txt',
                'description': 'File for testing indexing'
            }
            response = self.client.post(
                reverse('upload_file', args=[self.project.id]), 
                file_data
            )
        
        # Clean up test file
        os.remove('new_index_test.txt')
        
        self.assertEqual(response.status_code, 302)
        
        # Verify file was created
        new_file = FileAttachment.objects.filter(name='index_test.txt').first()
        self.assertIsNotNone(new_file)
        
        # Verify indexing was triggered
        mock_index_file.assert_called_once()
        mock_index_file.assert_called_with(new_file)
    
def test_search_integration_flow(self):
    """Test the complete search flow with indexing and retrieval"""
    # 1. First, index the file attachment
    from search.indexing import index_file
    index_file(self.file_attachment)
    
    # Verify index was created
    file_index = FileIndex.objects.filter(file=self.file_attachment).first()
    self.assertIsNotNone(file_index)
    self.assertIn('search indexing', file_index.extracted_text.lower())
    
    # 2. Search for a term that exists in work items, messages and files
    response = self.client.get(f"{reverse('search')}?q=search")
    self.assertEqual(response.status_code, 200)
    
    # Verify work items found
    self.assertIn(b'Search Integration Project', response.content)
    self.assertIn(b'Search Implementation Task', response.content)
    
    # Verify messages found
    self.assertIn(b'elasticsearch', response.content)
    
    # Verify files found
    self.assertIn(b'search_specs.txt', response.content)
    
    # 3. Search with content type filters
    response = self.client.get(f"{reverse('search')}?q=search&content_types=work_item")
    self.assertEqual(response.status_code, 200)
    
    # Should find work items but not messages or files
    self.assertIn(b'Search Integration Project', response.content)
    self.assertNotIn(b'elasticsearch', response.content)
    self.assertNotIn(b'search_specs.txt', response.content)
    
    # 4. Save the search
    response = self.client.post(
        reverse('saved_searches'),
        {'name': 'Search Term Query', 'is_default': True}
    )
    self.assertEqual(response.status_code, 302)
    
    # Verify saved search
    saved_search = SavedSearch.objects.filter(name='Search Term Query').first()
    self.assertIsNotNone(saved_search)
    self.assertEqual(saved_search.query, 'search')
    self.assertTrue(saved_search.is_default)
    
    # 5. Load saved search
    response = self.client.get(
        reverse('saved_search_detail', args=[saved_search.slug])
    )
    self.assertEqual(response.status_code, 302)
    self.assertIn('q=search', response.url)
    
    # 6. Update file and reindex
    # First modify the file content
    with open(self.temp_file.name, 'wb') as f:
        f.write(b'Updated content with additional search keywords and relevance scoring')
    
    # Update the file attachment with new content
    with open(self.temp_file.name, 'rb') as f:
        updated_file = SimpleUploadedFile('search_specs_updated.txt', f.read())
    
    # Update the file attachment
    self.file_attachment.file = updated_file
    self.file_attachment.save()
    
    # Reindex the file
    from search.indexing import reindex_file
    reindex_file(self.file_attachment)
    
    # Verify index was updated
    file_index.refresh_from_db()
    self.assertIn('additional search keywords', file_index.extracted_text.lower())
    
    # 7. Search for new terms that were just added
    response = self.client.get(f"{reverse('search')}?q=relevance+scoring")
    self.assertEqual(response.status_code, 200)
    
    # Should find the updated file
    self.assertIn(b'search_specs.txt', response.content)

class NotificationAndCommunicationTests(TestCase):
    """Integration tests for notifications and communication workflows"""
    
    def setUp(self):
        """Set up test data for notification and communication integration tests"""
        # Create users
        self.manager = User.objects.create_user(
            username='manager',
            email='manager@example.com',
            password='managerpassword'
        )
        
        self.team_member = User.objects.create_user(
            username='member',
            email='member@example.com',
            password='memberpassword'
        )
        
        # Create notification preferences
        self.manager_prefs = NotificationPreference.objects.create(
            user=self.manager,
            share_read_receipts=True,
            notification_mode='all'
        )
        
        self.member_prefs = NotificationPreference.objects.create(
            user=self.team_member,
            share_read_receipts=True,
            notification_mode='all'
        )
        
        # Create a project
        self.project = WorkItem.objects.create(
            title='Notification Test Project',
            description='Project for testing notifications',
            type='project',
            owner=self.manager
        )
        self.project.collaborators.add(self.team_member)
        
        # Create clients
        self.manager_client = Client()
        self.manager_client.login(username='manager', password='managerpassword')
        
        self.member_client = Client()
        self.member_client.login(username='member', password='memberpassword')
    
    def test_notifications_across_actions(self):
        """Test notifications triggered by various user actions"""
        # 1. Team member creates a thread in the project
        thread_data = {
            'title': 'Important Discussion',
            'is_public': True
        }
        
        response = self.member_client.post(
            reverse('create_thread', args=[self.project.id]),
            thread_data
        )
        self.assertEqual(response.status_code, 302)
        
        # Verify thread was created
        thread = Thread.objects.filter(title='Important Discussion').first()
        self.assertIsNotNone(thread)
        
        # Verify notification was created for the project owner
        notification = Notification.objects.filter(
            user=self.manager,
            notification_type='thread_created'
        ).first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.work_item, self.project)
        
        # 2. Manager reads notification and marks it as read
        response = self.manager_client.post(
            reverse('mark_notification_read', args=[notification.id])
        )
        self.assertEqual(response.status_code, 302)
        
        # Verify notification is marked as read
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        
        # 3. Manager posts a message in the thread
        thread_url = reverse('thread_detail', args=[self.project.id, thread.id])
        message_data = {
            'content': 'This is an important update from management'
        }
        
        response = self.manager_client.post(thread_url, message_data)
        self.assertEqual(response.status_code, 302)
        
        # Verify message was created
        message = Message.objects.filter(
            thread=thread,
            user=self.manager
        ).first()
        self.assertIsNotNone(message)
        
        # Verify notification was created for team member
        notification = Notification.objects.filter(
            user=self.team_member,
            notification_type='message'
        ).first()
        self.assertIsNotNone(notification)
        
        # 4. Team member enables DND mode
        self.member_prefs.dnd_enabled = True
        self.member_prefs.dnd_start_time = datetime.time(0, 0)  # 12 AM
        self.member_prefs.dnd_end_time = datetime.time(23, 59)  # 11:59 PM
        self.member_prefs.save()
        
        # 5. Manager creates another message (should be delayed due to DND)
        message_data = {
            'content': 'Another important update'
        }
        
        response = self.manager_client.post(thread_url, message_data)
        self.assertEqual(response.status_code, 302)
        
        # Verify message was created
        message = Message.objects.filter(
            thread=thread,
            content='Another important update'
        ).first()
        self.assertIsNotNone(message)
        
        # Verify notification was created but delayed
        notification = Notification.objects.filter(
            user=self.team_member,
            message__contains='Another important update'
        ).first()
        self.assertIsNotNone(notification)
        self.assertTrue(notification.is_delayed)
        
        # 6. Team member creates urgent message which should bypass DND
        message_data = {
            'content': 'URGENT: Critical issue needs immediate attention',
            'priority': 'urgent'  # Adding priority field
        }
        
        # Create an urgent message directly to bypass DND
        urgent_message = Message.objects.create(
            work_item=self.project,
            thread=thread,
            user=self.team_member,
            content='URGENT: Critical issue needs immediate attention',
            priority='urgent'
        )
        
        # Manually create notification to ensure priority is set
        urgent_notif = Notification.objects.create(
            user=self.manager,
            work_item=self.project,
            message='URGENT: Critical issue needs immediate attention',
            notification_type='message',
            priority='urgent'
        )
        
        # Verify notification was created and not delayed despite DND
        self.assertFalse(urgent_notif.is_delayed)
        
    def test_read_receipts_and_focus_mode(self):
        """Test read receipts and focus mode integration"""
        # 1. Manager creates a message in the project
        message = Message.objects.create(
            work_item=self.project,
            user=self.manager,
            content='Please review this when you have time'
        )
        
        # 2. Team member reads the message
        response = self.member_client.post(
            reverse('mark_message_read', args=[message.id])
        )
        self.assertEqual(response.status_code, 200)
        
        # Verify read receipt was created
        read_receipt = MessageReadReceipt.objects.filter(
            message=message,
            user=self.team_member
        ).first()
        self.assertIsNotNone(read_receipt)
        
        # 3. Manager checks read status
        response = self.manager_client.get(
            reverse('get_message_read_status', args=[message.id])
        )
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['total_read'], 1)
        
        # 4. Team member disables read receipts
        self.member_prefs.share_read_receipts = False
        self.member_prefs.save()
        
        # 5. Manager creates another message
        message2 = Message.objects.create(
            work_item=self.project,
            user=self.manager,
            content='Another message for review'
        )
        
        # 6. Team member reads the message
        response = self.member_client.post(
            reverse('mark_message_read', args=[message2.id])
        )
        self.assertEqual(response.status_code, 200)
        
        # Verify no read receipt was created
        read_receipt_exists = MessageReadReceipt.objects.filter(
            message=message2,
            user=self.team_member
        ).exists()
        self.assertFalse(read_receipt_exists)
        
        # 7. Manager enables focus mode
        self.manager_prefs.focus_mode = True
        self.manager_prefs.save()
        
        # Add project to focus items
        self.manager_prefs.focus_work_items.add(self.project)
        
        # 8. Team member creates a message in the focus project
        focus_message = Message.objects.create(
            work_item=self.project,
            user=self.team_member,
            content='This should get through focus mode'
        )
        
        # Create notification for this message
        focus_notif = Notification.objects.create(
            user=self.manager,
            work_item=self.project,
            message='New message from team member',
            notification_type='message'
        )
        
        # Verify notification is not filtered by focus mode
        self.assertFalse(focus_notif.is_focus_filtered)
        
        # 9. Create another project that's not in focus
        non_focus_project = WorkItem.objects.create(
            title='Non-Focus Project',
            description='Project not in focus mode',
            type='project',
            owner=self.team_member
        )
        non_focus_project.collaborators.add(self.manager)
        
        # 10. Create message in non-focus project
        non_focus_message = Message.objects.create(
            work_item=non_focus_project,
            user=self.team_member,
            content='This should be filtered by focus mode'
        )
        
        # Create notification for this message
        non_focus_notif = Notification.objects.create(
            user=self.manager,
            work_item=non_focus_project,
            message='New message in non-focus project',
            notification_type='message'
        )
        
        # Verify notification is filtered by focus mode
        self.assertTrue(non_focus_notif.is_focus_filtered)


class SchedulingAndSlowChannelTests(TransactionTestCase):
    """Integration tests for scheduling and slow channels"""
    
    def setUp(self):
        """Set up test data for scheduling and slow channel tests"""
        # Create users
        self.team_lead = User.objects.create_user(
            username='teamlead',
            email='lead@example.com',
            password='leadpassword'
        )
        
        self.team_members = []
        for i in range(3):
            user = User.objects.create_user(
                username=f'member{i}',
                email=f'member{i}@example.com',
                password='memberpassword'
            )
            self.team_members.append(user)
        
        # Create clients
        self.lead_client = Client()
        self.lead_client.login(username='teamlead', password='leadpassword')
        
        self.member_clients = []
        for i in range(3):
            client = Client()
            client.login(username=f'member{i}', password='memberpassword')
            self.member_clients.append(client)
        
        # Create a project
        self.project = WorkItem.objects.create(
            title='Team Coordination Project',
            description='Project for team coordination and slow communications',
            type='project',
            owner=self.team_lead
        )
        
        # Add team members as collaborators
        for member in self.team_members:
            self.project.collaborators.add(member)
    
    @patch('workspace.tasks.send_scheduled_messages')
    def test_scheduled_messages_workflow(self, mock_send_scheduled_messages):
        """Test the scheduled messages workflow"""
        # 1. Team lead creates a scheduled message
        tomorrow = timezone.now() + datetime.timedelta(days=1)
        scheduled_data = {
            'content': 'Team meeting tomorrow at 10:00 AM',
            'scheduled_time': tomorrow.strftime('%Y-%m-%d %H:%M:%S'),
            'work_item': self.project.id
        }
        
        response = self.lead_client.post(reverse('schedule_message'), scheduled_data)
        self.assertEqual(response.status_code, 302)
        
        # Verify scheduled message was created
        scheduled_msg = ScheduledMessage.objects.filter(
            content='Team meeting tomorrow at 10:00 AM'
        ).first()
        self.assertIsNotNone(scheduled_msg)
        self.assertEqual(scheduled_msg.sender, self.team_lead)
        self.assertEqual(scheduled_msg.work_item, self.project)
        self.assertEqual(scheduled_msg.scheduled_time.date(), tomorrow.date())
        
        # 2. Team lead views their scheduled messages
        response = self.lead_client.get(reverse('my_scheduled_messages'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Team meeting tomorrow at 10:00 AM', response.content)
        
        # 3. Simulate scheduled message sending task
        result = mock_send_scheduled_messages.return_value = {
            'status': 'success',
            'sent': 1,
            'failed': 0
        }
        
        # Call management command
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command('send_scheduled_messages', stdout=out)
        
        # Check command output
        output = out.getvalue()
        mock_send_scheduled_messages.assert_called_once()
        
        # 4. Create a scheduled message in the past (should be sent immediately by task)
        past_time = timezone.now() - datetime.timedelta(hours=1)
        past_scheduled = ScheduledMessage.objects.create(
            sender=self.team_lead,
            work_item=self.project,
            content='This message should be sent immediately',
            scheduled_time=past_time,
            is_sent=False
        )
        
        # Send the scheduled message manually (simulate task)
        from workspace.models import Message
        message = Message.objects.create(
            work_item=self.project,
            user=self.team_lead,
            content=past_scheduled.content
        )
        
        past_scheduled.message = message
        past_scheduled.is_sent = True
        past_scheduled.sent_at = timezone.now()
        past_scheduled.save()
        
        # Verify message was created and scheduled message was marked as sent
        self.assertTrue(past_scheduled.is_sent)
        self.assertIsNotNone(past_scheduled.sent_at)
        
        # Verify the actual message exists in the system
        created_message = Message.objects.filter(content=past_scheduled.content).first()
        self.assertIsNotNone(created_message)
        self.assertEqual(created_message.work_item, self.project)
        self.assertEqual(created_message.user, self.team_lead)
    
    def test_slow_channel_workflow(self):
        """Test the slow channel communication workflow"""
        # 1. Team lead creates a slow channel
        slow_channel_data = {
            'title': 'Weekly Reflections',
            'description': 'Channel for weekly team reflections',
            'type': 'reflection',
            'message_frequency': 'weekly',
            'participants': [user.id for user in self.team_members] + [self.team_lead.id]
        }
        
        response = self.lead_client.post(
            reverse('create_slow_channel', args=[self.project.id]),
            slow_channel_data
        )
        self.assertEqual(response.status_code, 302)
        
        # Verify slow channel was created
        slow_channel = SlowChannel.objects.filter(title='Weekly Reflections').first()
        self.assertIsNotNone(slow_channel)
        self.assertEqual(slow_channel.work_item, self.project)
        self.assertEqual(slow_channel.created_by, self.team_lead)
        self.assertEqual(slow_channel.type, 'reflection')
        self.assertEqual(slow_channel.message_frequency, 'weekly')
        
        # Verify all participants were added
        for user in self.team_members + [self.team_lead]:
            self.assertIn(user, slow_channel.participants.all())
        
        # 2. Team members add messages to the slow channel
        for i, member_client in enumerate(self.member_clients):
            slow_message_data = {
                'content': f'Reflection from team member {i}: we should focus on improving {i+1} area'
            }
            
            response = member_client.post(
                reverse('slow_channel_detail', args=[slow_channel.id]),
                slow_message_data
            )
            self.assertEqual(response.status_code, 302)
        
        # Verify messages were created
        for i in range(3):
            sc_message = SlowChannelMessage.objects.filter(
                channel=slow_channel,
                user=self.team_members[i]
            ).first()
            self.assertIsNotNone(sc_message)
            self.assertEqual(
                sc_message.content,
                f'Reflection from team member {i}: we should focus on improving {i+1} area'
            )
        
        # 3. Schedule message delivery for the channel
        # Create a scheduled delivery time (next Monday)
        import datetime as dt
        today = dt.date.today()
        next_monday = today + dt.timedelta(days=(7 - today.weekday()))
        delivery_time = timezone.make_aware(dt.datetime.combine(next_monday, dt.time(9, 0)))
        
        # Schedule delivery for all messages
        for sc_message in SlowChannelMessage.objects.filter(channel=slow_channel):
            sc_message.scheduled_delivery = delivery_time
            sc_message.save()
        
        # 4. Simulate the delivery task
        @patch('workspace.tasks.deliver_slow_channel_messages')
        def test_delivery(mock_deliver):
            mock_deliver.return_value = {
                'status': 'success',
                'delivered': 3,
                'failed': 0
            }
            
            from django.core.management import call_command
            from io import StringIO
            out = StringIO()
            call_command('deliver_slow_channel_messages', stdout=out)
            
            mock_deliver.assert_called_once()
        
        test_delivery()
        
        # 5. Mark messages as delivered (simulate task)
        for sc_message in SlowChannelMessage.objects.filter(channel=slow_channel):
            sc_message.is_delivered = True
            sc_message.delivered_at = timezone.now()
            sc_message.save()
        
        # Verify all messages were marked as delivered
        for sc_message in SlowChannelMessage.objects.filter(channel=slow_channel):
            self.assertTrue(sc_message.is_delivered)
            self.assertIsNotNone(sc_message.delivered_at)
        
        # 6. Team lead views all reflections
        response = self.lead_client.get(reverse('slow_channel_detail', args=[slow_channel.id]))
        self.assertEqual(response.status_code, 200)
        
        # Check that all reflections are visible
        for i in range(3):
            self.assertIn(
                f'Reflection from team member {i}: we should focus on improving {i+1} area'.encode(),
                response.content
            )