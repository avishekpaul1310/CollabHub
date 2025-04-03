from django.test import TestCase, Client, RequestFactory
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.utils.text import slugify
from django.db.models import Q

import json
import datetime
import tempfile
import os
from unittest.mock import patch, MagicMock

from workspace.models import WorkItem, Message, Thread, FileAttachment, SlowChannel
from search.models import SavedSearch, SearchLog, FileIndex
from search.forms import AdvancedSearchForm, SavedSearchForm, FileIndexForm
from search.views import search_view, index_file, search_work_items, search_messages, search_files, search_threads
from search.indexing import extract_text_from_file_in_chunks


class SearchModelsTests(TestCase):
    """Tests for Search-related models"""
    
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
        
        self.file = FileAttachment.objects.create(
            work_item=self.work_item,
            file=SimpleUploadedFile("test.txt", b"This is test content"),
            name="test.txt",
            uploaded_by=self.user
        )
    
    def test_saved_search_creation(self):
        """Test creating a SavedSearch model"""
        saved_search = SavedSearch.objects.create(
            user=self.user,
            name='Test Search',
            query='test query',
            filters=json.dumps({'type': 'task'})
        )
        
        self.assertEqual(saved_search.user, self.user)
        self.assertEqual(saved_search.name, 'Test Search')
        self.assertEqual(saved_search.query, 'test query')
        self.assertEqual(saved_search.get_filters(), {'type': 'task'})
        self.assertIsNotNone(saved_search.slug)
        self.assertFalse(saved_search.is_default)
    
    def test_saved_search_slug_generation(self):
        """Test that a unique slug is generated for each saved search"""
        saved_search1 = SavedSearch.objects.create(
            user=self.user,
            name='Test Search',
            query='test query',
            filters='{}'
        )
        
        saved_search2 = SavedSearch.objects.create(
            user=self.user,
            name='Test Search',  # Same name
            query='different query',
            filters='{}'
        )
        
        # Slugs should be different
        self.assertNotEqual(saved_search1.slug, saved_search2.slug)
        self.assertEqual(saved_search1.slug, slugify(saved_search1.name))
        self.assertTrue(saved_search2.slug.startswith(slugify(saved_search2.name)))
    
    def test_saved_search_default_setting(self):
        """Test that setting a saved search as default unsets other defaults"""
        saved_search1 = SavedSearch.objects.create(
            user=self.user,
            name='Default Search',
            query='default',
            filters='{}',
            is_default=True
        )
        
        saved_search2 = SavedSearch.objects.create(
            user=self.user,
            name='Another Search',
            query='another',
            filters='{}'
        )
        
        # First search should be default
        saved_search1.refresh_from_db()
        saved_search2.refresh_from_db()
        self.assertTrue(saved_search1.is_default)
        self.assertFalse(saved_search2.is_default)
        
        # Set second search as default
        saved_search2.is_default = True
        saved_search2.save()
        
        # First search should no longer be default
        saved_search1.refresh_from_db()
        saved_search2.refresh_from_db()
        self.assertFalse(saved_search1.is_default)
        self.assertTrue(saved_search2.is_default)
    
    def test_search_log_creation(self):
        """Test creating a SearchLog model"""
        search_log = SearchLog.objects.create(
            user=self.user,
            query='test query',
            filters=json.dumps({'type': 'task'}),
            results_count=5
        )
        
        self.assertEqual(search_log.user, self.user)
        self.assertEqual(search_log.query, 'test query')
        self.assertEqual(search_log.get_filters(), {'type': 'task'})
        self.assertEqual(search_log.results_count, 5)
    
    def test_search_log_ordering(self):
        """Test that search logs are ordered by timestamp (newest first)"""
        # Create an older log
        older_log = SearchLog.objects.create(
            user=self.user,
            query='older query',
            results_count=3
        )
        
        # Set timestamp to be older
        older_time = timezone.now() - datetime.timedelta(days=1)
        SearchLog.objects.filter(pk=older_log.pk).update(timestamp=older_time)
        
        # Create a newer log
        newer_log = SearchLog.objects.create(
            user=self.user,
            query='newer query',
            results_count=7
        )
        
        # Get logs ordered by default ordering
        logs = SearchLog.objects.filter(user=self.user)
        
        # The newest log should be first
        self.assertEqual(logs[0], newer_log)
        self.assertEqual(logs[1], older_log)
    
    def test_file_index_creation(self):
        """Test creating a FileIndex model"""
        file_index = FileIndex.objects.create(
            file=self.file,
            extracted_text='This is extracted text from the file',
            file_type='.txt'
        )
        
        self.assertEqual(file_index.file, self.file)
        self.assertEqual(file_index.extracted_text, 'This is extracted text from the file')
        self.assertEqual(file_index.file_type, '.txt')
    
    def test_file_index_str_representation(self):
        """Test the string representation of FileIndex"""
        file_index = FileIndex.objects.create(
            file=self.file,
            extracted_text='This is extracted text'
        )
        
        expected = f"Index for {self.file.name}"
        self.assertEqual(str(file_index), expected)


class SearchFormsTests(TestCase):
    """Tests for Search-related forms"""
    
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
        
        self.saved_search = SavedSearch.objects.create(
            user=self.user,
            name='Test Search',
            query='test query',
            filters=json.dumps({'type': 'task'})
        )
        
        self.file = FileAttachment.objects.create(
            work_item=self.work_item,
            file=SimpleUploadedFile("test.txt", b"This is test content"),
            name="test.txt",
            uploaded_by=self.user
        )
    
    def test_advanced_search_form_valid(self):
        """Test AdvancedSearchForm with valid data"""
        form_data = {
            'content_types': ['work_item', 'message'],
            'type': 'task',
            'user': 'testuser',
            'date_from': '2023-01-01',
            'date_to': '2023-12-31'
        }
        
        form = AdvancedSearchForm(data=form_data)
        self.assertTrue(form.is_valid())
        
        # Check cleaned data
        self.assertEqual(form.cleaned_data['content_types'], ['work_item', 'message'])
        self.assertEqual(form.cleaned_data['type'], 'task')
        self.assertEqual(form.cleaned_data['user'], 'testuser')
        self.assertEqual(
            form.cleaned_data['date_from'].strftime('%Y-%m-%d'), 
            '2023-01-01'
        )
    
    def test_advanced_search_form_with_no_data(self):
        """Test AdvancedSearchForm with no data should still be valid"""
        form = AdvancedSearchForm(data={})
        self.assertTrue(form.is_valid())
    
    def test_saved_search_form_valid(self):
        """Test SavedSearchForm with valid data"""
        form_data = {
            'name': 'New Saved Search',
            'is_default': True
        }
        
        form = SavedSearchForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_saved_search_form_invalid_name_too_short(self):
        """Test SavedSearchForm with a name that's too short"""
        form_data = {
            'name': 'AB',  # Less than 3 characters
        }
        
        form = SavedSearchForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)
    
    def test_file_index_form_valid(self):
        """Test FileIndexForm with valid data"""
        form_data = {
            'file_id': self.file.pk,
            'reindex': True
        }
        
        form = FileIndexForm(data=form_data)
        self.assertTrue(form.is_valid())


class SearchIndexingTests(TestCase):
    """Tests for search indexing functionality"""
    
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
        
        # Create a temporary text file for testing
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.txt', delete=False)
        self.temp_file.write(b"This is a test file content for indexing tests")
        self.temp_file.close()
        
        # Create file attachment with the temp file
        with open(self.temp_file.name, 'rb') as f:
            self.file = FileAttachment.objects.create(
                work_item=self.work_item,
                file=SimpleUploadedFile("test.txt", f.read()),
                name="test.txt",
                uploaded_by=self.user
            )
    
    def tearDown(self):
        """Clean up temporary files"""
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)
    
    @patch('search.indexing.extract_text_from_file_in_chunks')
    def test_index_file(self, mock_extract):
        """Test indexing a file"""
        # Set up mock to return test content
        mock_extract.return_value = "Extracted text content"
        
        # Call index_file function
        from search.indexing import index_file
        result = index_file(self.file)
        
        # Should return True for successful indexing
        self.assertTrue(result)
        
        # Check that a FileIndex was created
        self.assertTrue(FileIndex.objects.filter(file=self.file).exists())
        
        # Check the extracted text
        file_index = FileIndex.objects.get(file=self.file)
        self.assertEqual(file_index.extracted_text, "Extracted text content")
        self.assertEqual(file_index.file_type, ".txt")
        
        # Verify extract_text_from_file_in_chunks was called
        mock_extract.assert_called_once()
    
    def test_extract_text_from_file_in_chunks(self):
        """Test extracting text from a file in chunks"""
        # Create a test file with some text
        test_content = b"This is test content for extraction"
        test_file = SimpleUploadedFile("extract_test.txt", test_content)
        
        file_attachment = FileAttachment.objects.create(
            work_item=self.work_item,
            file=test_file,
            name="extract_test.txt",
            uploaded_by=self.user
        )
        
        # Mock the storage interface
        with patch('search.indexing.default_storage.open') as mock_open:
            # Create a mock file object
            mock_file = MagicMock()
            mock_file.read.side_effect = [test_content, b""]  # Return content then EOF
            mock_open.return_value = mock_file
            
            # Call the function
            result = extract_text_from_file_in_chunks(file_attachment)
            
            # Check result
            self.assertEqual(result, "This is test content for extraction")
            
            # Verify file was opened and read
            mock_open.assert_called_once()
            self.assertEqual(mock_file.read.call_count, 2)  # Called twice (content + EOF)
    
    @patch('search.indexing.index_file')
    def test_index_all_files(self, mock_index):
        """Test indexing all unindexed files"""
        # Set up mock to return True (success)
        mock_index.return_value = True
        
        # Create a second file
        second_file = FileAttachment.objects.create(
            work_item=self.work_item,
            file=SimpleUploadedFile("second.txt", b"Second file content"),
            name="second.txt",
            uploaded_by=self.user
        )
        
        # Call index_all_files function
        from search.indexing import index_all_files
        indexed_count, failed_count = index_all_files()
        
        # Should have indexed both files
        self.assertEqual(indexed_count, 2)
        self.assertEqual(failed_count, 0)
        
        # Verify index_file was called for both files
        self.assertEqual(mock_index.call_count, 2)
    
    @patch('search.indexing.index_file')
    def test_reindex_file(self, mock_index):
        """Test reindexing a specific file"""
        # Set up mock to return True (success)
        mock_index.return_value = True
        
        # Create a file index for the file
        file_index = FileIndex.objects.create(
            file=self.file,
            extracted_text="Old extracted text",
            file_type=".txt"
        )
        
        # Call reindex_file function
        from search.indexing import reindex_file
        result = reindex_file(self.file.pk)
        
        # Should return True for successful reindexing
        self.assertTrue(result)
        
        # Verify old index was deleted
        self.assertFalse(FileIndex.objects.filter(pk=file_index.pk).exists())
        
        # Verify index_file was called
        mock_index.assert_called_once_with(self.file)


class SearchViewTests(TestCase):
    """Tests for search views"""
    
    def setUp(self):
        """Set up test data and client"""
        self.client = Client()
        
        # Create users
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
        
        # Create work items with content to search
        self.work_item1 = WorkItem.objects.create(
            title='Project Alpha',
            description='This is a project about alpha testing',
            type='project',
            owner=self.user
        )
        self.work_item1.collaborators.add(self.collaborator)
        
        self.work_item2 = WorkItem.objects.create(
            title='Task Beta',
            description='This is a task for beta testing',
            type='task',
            owner=self.collaborator
        )
        self.work_item2.collaborators.add(self.user)
        
        # Create messages
        self.message1 = Message.objects.create(
            work_item=self.work_item1,
            user=self.user,
            content='Alpha version message about the project'
        )
        
        self.message2 = Message.objects.create(
            work_item=self.work_item2,
            user=self.collaborator,
            content='Beta version message about the task'
        )
        
        # Create threads
        self.thread1 = Thread.objects.create(
            title='Alpha Discussion',
            work_item=self.work_item1,
            created_by=self.user,
            is_public=True
        )
        
        self.thread2 = Thread.objects.create(
            title='Beta Discussion',
            work_item=self.work_item2,
            created_by=self.collaborator,
            is_public=False
        )
        self.thread2.allowed_users.add(self.user)
        
        # Create thread messages
        self.thread_message1 = Message.objects.create(
            work_item=self.work_item1,
            thread=self.thread1,
            user=self.user,
            content='Message in alpha thread',
            is_thread_starter=True
        )
        
        self.thread_message2 = Message.objects.create(
            work_item=self.work_item2,
            thread=self.thread2,
            user=self.collaborator,
            content='Message in beta thread',
            is_thread_starter=True
        )
        
        # Create files
        self.file1 = FileAttachment.objects.create(
            work_item=self.work_item1,
            file=SimpleUploadedFile("alpha.txt", b"Alpha file content"),
            name="alpha.txt",
            uploaded_by=self.user
        )
        
        self.file2 = FileAttachment.objects.create(
            work_item=self.work_item2,
            file=SimpleUploadedFile("beta.txt", b"Beta file content"),
            name="beta.txt",
            uploaded_by=self.collaborator
        )
        
        # Create file indices
        self.file_index1 = FileIndex.objects.create(
            file=self.file1,
            extracted_text="Alpha file content for searching",
            file_type=".txt"
        )
        
        self.file_index2 = FileIndex.objects.create(
            file=self.file2,
            extracted_text="Beta file content for searching",
            file_type=".txt"
        )
        
        # Create slow channels
        self.channel1 = SlowChannel.objects.create(
            title='Alpha Channel',
            description='Channel for alpha discussions',
            type='reflection',
            work_item=self.work_item1,
            created_by=self.user
        )
        self.channel1.participants.add(self.user)
        self.channel1.participants.add(self.collaborator)
        
        self.channel2 = SlowChannel.objects.create(
            title='Beta Channel',
            description='Channel for beta discussions',
            type='ideation',
            work_item=self.work_item2,
            created_by=self.collaborator
        )
        self.channel2.participants.add(self.user)
        self.channel2.participants.add(self.collaborator)
        
        # Create saved searches
        self.saved_search = SavedSearch.objects.create(
            user=self.user,
            name='Alpha Search',
            query='alpha',
            filters=json.dumps({'content_types': ['work_item', 'message']}),
            is_default=True
        )
        
        # URLs
        self.search_url = reverse('search')
        self.saved_searches_url = reverse('saved_searches')
        self.saved_search_detail_url = reverse('saved_search_detail', args=[self.saved_search.slug])
        self.delete_saved_search_url = reverse('delete_saved_search', args=[self.saved_search.pk])
        self.set_default_search_url = reverse('set_default_search', args=[self.saved_search.pk])
        self.clear_search_history_url = reverse('clear_search_history')
    
    def test_search_view_unauthenticated(self):
        """Test that unauthenticated user is redirected from search"""
        response = self.client.get(self.search_url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('login')))
    
    def test_search_view_authenticated_no_query(self):
        """Test search view for authenticated user with no query"""
        self.client.login(username='testuser', password='testpassword')
        response = self.client.get(self.search_url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'search/search.html')
        self.assertEqual(response.context['query'], '')
        self.assertEqual(response.context['total_results'], 0)
    
    def test_search_view_basic_query(self):
        """Test search view with a basic query"""
        self.client.login(username='testuser', password='testpassword')
        response = self.client.get(f"{self.search_url}?q=alpha")
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'search/search.html')
        self.assertEqual(response.context['query'], 'alpha')
        
        # Should find work items, messages, threads, and files with "alpha"
        results = response.context['results']
        self.assertTrue(len(results) > 0)
        
        # Check result types
        result_types = [r['type'] for r in results]
        self.assertIn('work_item', result_types)
        self.assertIn('message', result_types)
        self.assertIn('thread', result_types)
        self.assertIn('file', result_types)
        
        # Check counts
        self.assertEqual(response.context['work_items_count'], 1)  # work_item1
        self.assertEqual(response.context['messages_count'], 1)    # message1
        self.assertEqual(response.context['threads_count'], 1)     # thread1
        self.assertEqual(response.context['files_count'], 1)       # file1
    
    def test_search_view_with_content_type_filter(self):
        """Test search view with content type filter"""
        self.client.login(username='testuser', password='testpassword')
        response = self.client.get(f"{self.search_url}?q=alpha&content_types=work_item")
        
        self.assertEqual(response.status_code, 200)
        
        # Should only find work items with "alpha"
        results = response.context['results']
        self.assertTrue(all(r['type'] == 'work_item' for r in results))
        self.assertEqual(response.context['work_items_count'], 1)
        self.assertEqual(response.context['messages_count'], 0)
        self.assertEqual(response.context['threads_count'], 0)
        self.assertEqual(response.context['files_count'], 0)
    
    def test_search_view_with_type_filter(self):
        """Test search view with work item type filter"""
        self.client.login(username='testuser', password='testpassword')
        response = self.client.get(f"{self.search_url}?q=&type=project")
        
        self.assertEqual(response.status_code, 200)
        
        # Should find project type work items
        results = response.context['results']
        work_item_results = [r for r in results if r['type'] == 'work_item']
        self.assertTrue(all(r['object'].type == 'project' for r in work_item_results))
    
    def test_search_view_with_date_filter(self):
        """Test search view with date filter"""
        self.client.login(username='testuser', password='testpassword')
        
        # Create a work item with older date
        old_item = WorkItem.objects.create(
            title='Old Alpha Item',
            description='This is an old alpha item',
            type='task',
            owner=self.user
        )
        
        # Set created_at to be older
        old_date = timezone.now() - datetime.timedelta(days=100)
        WorkItem.objects.filter(pk=old_item.pk).update(created_at=old_date, updated_at=old_date)
        
        # Search with date filter for recent items
        yesterday = (timezone.now() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        response = self.client.get(f"{self.search_url}?q=alpha&date_from={yesterday}")
        
        self.assertEqual(response.status_code, 200)
        
        # Should only find recent items, not the old one
        results = response.context['results']
        work_item_ids = [r['object'].pk for r in results if r['type'] == 'work_item']
        self.assertIn(self.work_item1.pk, work_item_ids)
        self.assertNotIn(old_item.pk, work_item_ids)
    
    def test_search_work_items_function(self):
        """Test the search_work_items function directly"""
        # Search with query
        results = search_work_items(self.user, 'alpha')
        self.assertEqual(results.count(), 1)
        self.assertEqual(results.first(), self.work_item1)
        
        # Search with type filter
        results = search_work_items(self.user, '', {'type': 'project'})
        self.assertEqual(results.count(), 1)
        self.assertEqual(results.first(), self.work_item1)
        
        # Search with user/owner filter
        results = search_work_items(self.user, '', {'user': 'collaborator'})
        self.assertEqual(results.count(), 1)
        self.assertEqual(results.first(), self.work_item2)
    
    def test_search_messages_function(self):
        """Test the search_messages function directly"""
        # Search with query
        results = search_messages(self.user, 'alpha')
        self.assertEqual(results.count(), 1)
        self.assertEqual(results.first(), self.message1)
        
        # Search with thread filter (only thread messages)
        results = search_messages(self.user, '', {'thread': 'only'})
        self.assertEqual(results.count(), 2)  # Both thread messages
        
        # Search with thread filter (exclude thread messages)
        results = search_messages(self.user, '', {'thread': 'exclude'})
        self.assertEqual(results.count(), 2)  # Both non-thread messages
    
    def test_search_threads_function(self):
        """Test the search_threads function directly"""
        # Search with query
        results = search_threads(self.user, 'alpha')
        self.assertEqual(results.count(), 1)
        self.assertEqual(results.first(), self.thread1)
        
        # Search with visibility filter (public only)
        results = search_threads(self.user, '', {'visibility': 'public'})
        self.assertEqual(results.count(), 1)
        self.assertEqual(results.first(), self.thread1)
        
        # Search with visibility filter (private only)
        results = search_threads(self.user, '', {'visibility': 'private'})
        self.assertEqual(results.count(), 1)
        self.assertEqual(results.first(), self.thread2)
    
    def test_search_files_function(self):
        """Test the search_files function directly"""
        # Search with query in filename
        results = search_files(self.user, 'alpha')
        self.assertEqual(results.count(), 1)
        self.assertEqual(results.first(), self.file1)
        
        # Search with query in extracted text
        results = search_files(self.user, 'searching')
        self.assertEqual(results.count(), 2)  # Both files have "searching" in extracted text
        
        # Search with file type filter
        results = search_files(self.user, '', {'file_type': 'document'})
        self.assertEqual(results.count(), 2)  # Both are .txt files
    
    def test_saved_searches_view(self):
        """Test saved searches list view"""
        self.client.login(username='testuser', password='testpassword')
        response = self.client.get(self.saved_searches_url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'search/saved_searches.html')
        self.assertIn(self.saved_search, response.context['saved_searches'])
    
    def test_create_saved_search(self):
        """Test creating a new saved search"""
        self.client.login(username='testuser', password='testpassword')
        
        # First perform a search to store in session
        self.client.get(f"{self.search_url}?q=beta&type=task")
        
        # Then create a saved search based on that
        form_data = {
            'name': 'Beta Tasks Search',
            'is_default': False
        }
        
        response = self.client.post(self.saved_searches_url, form_data)
        
        # Should redirect to saved searches list
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.saved_searches_url)
        
        # Check that saved search was created
        new_search = SavedSearch.objects.filter(name='Beta Tasks Search').first()
        self.assertIsNotNone(new_search)
        self.assertEqual(new_search.query, 'beta')
        self.assertIn('type', new_search.get_filters())
        self.assertEqual(new_search.get_filters()['type'], 'task')
    
    def test_saved_search_detail_view(self):
        """Test viewing a saved search"""
        self.client.login(username='testuser', password='testpassword')
        response = self.client.get(self.saved_search_detail_url)
        
        # Should redirect to search with the saved parameters
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('search')))
        self.assertIn('q=alpha', response.url)
        self.assertIn('content_types=work_item', response.url)
        self.assertIn('content_types=message', response.url)
    
    def test_delete_saved_search(self):
        """Test deleting a saved search"""
        self.client.login(username='testuser', password='testpassword')
        response = self.client.post(self.delete_saved_search_url)
        
        # Should redirect to saved searches list
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.saved_searches_url)
        
        # Check that saved search was deleted
        self.assertFalse(SavedSearch.objects.filter(pk=self.saved_search.pk).exists())
    
    def test_set_default_search(self):
        """Test setting a saved search as default"""
        # Create a second saved search
        second_search = SavedSearch.objects.create(
            user=self.user,
            name='Second Search',
            query='second',
            filters='{}'
        )
        
        self.client.login(username='testuser', password='testpassword')
        response = self.client.post(reverse('set_default_search', args=[second_search.pk]))
        
        # Should redirect to saved searches list
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.saved_searches_url)
        
        # Check that second search is now default and first is not
        self.saved_search.refresh_from_db()
        second_search.refresh_from_db()
        self.assertFalse(self.saved_search.is_default)
        self.assertTrue(second_search.is_default)
    
    def test_clear_search_history(self):
        """Test clearing search history"""
        # Create some search logs
        SearchLog.objects.create(
            user=self.user,
            query='test query 1',
            results_count=5
        )
        
        SearchLog.objects.create(
            user=self.user,
            query='test query 2',
            results_count=10
        )
        
        self.client.login(username='testuser', password='testpassword')
        response = self.client.post(self.clear_search_history_url)
        
        # Should redirect to search
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.search_url)
        
        # Check that all search logs were deleted
        self.assertEqual(SearchLog.objects.filter(user=self.user).count(), 0)
    
    @patch('search.views.JsonResponse')
    def test_search_view_ajax(self, mock_json_response):
        """Test search view with AJAX request"""
        # Setup mock for JsonResponse
        mock_response = MagicMock()
        mock_json_response.return_value = mock_response
        
        # Setup request factory and request
        factory = RequestFactory()
        request = factory.get(f"{self.search_url}?q=alpha")
        request.user = self.user
        
        # Add AJAX header
        request.META['HTTP_X_REQUESTED_WITH'] = 'XMLHttpRequest'
        
        # Call the view
        response = search_view(request)
        
        # Check that JsonResponse was called
        mock_json_response.assert_called_once()
        
        # Extract call arguments
        call_args = mock_json_response.call_args[0][0]
        
        # Verify keys exist
        self.assertIn('html', call_args)
        self.assertIn('total', call_args)
        self.assertIn('work_items', call_args)
        self.assertIn('messages', call_args)
        self.assertIn('files', call_args)
        self.assertIn('threads', call_args)


class SearchCommandTests(TestCase):
    """Tests for management commands related to search"""
    
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
        
        self.file1 = FileAttachment.objects.create(
            work_item=self.work_item,
            file=SimpleUploadedFile("alpha.txt", b"Alpha file content"),
            name="alpha.txt",
            uploaded_by=self.user
        )
        
        self.file2 = FileAttachment.objects.create(
            work_item=self.work_item,
            file=SimpleUploadedFile("beta.txt", b"Beta file content"),
            name="beta.txt",
            uploaded_by=self.user
        )
        
        # Create a file index for file1
        self.file_index = FileIndex.objects.create(
            file=self.file1,
            extracted_text="Alpha file content for searching",
            file_type=".txt"
        )
    
    @patch('search.management.commands.index_files.index_all_files')
    def test_index_files_command_all(self, mock_index_all):
        """Test the index_files management command with --all option"""
        # Set up mock to return counts
        mock_index_all.return_value = (1, 0)
        
        # Call the command
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command('index_files', '--all', stdout=out)
        
        # Verify index_all_files was called
        mock_index_all.assert_called_once()
        
        # Check command output
        output = out.getvalue()
        self.assertIn('Indexing all unindexed files', output)
        self.assertIn('1 files indexed, 0 failed', output)
    
    @patch('search.management.commands.index_files.reindex_file')
    def test_index_files_command_reindex(self, mock_reindex):
        """Test the index_files management command with --reindex option"""
        # Set up mock to return True (success)
        mock_reindex.return_value = True
        
        # Call the command
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command('index_files', '--reindex', stdout=out)
        
        # Verify reindex_file was called for both files
        self.assertEqual(mock_reindex.call_count, 2)
        
        # Check command output
        output = out.getvalue()
        self.assertIn('Reindexing all files', output)
        self.assertIn('2 files indexed, 0 failed', output)
    
    @patch('search.management.commands.index_files.reindex_file')
    def test_index_files_command_file_id(self, mock_reindex):
        """Test the index_files management command with --file-id option"""
        # Set up mock to return True (success)
        mock_reindex.return_value = True
        
        # Call the command
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command('index_files', '--file-id', str(self.file1.pk), stdout=out)
        
        # Verify reindex_file was called for the specified file
        mock_reindex.assert_called_once_with(self.file1.pk)
        
        # Check command output
        output = out.getvalue()
        self.assertIn(f"Processing file: {self.file1.name}", output)
        self.assertIn(f"Successfully indexed file {self.file1.name}", output)


class SearchSignalTests(TestCase):
    """Tests for search signals"""
    
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
    
    @patch('search.signals.index_file')
    def test_file_attachment_create_signal(self, mock_index_file):
        """Test that creating a FileAttachment triggers indexing"""
        # Create a file attachment
        file = FileAttachment.objects.create(
            work_item=self.work_item,
            file=SimpleUploadedFile("test.txt", b"Test content"),
            name="test.txt",
            uploaded_by=self.user
        )
        
        # Verify index_file was called
        mock_index_file.assert_called_once_with(file)
    
    def test_file_attachment_delete_signal(self):
        """Test that deleting a FileAttachment deletes its index"""
        # Create a file attachment
        file = FileAttachment.objects.create(
            work_item=self.work_item,
            file=SimpleUploadedFile("test.txt", b"Test content"),
            name="test.txt",
            uploaded_by=self.user
        )
        
        # Create a file index
        file_index = FileIndex.objects.create(
            file=file,
            extracted_text="Test content for indexing",
            file_type=".txt"
        )
        
        # Delete the file attachment
        file_pk = file.pk
        file.delete()
        
        # Check that the file index was also deleted
        self.assertFalse(FileIndex.objects.filter(file_id=file_pk).exists())


class SearchTemplateTagsTests(TestCase):
    """Tests for search template tags"""
    
    def setUp(self):
        """Set up test data"""
        from django.template import Template, Context
        self.template = Template
        self.context = Context
    
    def test_split_filter(self):
        """Test the split template filter"""
        template = self.template(
            '{% load search_filters %}'
            '{% for part in "a,b,c"|split:"," %}'
            '{{ part }}'
            '{% endfor %}'
        )
        rendered = template.render(self.context())
        self.assertEqual(rendered, 'abc')
    
    def test_highlight_filter(self):
        """Test the highlight template filter"""
        template = self.template(
            '{% load search_filters %}'
            '{{ "This is a test phrase with test words"|highlight:"test" }}'
        )
        rendered = template.render(self.context())
        expected = 'This is a <span class="highlight">test</span> phrase with <span class="highlight">test</span> words'
        self.assertEqual(rendered, expected)
    
    def test_truncate_middle_filter(self):
        """Test the truncate_middle template filter"""
        template = self.template(
            '{% load search_filters %}'
            '{{ "This is a very long text that should be truncated in the middle"|truncate_middle:20 }}'
        )
        rendered = template.render(self.context())
        self.assertEqual(rendered, 'This is a...e middle')
        self.assertTrue(len(rendered) <= 20 + 3)  # Length should be <= 23 (length + ellipsis)
    
    def test_file_icon_class_filter(self):
        """Test the file_icon_class template filter"""
        # Test various file types
        template = self.template(
            '{% load search_filters %}'
            '{{ "document.docx"|file_icon_class }}'
        )
        rendered = template.render(self.context())
        self.assertEqual(rendered, 'fa-file-word text-primary')
        
        template = self.template(
            '{% load search_filters %}'
            '{{ "image.jpg"|file_icon_class }}'
        )
        rendered = template.render(self.context())
        self.assertEqual(rendered, 'fa-file-image text-info')
        
        template = self.template(
            '{% load search_filters %}'
            '{{ "unknown.xyz"|file_icon_class }}'
        )
        rendered = template.render(self.context())
        self.assertEqual(rendered, 'fa-file text-muted')