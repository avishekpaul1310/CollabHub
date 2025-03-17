from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from .models import WorkItem, Message

class WorkItemModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Set up non-modified objects used by all test methods
        test_user = User.objects.create_user(username='testuser', password='12345')
        WorkItem.objects.create(
            title='Test Work Item',
            description='This is a test description',
            type='task',
            owner=test_user
        )

    def test_work_item_content(self):
        work_item = WorkItem.objects.get(id=1)
        self.assertEqual(work_item.title, 'Test Work Item')
        self.assertEqual(work_item.description, 'This is a test description')
        self.assertEqual(work_item.type, 'task')
        self.assertEqual(work_item.owner.username, 'testuser')

class WorkItemViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Create users
        test_user1 = User.objects.create_user(username='testuser1', password='12345')
        test_user2 = User.objects.create_user(username='testuser2', password='12345')
        
        # Create work items
        WorkItem.objects.create(
            title='Test Work Item 1',
            description='This is a test description 1',
            type='task',
            owner=test_user1
        )
        
        work_item2 = WorkItem.objects.create(
            title='Test Work Item 2',
            description='This is a test description 2',
            type='doc',
            owner=test_user2
        )
        work_item2.collaborators.add(test_user1)

    def test_redirect_if_not_logged_in(self):
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, '/login/?next=/')

    def test_logged_in_user_can_access_own_work_item(self):
        self.client.login(username='testuser1', password='12345')
        response = self.client.get(reverse('work_item_detail', kwargs={'pk': 1}))
        self.assertEqual(response.status_code, 200)

    def test_logged_in_user_can_see_collaborator_work_item(self):
        self.client.login(username='testuser1', password='12345')
        response = self.client.get(reverse('work_item_detail', kwargs={'pk': 2}))
        self.assertEqual(response.status_code, 200)

    def test_logged_in_user_cannot_access_other_work_item(self):
        self.client.login(username='testuser2', password='12345')
        response = self.client.get(reverse('work_item_detail', kwargs={'pk': 1}))
        self.assertEqual(response.status_code, 302)  # Redirect due to permission check