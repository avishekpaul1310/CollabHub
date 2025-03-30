from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.utils.text import slugify
from django.db.models import Q
import json
import tempfile
from unittest.mock import patch, MagicMock
import os

from workspace.models import (
    WorkItem, Message, Thread, FileAttachment, SlowChannel
)
from search.models import SavedSearch, SearchLog, FileIndex
from search.indexing import index_file, extract_text_from_document
from search.forms import AdvancedSearchForm, SavedSearchForm
from search.templatetags.search_filters import highlight, truncate_middle, file_icon_class

class SearchModelTests(TestCase):
    """Tests for search-related models."""
    
    def setUp(self):
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
        
        # Create a file attachment
        self.file_content = b'This is a test file with searchable content'
        self.test_file = SimpleUploadedFile(
            name='test_file.txt',
            content=self.file_content,
            content_type='text/plain'
        )
        
        self.file_attachment = FileAttachment.objects.create(
            work_item=self.work_item,
            file=self.test_file,
            name='test_file.txt',
            uploaded_by=self.user
        )
        
        # Create a saved search
        self.saved_search = SavedSearch.objects.create(
            user=self.user,
            name='Test Search',
            query='test',
            filters=json.dumps({'type': 'task'}),
            slug='test-search'
        )
        
        # Create a search log
        self.search_log = SearchLog.objects.create(
            user=self.user,
            query='test query',
            filters=json.dumps({'content_types': ['work_item']}),
            results_count=5
        )
    
    def test_saved_search_creation(self):
        """Test that a SavedSearch can be created with proper attributes."""
        self.assertEqual(self.saved_search.name, 'Test Search')
        self.assertEqual(self.saved_search.query, 'test')
        self.assertEqual(self.saved_search.get_filters(), {'type': 'task'})
        self.assertEqual(self.saved_search.slug, 'test-search')
        self.assertFalse(self.saved_search.is_default)
    
    def test_saved_search_default_handling(self):
        """Test that setting a saved search as default unsets other defaults."""
        # Create a second search and set as default
        saved_search2 = SavedSearch.objects.create(
            user=self.user,
            name='Default Search',
            query='default',
            filters='{}',
            is_default=True
        )
        
        # Check it's set as default
        saved_search2.refresh_from_db()
        self.assertTrue(saved_search2.is_default)
        
        # Set the first one as default
        self.saved_search.is_default = True
        self.saved_search.save()
        
        # Refresh both from DB
        self.saved_search.refresh_from_db()
        saved_search2.refresh_from_db()
        
        # Check that first one is now default and second one is not
        self.assertTrue(self.saved_search.is_default)
        self.assertFalse(saved_search2.is_default)
    
    def test_saved_search_unique_slug(self):
        """Test that SavedSearch creates unique slugs."""
        # Create a search with the same name
        saved_search2 = SavedSearch.objects.create(
            user=self.user,
            name='Test Search',
            query='test',
            filters='{}'
        )
        
        # Slug should be different
        self.assertNotEqual(saved_search2.slug, self.saved_search.slug)
        self.assertTrue(saved_search2.slug.startswith('test-search-'))
    
    def test_search_log_creation(self):
        """Test that a SearchLog can be created with proper attributes."""
        self.assertEqual(self.search_log.query, 'test query')
        self.assertEqual(self.search_log.get_filters(), {'content_types': ['work_item']})
        self.assertEqual(self.search_log.results_count, 5)
    
    def test_file_index_creation(self):
        """Test that a FileIndex can be created."""
        # Create a file index
        file_index = FileIndex.objects.create(
            file=self.file_attachment,
            extracted_text='Test extracted text',
            file_type='.txt'
        )
        
        self.assertEqual(file_index.file, self.file_attachment)
        self.assertEqual(file_index.extracted_text, 'Test extracted text')
        self.assertEqual(file_index.file_type, '.txt')
        
    def test_file_index_str_representation(self):
        """Test the string representation of a FileIndex."""
        file_index = FileIndex.objects.create(
            file=self.file_attachment,
            extracted_text='Test extracted text',
            file_type='.txt'
        )
        
        self.assertEqual(str(file_index), f"Index for {self.file_attachment.name}")


class SearchIndexingTests(TestCase):
    """Tests for search indexing functionality."""
    
    def setUp(self):
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
        
        # Create test files
        self.text_content = b'This is a plain text file with searchable content'
        self.text_file = SimpleUploadedFile(
            name='test_document.txt',
            content=self.text_content,
            content_type='text/plain'
        )
        
        # Create file attachments
        self.text_file_attachment = FileAttachment.objects.create(
            work_item=self.work_item,
            file=self.text_file,
            name='test_document.txt',
            uploaded_by=self.user
        )
    
    @patch('search.indexing.extract_text_from_document')
    def test_index_text_file(self, mock_extract):
        """Test indexing a text file."""
        # Set up mock
        mock_extract.return_value = "This is extracted text content."
        
        # Call function
        result = index_file(self.text_file_attachment)
        
        # Check result
        self.assertTrue(result)
        
        # Check that FileIndex was created
        file_index = FileIndex.objects.get(file=self.text_file_attachment)
        self.assertEqual(file_index.file_type, '.txt')
        
        # Verify mock was not called for text files (they're processed directly)
        mock_extract.assert_not_called()
    
    @patch('search.indexing.extract_text_from_document')
    def test_reindex_existing_file(self, mock_extract):
        """Test reindexing a file that already has an index."""
        # Create initial index
        FileIndex.objects.create(
            file=self.text_file_attachment,
            extracted_text='Initial content',
            file_type='.txt'
        )
        
        # Mock extract function to return new content
        mock_extract.return_value = "Updated content"
        
        # Call function
        result = index_file(self.text_file_attachment)
        
        # Check result
        self.assertTrue(result)
        
        # Verify index was updated
        file_index = FileIndex.objects.get(file=self.text_file_attachment)
        self.assertNotEqual(file_index.extracted_text, 'Initial content')
    
    def test_index_unsupported_file_type(self):
        """Test indexing an unsupported file type."""
        # Create an unsupported file
        unsupported_file = SimpleUploadedFile(
            name='test_file.xyz',
            content=b'Unsupported file content',
            content_type='application/octet-stream'
        )
        
        unsupported_attachment = FileAttachment.objects.create(
            work_item=self.work_item,
            file=unsupported_file,
            name='test_file.xyz',
            uploaded_by=self.user
        )
        
        # Call function
        result = index_file(unsupported_attachment)
        
        # Check result is False for unsupported type
        self.assertFalse(result)
        
        # Check that no FileIndex was created
        self.assertFalse(FileIndex.objects.filter(file=unsupported_attachment).exists())

    @override_settings(TESTING=True)
    def test_extract_text_from_document_in_test_mode(self):
        """Test extract_text_from_document in test mode."""
        # In test mode, it should return a placeholder
        result = extract_text_from_document(self.text_file_attachment, '.txt')
        self.assertEqual(result, "Test document content")


class SearchViewTests(TestCase):
    """Tests for search views."""
    
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
        
        # Log in user1
        self.client.login(username='user1', password='password123')
        
        # Create work items
        self.work_item1 = WorkItem.objects.create(
            title='Test Work Item',
            description='Test description for searching',
            type='task',
            owner=self.user1
        )
        
        self.work_item2 = WorkItem.objects.create(
            title='Another Work Item',
            description='Different description',
            type='project',
            owner=self.user1
        )
        
        self.work_item3 = WorkItem.objects.create(
            title='User2 Work Item',
            description='Item owned by user2',
            type='doc',
            owner=self.user2
        )
        self.work_item3.collaborators.add(self.user1)
        
        # Create messages
        self.message1 = Message.objects.create(
            work_item=self.work_item1,
            user=self.user1,
            content='Test message with searchable content'
        )
        
        self.message2 = Message.objects.create(
            work_item=self.work_item2,
            user=self.user2,
            content='Another test message'
        )
        
        # Create thread
        self.thread = Thread.objects.create(
            work_item=self.work_item1,
            title='Test Thread',
            created_by=self.user1,
            is_public=True
        )
        
        # Create thread message
        self.thread_message = Message.objects.create(
            work_item=self.work_item1,
            thread=self.thread,
            user=self.user1,
            content='Message in thread with searchable content',
            is_thread_starter=True
        )
        
        # Create file attachment
        self.file_content = b'This is a test file with unique searchable content'
        self.test_file = SimpleUploadedFile(
            name='searchable_file.txt',
            content=self.file_content,
            content_type='text/plain'
        )
        
        self.file_attachment = FileAttachment.objects.create(
            work_item=self.work_item1,
            file=self.test_file,
            name='searchable_file.txt',
            uploaded_by=self.user1
        )
        
        # Create file index
        self.file_index = FileIndex.objects.create(
            file=self.file_attachment,
            extracted_text='Searchable content inside the file',
            file_type='.txt'
        )
        
        # Create slow channel
        self.slow_channel = SlowChannel.objects.create(
            title='Test Slow Channel',
            description='Test channel for searching',
            type='reflection',
            work_item=self.work_item1,
            created_by=self.user1
        )
        self.slow_channel.participants.add(self.user1)
        
        # Create saved search for user1
        self.saved_search = SavedSearch.objects.create(
            user=self.user1,
            name='Test Search',
            query='test',
            filters=json.dumps({'type': 'task'}),
            is_default=True
        )

    def test_search_view_not_authenticated(self):
        """Test that search view requires authentication."""
        # Log out
        self.client.logout()
        
        # Attempt to access search view
        url = reverse('search')
        response = self.client.get(url)
        
        # Should redirect to login
        self.assertRedirects(response, f'{reverse("login")}?next={url}')
    
    def test_search_view_simple_query(self):
        """Test search view with a simple query."""
        url = reverse('search')
        response = self.client.get(url, {'q': 'test'})
        
        # Check response
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'search/search.html')
        
        # Check that results include our test items
        self.assertContains(response, 'Test Work Item')
        self.assertContains(response, 'Test Thread')
        
        # Check if search was logged
        self.assertTrue(SearchLog.objects.filter(user=self.user1, query='test').exists())
    
    def test_search_view_with_filters(self):
        """Test search view with filters."""
        url = reverse('search')
        response = self.client.get(url, {'q': 'test', 'type': 'task'})
        
        # Check that only task items are in results
        self.assertContains(response, 'Test Work Item')  # This is a task
        self.assertNotContains(response, 'Another Work Item')  # This is a project
    
    def test_search_view_content_type_filter(self):
        """Test search view with content type filters."""
        url = reverse('search')
        response = self.client.get(url, {'q': 'searchable', 'content_types': ['message']})
        
        # Check that only messages are in results
        self.assertContains(response, 'Message in thread with searchable content')
        self.assertContains(response, 'Test message with searchable content')
        
        # Check if file appears (it shouldn't with message filter)
        self.assertNotContains(response, 'searchable_file.txt')
    
    def test_search_view_ajax_request(self):
        """Test search view with AJAX request."""
        url = reverse('search')
        response = self.client.get(
            url, 
            {'q': 'test'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        # Check response
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        
        # Parse JSON response
        data = json.loads(response.content)
        
        # Check that response contains expected fields
        self.assertIn('html', data)
        self.assertIn('total', data)
        self.assertIn('work_items', data)
        self.assertIn('messages', data)
        self.assertIn('files', data)
        self.assertIn('threads', data)
    
    def test_search_view_no_results(self):
        """Test search view with no results."""
        url = reverse('search')
        response = self.client.get(url, {'q': 'nonexistentterm'})
        
        # Should return 200 but with no results
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No results found')
        
        # Search log should still be created
        self.assertTrue(
            SearchLog.objects.filter(
                user=self.user1, 
                query='nonexistentterm',
                results_count=0
            ).exists()
        )
    
    def test_saved_search_list_view(self):
        """Test the saved searches list view."""
        url = reverse('saved_searches')
        response = self.client.get(url)
        
        # Check response
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'search/saved_searches.html')
        
        # Check that saved search is in context
        self.assertIn(self.saved_search, response.context['saved_searches'])
    
    def test_saved_search_detail_view(self):
        """Test using a saved search."""
        url = reverse('saved_search_detail', args=[self.saved_search.slug])
        response = self.client.get(url)
        
        # Check that it redirects to search view with parameters
        self.assertRedirects(
            response, 
            f"{reverse('search')}?q=test&type=task", 
            fetch_redirect_response=False
        )
    
    def test_create_saved_search(self):
        """Test creating a saved search."""
        url = reverse('saved_searches')
        data = {
            'name': 'New Saved Search',
            'is_default': False
        }
        
        # Create search log to simulate previous search
        SearchLog.objects.create(
            user=self.user1,
            query='recent query',
            filters=json.dumps({'type': 'doc'}),
            results_count=3
        )
        
        response = self.client.post(url, data)
        
        # Check redirect
        self.assertRedirects(response, url)
        
        # Check that saved search was created
        self.assertTrue(SavedSearch.objects.filter(user=self.user1, name='New Saved Search').exists())
    
    def test_delete_saved_search(self):
        """Test deleting a saved search."""
        url = reverse('delete_saved_search', args=[self.saved_search.id])
        response = self.client.post(url)
        
        # Check redirect
        self.assertRedirects(response, reverse('saved_searches'))
        
        # Check that saved search was deleted
        self.assertFalse(SavedSearch.objects.filter(id=self.saved_search.id).exists())
    
    def test_set_default_search(self):
        """Test setting a search as default."""
        # Create a second non-default search
        saved_search2 = SavedSearch.objects.create(
            user=self.user1,
            name='Second Search',
            query='second',
            filters='{}',
            is_default=False
        )
        
        url = reverse('set_default_search', args=[saved_search2.id])
        response = self.client.post(url)
        
        # Check redirect
        self.assertRedirects(response, reverse('saved_searches'))
        
        # Refresh from DB
        saved_search2.refresh_from_db()
        self.saved_search.refresh_from_db()
        
        # Check that second search is now default
        self.assertTrue(saved_search2.is_default)
        self.assertFalse(self.saved_search.is_default)
    
    def test_clear_search_history(self):
        """Test clearing search history."""
        # Create some search logs
        SearchLog.objects.create(
            user=self.user1,
            query='query1',
            filters='{}',
            results_count=5
        )
        SearchLog.objects.create(
            user=self.user1,
            query='query2',
            filters='{}',
            results_count=3
        )
        
        url = reverse('clear_search_history')
        response = self.client.post(url)
        
        # Check redirect
        self.assertRedirects(response, reverse('search'))
        
        # Check that search logs were deleted
        self.assertEqual(SearchLog.objects.filter(user=self.user1).count(), 0)


class SearchFormsTests(TestCase):
    """Tests for search forms."""
    
    def test_advanced_search_form_fields(self):
        """Test that advanced search form has expected fields."""
        form = AdvancedSearchForm()
        
        # Check that form has expected fields
        self.assertIn('content_types', form.fields)
        self.assertIn('type', form.fields)
        self.assertIn('user', form.fields)
        self.assertIn('owner', form.fields)
        self.assertIn('date_from', form.fields)
        self.assertIn('date_to', form.fields)
        self.assertIn('recent', form.fields)
        self.assertIn('thread', form.fields)
        self.assertIn('visibility', form.fields)
        self.assertIn('file_type', form.fields)
        self.assertIn('channel_type', form.fields)
    
    def test_advanced_search_form_validation(self):
        """Test advanced search form validation."""
        # Test with valid data
        form = AdvancedSearchForm({
            'content_types': ['work_item', 'message'],
            'type': 'task',
            'recent': '7'
        })
        
        self.assertTrue(form.is_valid())
        
        # All fields are optional, so empty form should also validate
        empty_form = AdvancedSearchForm({})
        self.assertTrue(empty_form.is_valid())
    
    def test_saved_search_form_fields(self):
        """Test that saved search form has expected fields."""
        form = SavedSearchForm()
        
        # Check that form has expected fields
        self.assertIn('name', form.fields)
        self.assertIn('is_default', form.fields)
    
    def test_saved_search_form_validation(self):
        """Test saved search form validation."""
        # Test with valid data
        form = SavedSearchForm({
            'name': 'Test Search',
            'is_default': True
        })
        
        self.assertTrue(form.is_valid())
        
        # Test with invalid data (name too short)
        form = SavedSearchForm({
            'name': 'Te',
            'is_default': False
        })
        
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)


class SearchTemplateTagsTests(TestCase):
    """Tests for search template tags."""
    
    def test_highlight_filter(self):
        """Test the highlight template filter."""
        text = "This is a test message with important content."
        query = "test important"
        
        highlighted = highlight(text, query)
        
        # Both "test" and "important" should be highlighted
        self.assertIn('<span class="highlight">test</span>', highlighted)
        self.assertIn('<span class="highlight">important</span>', highlighted)
    
    def test_highlight_filter_with_empty_query(self):
        """Test the highlight filter with empty query."""
        text = "This is a test."
        query = ""
        
        # Should return original text
        self.assertEqual(highlight(text, query), text)
    
    def test_truncate_middle_filter(self):
        """Test the truncate_middle template filter."""
        text = "This is a very long text that should be truncated in the middle for display purposes."
        
        truncated = truncate_middle(text, 30)
        
        # Length should be approximately 30 plus the length of "..."
        self.assertLessEqual(len(truncated), 33)
        self.assertIn('...', truncated)
        
        # Start and end should be preserved
        self.assertTrue(truncated.startswith("This is"))
        self.assertTrue(truncated.endswith("purposes."))
    
    def test_truncate_middle_filter_with_short_text(self):
        """Test the truncate_middle filter with text shorter than limit."""
        text = "Short text."
        
        # Should return original text
        self.assertEqual(truncate_middle(text, 20), text)
    
    def test_file_icon_class_filter(self):
        """Test the file_icon_class template filter."""
        # Test different file types
        self.assertIn('fa-file-word', file_icon_class('document.docx'))
        self.assertIn('fa-file-excel', file_icon_class('spreadsheet.xlsx'))
        self.assertIn('fa-file-pdf', file_icon_class('document.pdf'))
        self.assertIn('fa-file-image', file_icon_class('image.jpg'))
        self.assertIn('fa-file-archive', file_icon_class('archive.zip'))
        self.assertIn('fa-file-audio', file_icon_class('audio.mp3'))
        self.assertIn('fa-file-video', file_icon_class('video.mp4'))
        self.assertIn('fa-file-code', file_icon_class('code.py'))
        self.assertIn('fa-file-alt', file_icon_class('text.txt'))
        
        # Default for unknown extension
        self.assertIn('fa-file', file_icon_class('unknown.xyz'))


class IndexCommandTests(TestCase):
    """Tests for the management command for file indexing."""
    
    @patch('search.management.commands.index_files.index_all_files')
    def test_index_all_command(self, mock_index_all):
        """Test the index_files command with --all argument."""
        mock_index_all.return_value = (5, 1)  # 5 indexed, 1 failed
        
        from django.core.management import call_command
        
        # Call the command
        call_command('index_files', all=True)
        
        # Check that index_all_files was called
        mock_index_all.assert_called_once()
    
    @patch('search.management.commands.index_files.reindex_file')
    def test_reindex_command(self, mock_reindex):
        """Test the index_files command with --reindex argument."""
        mock_reindex.return_value = True
        
        # Create test data
        user = User.objects.create_user('testuser', 'test@example.com', 'password')
        work_item = WorkItem.objects.create(
            title='Test Work Item',
            description='Test description',
            type='task',
            owner=user
        )
        
        # Create a test file
        test_file = SimpleUploadedFile(
            name='test_file.txt',
            content=b'Test content',
            content_type='text/plain'
        )
        
        file_attachment = FileAttachment.objects.create(
            work_item=work_item,
            file=test_file,
            name='test_file.txt',
            uploaded_by=user
        )
        
        from django.core.management import call_command
        
        # Call the command
        call_command('index_files', reindex=True)
        
        # Check that reindex_file was called for each file
        self.assertEqual(mock_reindex.call_count, 1)
    
    @patch('search.management.commands.index_files.reindex_file')
    def test_file_id_command(self, mock_reindex):
        """Test the index_files command with --file-id argument."""
        mock_reindex.return_value = True
        
        # Create test data
        user = User.objects.create_user('testuser', 'test@example.com', 'password')
        work_item = WorkItem.objects.create(
            title='Test Work Item',
            description='Test description',
            type='task',
            owner=user
        )
        
        # Create a test file
        test_file = SimpleUploadedFile(
            name='test_file.txt',
            content=b'Test content',
            content_type='text/plain'
        )
        
        file_attachment = FileAttachment.objects.create(
            work_item=work_item,
            file=test_file,
            name='test_file.txt',
            uploaded_by=user
        )
        
        from django.core.management import call_command
        
        # Call the command
        call_command('index_files', file_id=file_attachment.id)
        
        # Check that reindex_file was called with the correct file ID
        mock_reindex.assert_called_once_with(file_attachment.id)