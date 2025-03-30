from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from users.models import Profile
from users.forms import UserRegisterForm, UserUpdateForm, ProfileUpdateForm
from workspace.models import NotificationPreference, WorkItem, Notification
import datetime
import json
from unittest.mock import patch, MagicMock
from PIL import Image
import tempfile
import io

class UserModelTests(TestCase):
    """Tests for User model and related functionality."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
    
    def test_profile_creation(self):
        """Test that a profile is automatically created when a user is created."""
        self.assertTrue(hasattr(self.user, 'profile'))
        self.assertIsInstance(self.user.profile, Profile)
    
    def test_profile_str_representation(self):
        """Test the string representation of a Profile."""
        self.assertEqual(str(self.user.profile), 'testuser Profile')
    
    def test_notification_preference_creation(self):
        """Test that notification preferences are created with a new user."""
        self.assertTrue(hasattr(self.user, 'notification_preferences'))
        self.assertIsInstance(self.user.notification_preferences, NotificationPreference)
        
    def test_profile_default_image(self):
        """Test that profile is created with default image."""
        self.assertEqual(self.user.profile.avatar, 'default.png')
        
    def test_profile_bio_blank(self):
        """Test that profile is created with blank bio."""
        self.assertEqual(self.user.profile.bio, '')


class UserAuthenticationTests(TestCase):
    """Tests for user registration, login, and logout."""
    
    def setUp(self):
        self.client = Client()
        self.register_url = reverse('register')
        self.login_url = reverse('login')
        self.logout_url = reverse('logout')
        self.dashboard_url = reverse('dashboard')
        
        # Create a test user
        self.user = User.objects.create_user(
            username='existinguser', 
            email='existing@example.com',
            password='password123'
        )
    
    def test_register_view_get(self):
        """Test that the register page loads correctly."""
        response = self.client.get(self.register_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/register.html')
        self.assertIsInstance(response.context['form'], UserRegisterForm)
    
    def test_register_success(self):
        """Test successful user registration."""
        data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'complex_password123',
            'password2': 'complex_password123',
        }
        response = self.client.post(self.register_url, data)
        
        # Check that user was created
        self.assertEqual(User.objects.count(), 2)
        # Check redirect to login page
        self.assertRedirects(response, self.login_url)
        
        # Check profile was created
        user = User.objects.get(username='newuser')
        self.assertTrue(hasattr(user, 'profile'))
        
        # Check notification preferences were created
        self.assertTrue(hasattr(user, 'notification_preferences'))
    
    def test_register_password_mismatch(self):
        """Test registration with mismatched passwords."""
        data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'complex_password123',
            'password2': 'different_password',
        }
        response = self.client.post(self.register_url, data)
        
        # Form should display error and not create user
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 1)
        
        # Check if form has the expected error
        form = response.context.get('form')
        self.assertTrue(form.errors)
        self.assertIn('password2', form.errors)
        
        # Verify that the user wasn't created
        self.assertFalse(User.objects.filter(username='newuser').exists())
    
    def test_register_existing_username(self):
        """Test registration with an existing username."""
        data = {
            'username': 'existinguser',
            'email': 'new@example.com',
            'password1': 'complex_password123',
            'password2': 'complex_password123',
        }
        response = self.client.post(self.register_url, data)
        
        # Form should display error and not create another user
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 1)
        self.assertFormError(response, 'form', 'username', 'A user with that username already exists.')
    
    def test_login_success(self):
        """Test successful login."""
        data = {
            'username': 'existinguser',
            'password': 'password123',
        }
        response = self.client.post(self.login_url, data)
        
        # Check redirect to dashboard
        self.assertRedirects(response, self.dashboard_url)
        # Verify user is logged in
        self.assertTrue(response.wsgi_request.user.is_authenticated)
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials."""
        data = {
            'username': 'existinguser',
            'password': 'wrongpassword',
        }
        response = self.client.post(self.login_url, data)
        
        # Form should display error
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertContains(response, "Please enter a correct username and password")
    
    def test_logout(self):
        """Test logout functionality."""
        # Login first
        self.client.login(username='existinguser', password='password123')
        
        # Check that user is logged in
        self.assertTrue(self.client.session.get('_auth_user_id'))
        
        # Perform logout
        response = self.client.get(self.logout_url)
        
        # Check redirect to login page
        self.assertRedirects(response, self.login_url)
        
        # Verify user is logged out
        response = self.client.get(self.dashboard_url)
        self.assertRedirects(response, f'{self.login_url}?next={self.dashboard_url}')
        
    def test_login_template(self):
        """Test that login page uses correct template."""
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/login.html')
        
    def test_logout_template(self):
        """Test that logout page uses correct template."""
        # Login first
        self.client.login(username='existinguser', password='password123')
        
        # Access logout page
        response = self.client.get(self.logout_url)
        self.assertEqual(response.status_code, 302)  # Redirects
        
        # Follow redirect to ensure template is used
        response = self.client.get(self.logout_url, follow=True)
        self.assertTemplateUsed(response, 'users/logout.html')
        
    def test_password_reset_flow(self):
        """Test the password reset flow."""
        # This is simplified as we can't easily test email sending in unit tests
        # Just check that the views return correct status codes
        
        # Password reset request form
        reset_url = reverse('password_reset')
        response = self.client.get(reset_url)
        self.assertEqual(response.status_code, 200)
        
        # Password reset done page
        reset_done_url = reverse('password_reset_done')
        response = self.client.get(reset_done_url)
        self.assertEqual(response.status_code, 200)
        
        # Password reset confirm page (invalid token)
        reset_confirm_url = reverse('password_reset_confirm', 
                                   kwargs={'uidb64': 'invalid', 'token': 'invalid'})
        response = self.client.get(reset_confirm_url)
        self.assertEqual(response.status_code, 200)
        
        # Password reset complete page
        reset_complete_url = reverse('password_reset_complete')
        response = self.client.get(reset_complete_url)
        self.assertEqual(response.status_code, 200)


class UserProfileTests(TestCase):
    """Tests for user profile functionality."""
    
    def setUp(self):
        self.client = Client()
        self.profile_url = reverse('profile')
        self.login_url = reverse('login')
        
        # Create a test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        
        # Create a test avatar
        self.avatar = SimpleUploadedFile(
            name='test_avatar.jpg',
            content=b'',  # Empty content for testing
            content_type='image/jpeg'
        )
    
    def test_profile_login_required(self):
        """Test that profile view requires login."""
        response = self.client.get(self.profile_url)
        self.assertRedirects(response, f'{self.login_url}?next={self.profile_url}')
    
    def test_profile_view_get(self):
        """Test that the profile page loads correctly for logged in user."""
        self.client.login(username='testuser', password='password123')
        response = self.client.get(self.profile_url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/profile.html')
        self.assertIsInstance(response.context['u_form'], UserUpdateForm)
        self.assertIsInstance(response.context['p_form'], ProfileUpdateForm)
    
    def test_profile_update_basic_info(self):
        """Test updating a user's basic profile information."""
        self.client.login(username='testuser', password='password123')
        
        # Update profile with new data
        data = {
            'username': 'updated_user',
            'email': 'updated@example.com',
            'bio': 'This is my updated bio',
        }
        
        response = self.client.post(self.profile_url, data)
        
        # Refresh user from database
        self.user.refresh_from_db()
        
        # Check that user info was updated
        self.assertEqual(self.user.username, 'updated_user')
        self.assertEqual(self.user.email, 'updated@example.com')
        self.assertEqual(self.user.profile.bio, 'This is my updated bio')
    
    def test_profile_update_with_avatar(self):
        """Test updating a user's profile with an avatar image."""
        self.client.login(username='testuser', password='password123')
        
        # Create a valid image file
        image = Image.new('RGB', (100, 100))
        temp_file = tempfile.NamedTemporaryFile(suffix='.jpg')
        image.save(temp_file)
        temp_file.seek(0)
        
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'avatar': temp_file,
            'bio': 'Updated bio with new avatar'
        }
        
        response = self.client.post(self.profile_url, data, format='multipart')
        
        # Check the response
        self.assertEqual(response.status_code, 302)  # Redirects to profile page
        
        # Refresh user from database
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        
        # Check that bio was updated
        self.assertEqual(self.user.profile.bio, 'Updated bio with new avatar')
        
        # Check that avatar was updated
        self.assertNotEqual(self.user.profile.avatar, 'default.png')
        
    def test_profile_form_validation(self):
        """Test profile form validation."""
        self.client.login(username='testuser', password='password123')
        
        # Create another user for username conflict
        User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='password123'
        )
        
        # Try to update with existing username
        data = {
            'username': 'otheruser',  # This should fail
            'email': 'test@example.com',
        }
        
        response = self.client.post(self.profile_url, data)
        
        # Should show form with errors
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A user with that username already exists")
        
        # Verify original username was preserved
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'testuser')
        
    def test_profile_update_email_validation(self):
        """Test email validation in profile update."""
        self.client.login(username='testuser', password='password123')
        
        # Try to update with invalid email
        data = {
            'username': 'testuser',
            'email': 'invalid-email',  # Invalid email format
        }
        
        response = self.client.post(self.profile_url, data)
        
        # Should show form with errors
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid email address")
        
        # Verify original email was preserved
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'test@example.com')
        
    def test_profile_update_success_message(self):
        """Test that successful profile update shows a success message."""
        self.client.login(username='testuser', password='password123')
        
        data = {
            'username': 'testuser',
            'email': 'updated@example.com',
        }
        
        response = self.client.post(self.profile_url, data, follow=True)
        
        # Check for success message
        self.assertContains(response, "Your profile has been updated")


class NotificationPreferenceTests(TestCase):
    """Tests for user notification preferences."""
    
    def setUp(self):
        self.client = Client()
        self.preferences_url = reverse('notification_preferences')
        
        # Create users
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        
        # Log in
        self.client.login(username='testuser', password='password123')
        
        # Create work item for muting tests
        self.work_item = WorkItem.objects.create(
            title='Test Work Item',
            description='Test description',
            type='task',
            owner=self.user
        )
    
    def test_preferences_view_get(self):
        """Test that the notification preferences page loads correctly."""
        response = self.client.get(self.preferences_url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'workspace/notification_preferences.html')
    
    def test_preferences_view_login_required(self):
        """Test that notification preferences view requires login."""
        # Log out
        self.client.logout()
        
        response = self.client.get(self.preferences_url)
        
        # Should redirect to login
        self.assertRedirects(response, f'{reverse("login")}?next={self.preferences_url}')
    
    def test_update_notification_mode(self):
        """Test updating notification mode."""
        data = {
            'notification_mode': 'mentions',
            'dnd_enabled': False,
            'work_days': '12345',  # Monday through Friday
            'work_start_time': '09:00',
            'work_end_time': '17:00',
            'show_online_status': False,
            'share_read_receipts': True
        }
        
        response = self.client.post(self.preferences_url, data)
        
        # Should redirect back to preferences page
        self.assertRedirects(response, self.preferences_url)
        
        # Refresh from database
        self.user.notification_preferences.refresh_from_db()
        
        # Check that preferences were updated
        self.assertEqual(self.user.notification_preferences.notification_mode, 'mentions')
    
    def test_update_dnd_settings(self):
        """Test updating Do Not Disturb settings."""
        data = {
            'notification_mode': 'all',
            'dnd_enabled': True,
            'dnd_start_time': '22:00',
            'dnd_end_time': '08:00',
            'work_days': '12345',
            'work_start_time': '09:00',
            'work_end_time': '17:00',
            'show_online_status': False,
            'share_read_receipts': True
        }
        
        response = self.client.post(self.preferences_url, data)
        
        # Refresh from database
        self.user.notification_preferences.refresh_from_db()
        
        # Check that preferences were updated
        self.assertTrue(self.user.notification_preferences.dnd_enabled)
        self.assertEqual(str(self.user.notification_preferences.dnd_start_time), '22:00:00')
        self.assertEqual(str(self.user.notification_preferences.dnd_end_time), '08:00:00')
    
    def test_update_work_hours(self):
        """Test updating work hours settings."""
        data = {
            'notification_mode': 'all',
            'dnd_enabled': False,
            'work_days': '135',  # Monday, Wednesday, Friday
            'work_start_time': '10:00',
            'work_end_time': '16:00',
            'show_online_status': False,
            'share_read_receipts': True
        }
        
        response = self.client.post(self.preferences_url, data)
        
        # Refresh from database
        self.user.notification_preferences.refresh_from_db()
        
        # Check work days
        self.assertEqual(self.user.notification_preferences.work_days, '135')
        
        # Check work hours
        self.assertEqual(str(self.user.notification_preferences.work_start_time), '10:00:00')
        self.assertEqual(str(self.user.notification_preferences.work_end_time), '16:00:00')
    
    def test_update_async_settings(self):
        """Test updating asynchronous communication settings."""
        data = {
            'notification_mode': 'all',
            'dnd_enabled': False,
            'work_days': '12345',
            'work_start_time': '09:00',
            'work_end_time': '17:00',
            'show_online_status': True,
            'share_read_receipts': False
        }
        
        response = self.client.post(self.preferences_url, data)
        
        # Refresh from database
        self.user.notification_preferences.refresh_from_db()
        
        # Check that preferences were updated
        self.assertTrue(self.user.notification_preferences.show_online_status)
        self.assertFalse(self.user.notification_preferences.share_read_receipts)
    
    def test_toggle_mute_work_item(self):
        """Test toggling mute status for a work item."""
        # First, check the work item is not muted
        self.assertFalse(self.user.notification_preferences.muted_channels.filter(id=self.work_item.id).exists())
        
        # Toggle mute on
        url = reverse('toggle_mute_work_item', args=[self.work_item.id])
        response = self.client.post(
            url, 
            {},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        # Check response and that work item is now muted
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        
        # Check all notifications were marked as read
        self.notification1.refresh_from_db()
        self.notification2.refresh_from_db()
        self.assertTrue(self.notification1.is_read)
        self.assertTrue(self.notification2.is_read)
    
    def test_unread_notifications_count(self):
        """Test the unread notifications count."""
        # Initially both notifications are unread
        response = self.client.get(reverse('dashboard'))
        
        # Check that unread count is shown
        self.assertContains(response, 'unread_notifications_count')
        
        # Mark one as read
        self.notification1.is_read = True
        self.notification1.save()
        
        # Check count again
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['unread_notifications_count'], 1)
        
        # Mark all as read
        self.notification2.is_read = True
        self.notification2.save()
        
        # Check count again
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['unread_notifications_count'], 0)
    
    def test_notification_for_other_user(self):
        """Test that a user can't mark another user's notification as read."""
        # Create a notification for user2
        notification = Notification.objects.create(
            user=self.user2,
            message='Notification for user2',
            work_item=self.work_item,
            notification_type='message'
        )
        
        # Try to mark it as read as user1
        url = reverse('mark_notification_read', args=[notification.id])
        response = self.client.get(url)
        
        # Should return 404 as it doesn't "exist" for this user
        self.assertEqual(response.status_code, 404)
        
        # Notification should still be unread
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)
    
    def test_notification_types(self):
        """Test different notification types."""
        # Check that initial notifications have correct types
        self.assertEqual(self.notification1.notification_type, 'message')
        self.assertEqual(self.notification2.notification_type, 'update')
        
        # Create a file upload notification
        file_notification = Notification.objects.create(
            user=self.user1,
            message='New file uploaded',
            work_item=self.work_item,
            notification_type='file_upload'
        )
        
        self.assertEqual(file_notification.notification_type, 'file_upload')
        
        # Check that notifications list shows different icons for different types
        url = reverse('notifications_list')
        response = self.client.get(url)
        
        # This checks that the template is using the notification type to display different icons
        self.assertContains(response, 'fa-comment')  # For message notifications
        self.assertContains(response, 'fa-edit')     # For update notifications
        self.assertContains(response, 'fa-file-upload')  # For file upload notifications
    
    def test_notification_work_item_link(self):
        """Test that notifications link to the related work item."""
        url = reverse('notifications_list')
        response = self.client.get(url)
        
        # Check that notifications link to the work item
        work_item_url = reverse('work_item_detail', args=[self.work_item.pk])
        self.assertContains(response, f'href="{work_item_url}"')
    
    def test_notification_dropdown(self):
        """Test the notification dropdown in the navbar."""
        response = self.client.get(reverse('dashboard'))
        
        # Check that dropdown elements exist
        self.assertContains(response, 'id="notificationDropdown"')
        self.assertContains(response, 'fa-bell')  # Bell icon
        
        # With unread notifications, should show badge with count
        self.assertContains(response, 'badge bg-danger')
        
        # Mark all as read
        self.client.get(reverse('mark_all_read'))
        
        # Without unread notifications, should not show badge
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, 'badge bg-danger')


class OnlineStatusTests(TestCase):
    """Tests for online status API functionality."""
    
    def setUp(self):
        self.client = Client()
        
        # Create user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        
        # Set online status preference
        prefs = self.user.notification_preferences
        prefs.show_online_status = True
        prefs.save()
        
        # Login
        self.client.login(username='testuser', password='password123')
    
    def test_get_online_status_preference(self):
        """Test retrieving user's online status preference."""
        url = reverse('get_online_status_preference')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertTrue(data['show_online_status'])
        
        # Test after disabling online status
        prefs = self.user.notification_preferences
        prefs.show_online_status = False
        prefs.save()
        
        response = self.client.get(url)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertFalse(data['show_online_status'])
    
    def test_update_online_status(self):
        """Test updating user's online status."""
        url = reverse('update_online_status')
        
        # Test with valid data
        response = self.client.post(
            url,
            json.dumps({'status': 'active'}),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['online_status'], 'active')
        
        # Test with online status disabled
        prefs = self.user.notification_preferences
        prefs.show_online_status = False
        prefs.save()
        
        response = self.client.post(
            url,
            json.dumps({'status': 'active'}),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'error')
    
    def test_get_other_user_online_status(self):
        """Test retrieving another user's online status."""
        # Create another user with online status enabled
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='password123'
        )
        
        other_prefs = other_user.notification_preferences
        other_prefs.show_online_status = True
        other_prefs.save()
        
        url = reverse('get_user_online_status', args=[other_user.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        
        # Check user IDs match
        self.assertEqual(int(data['user_id']), other_user.id)
        self.assertEqual(data['username'], other_user.username)
        
        # Test with user who has disabled online status
        other_prefs.show_online_status = False
        other_prefs.save()
        
        response = self.client.get(url)
        data = json.loads(response.content)
        
        # Should return hidden status
        self.assertEqual(data['status'], 'hidden')
    
    def test_online_status_not_authenticated(self):
        """Test that online status APIs require authentication."""
        self.client.logout()
        
        # Try to get preferences
        url = reverse('get_online_status_preference')
        response = self.client.get(url)
        self.assertRedirects(response, f"{reverse('login')}?next={url}")
        
        # Try to update status
        url = reverse('update_online_status')
        response = self.client.post(
            url,
            json.dumps({'status': 'active'}),
            content_type='application/json'
        )
        self.assertRedirects(response, f"{reverse('login')}?next={url}")


class CommandsTests(TestCase):
    """Tests for management commands."""
    
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
        
        # Delete profile for user2 to test command
        Profile.objects.filter(user=self.user2).delete()
    
    def test_create_profiles_command(self):
        """Test the create_profiles management command."""
        # Import command here to avoid import errors
        from django.core.management import call_command
        from io import StringIO
        
        # Call command with redirected stdout
        out = StringIO()
        call_command('create_profiles', stdout=out)
        
        # Check output
        self.assertIn('Created profiles for users: user2', out.getvalue())
        
        # Check that profile was created
        self.assertTrue(hasattr(self.user2, 'profile'))
        
        # Call command again - should output that all users have profiles
        out = StringIO()
        call_command('create_profiles', stdout=out)
        self.assertIn('All users already have profiles', out.getvalue())
    
    @patch('users.signals.Profile.objects.create')
    def test_create_profile_signal(self, mock_create):
        """Test the signal that creates a profile when a user is created."""
        # Create a new user
        user = User.objects.create_user(
            username='signaluser',
            email='signal@example.com',
            password='password123'
        )
        
        # Check that the signal called create
        mock_create.assert_called_once_with(user=user)
    
@patch('users.signals.Profile.objects.create')
def test_save_profile_signal_with_exception(self, mock_create):
    """Test the signal that saves profile with exception handling."""
    # Set up user without profile to trigger exception
    user = User.objects.create_user(
        username='exceptionuser',
        email='exception@example.com',
        password='password123'
    )
    Profile.objects.filter(user=user).delete()
    
    # Now save the user to trigger signal
    user.save()
    
    # Check that Profile.objects.create was called
    mock_create.assert_called_once_with(user=user)
    
    def test_dnd_period_crossing_midnight(self):
        """Test DND period that crosses midnight."""
        # Set up preferences
        prefs = self.user.notification_preferences
        prefs.dnd_enabled = True
        prefs.dnd_start_time = datetime.time(22, 0)  # 10 PM
        prefs.dnd_end_time = datetime.time(6, 0)     # 6 AM
        prefs.save()
        
        # Mock current time to 11 PM (should be DND)
        with patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = datetime.datetime.combine(
                datetime.date.today(),
                datetime.time(23, 0)
            )
            
            self.assertTrue(prefs.is_in_dnd_period())
            
        # Mock current time to 5 AM (should be DND)
        with patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = datetime.datetime.combine(
                datetime.date.today(),
                datetime.time(5, 0)
            )
            
            self.assertTrue(prefs.is_in_dnd_period())
            
        # Mock current time to 8 AM (should not be DND)
        with patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = datetime.datetime.combine(
                datetime.date.today(),
                datetime.time(8, 0)
            )
            
            self.assertFalse(prefs.is_in_dnd_period())
    
    def test_dnd_period_same_day(self):
        """Test DND period within same day."""
        # Set up preferences
        prefs = self.user.notification_preferences
        prefs.dnd_enabled = True
        prefs.dnd_start_time = datetime.time(13, 0)  # 1 PM
        prefs.dnd_end_time = datetime.time(15, 0)    # 3 PM
        prefs.save()
        
        # Mock current time to 2 PM (should be DND)
        with patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = datetime.datetime.combine(
                datetime.date.today(),
                datetime.time(14, 0)
            )
            
            self.assertTrue(prefs.is_in_dnd_period())
            
        # Mock current time to 4 PM (should not be DND)
        with patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = datetime.datetime.combine(
                datetime.date.today(),
                datetime.time(16, 0)
            )
            
            self.assertFalse(prefs.is_in_dnd_period())
    
    def test_should_notify_work_hours(self):
        """Test notification based on work hours."""
        # Set up preferences
        prefs = self.user.notification_preferences
        prefs.dnd_enabled = False
        prefs.work_days = '12345'  # Monday-Friday
        prefs.work_start_time = datetime.time(9, 0)
        prefs.work_end_time = datetime.time(17, 0)
        prefs.save()
        
        # Mock current time to Wednesday 10 AM (should notify)
        with patch('django.utils.timezone.now') as mock_now:
            mock_date = datetime.datetime.now()
            # Find next Wednesday (weekday 2)
            while mock_date.weekday() != 2:  # 2 is Wednesday
                mock_date += datetime.timedelta(days=1)
            mock_date = mock_date.replace(hour=10, minute=0)
            mock_now.return_value = mock_date
            
            self.assertTrue(prefs.should_notify())
            
        # Mock current time to Saturday 10 AM (should not notify)
        with patch('django.utils.timezone.now') as mock_now:
            mock_date = datetime.datetime.now()
            # Find next Saturday (weekday 5)
            while mock_date.weekday() != 5:  # 5 is Saturday
                mock_date += datetime.timedelta(days=1)
            mock_date = mock_date.replace(hour=10, minute=0)
            mock_now.return_value = mock_date
            
            self.assertFalse(prefs.should_notify())
            
        # Mock current time to Wednesday 8 AM (should not notify)
        with patch('django.utils.timezone.now') as mock_now:
            mock_date = datetime.datetime.now()
            # Find next Wednesday
            while mock_date.weekday() != 2:
                mock_date += datetime.timedelta(days=1)
            mock_date = mock_date.replace(hour=8, minute=0)
            mock_now.return_value = mock_date
            
            self.assertFalse(prefs.should_notify())
    
    def test_should_notify_dnd(self):
        """Test notification when DND is active."""
        # Set up preferences
        prefs = self.user.notification_preferences
        prefs.dnd_enabled = True
        prefs.dnd_start_time = datetime.time(22, 0)
        prefs.dnd_end_time = datetime.time(8, 0)
        prefs.work_days = '12345'
        prefs.work_start_time = datetime.time(9, 0)
        prefs.work_end_time = datetime.time(17, 0)
        prefs.save()
        
        # Mock current time to 11 PM (should not notify)
        with patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = datetime.datetime.combine(
                datetime.date.today(),
                datetime.time(23, 0)
            )
            
            self.assertFalse(prefs.should_notify())
            
        # Mock current time to 9 AM (should notify)
        with patch('django.utils.timezone.now') as mock_now:
            # Make sure it's a weekday
            mock_date = datetime.datetime.now()
            # Find next Monday
            while mock_date.weekday() != 0:
                mock_date += datetime.timedelta(days=1)
            mock_date = mock_date.replace(hour=9, minute=0)
            mock_now.return_value = mock_date
            
            self.assertTrue(prefs.should_notify())
    
    def test_notification_mode_setting(self):
        """Test notification based on notification mode."""
        # Set up preferences
        prefs = self.user.notification_preferences
        prefs.dnd_enabled = False
        prefs.notification_mode = 'none'
        prefs.save()
        
        # Should not notify in 'none' mode
        self.assertFalse(prefs.should_notify())
        
        # Change to 'all' mode
        prefs.notification_mode = 'all'
        prefs.save()
        
        # Should notify in 'all' mode
        self.assertTrue(prefs.should_notify())


class NotificationTests(TestCase):
    """Tests for notification functionality."""
    
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
            user=self.user1,
            message='Test notification 2',
            work_item=self.work_item,
            notification_type='update'
        )
        
        # Login
        self.client.login(username='user1', password='password123')
    
    def test_notifications_list_view(self):
        """Test the notifications list view."""
        url = reverse('notifications_list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'workspace/notifications_list.html')
        self.assertIn(self.notification1, response.context['notifications'])
        self.assertIn(self.notification2, response.context['notifications'])
        self.assertEqual(response.context['unread_count'], 2)
    
    def test_mark_notification_read(self):
        """Test marking a notification as read."""
        url = reverse('mark_notification_read', args=[self.notification1.id])
        response = self.client.get(url)
        
        # Refresh from database
        self.notification1.refresh_from_db()
        
        # Check the notification was marked as read
        self.assertTrue(self.notification1.is_read)
        
        # Check redirect
        self.assertRedirects(response, reverse('notifications_list'))
    
    def test_mark_all_read(self):
        """Test marking all notifications as read."""
        url = reverse('mark_all_read')
        response = self.client.get(url)
        
        # Refresh from database
        self.notification1.refresh_from_db()
        self.notification2.refresh_from_db()
        
        # Check both notifications were marked as read
        self.assertTrue(self.notification1.is_read)
        self.assertTrue(self.notification2.is_read)
        
        # Check redirect
        self.assertRedirects(response, reverse('notifications_list'))
    
    def test_mark_notification_read_ajax(self):
        """Test marking a notification as read via AJAX."""
        url = reverse('mark_notification_read', args=[self.notification1.id])
        response = self.client.get(
            url, 
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        # Check response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        
        # Check notification was marked as read
        self.notification1.refresh_from_db()
        self.assertTrue(self.notification1.is_read)
        
    def test_mark_all_read_ajax(self):
        """Test marking all notifications as read via AJAX."""
        url = reverse('mark_all_read')
        response = self.client.get(
            url, 
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        # Check response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        
        # Check notifications were marked as read
        self.notification1.refresh_from_db()
        self.notification2.refresh_from_db()
        self.assertTrue(self.notification1.is_read)
        self.assertTrue(self.notification2.is_read)
    
    def test_notification_creation_when_mentioned(self):
        """Test that a notification is created when a user is mentioned."""
        # Assuming there's a method to create a notification when a user is mentioned
        # We'll simulate this with a direct creation
        mention_notification = Notification.objects.create(
            user=self.user2,
            message='You were mentioned by user1',
            work_item=self.work_item,
            notification_type='mention'
        )
        
        # Login as user2
        self.client.logout()
        self.client.login(username='user2', password='password123')
        
        # Check that user2 sees the notification
        response = self.client.get(reverse('notifications_list'))
        self.assertIn(mention_notification, response.context['notifications'])
    
    def test_notification_deletion(self):
        """Test deleting a notification."""
        url = reverse('delete_notification', args=[self.notification1.id])
        response = self.client.post(url)
        
        # Check the notification was deleted
        self.assertFalse(Notification.objects.filter(id=self.notification1.id).exists())
        
        # Check redirect
        self.assertRedirects(response, reverse('notifications_list'))