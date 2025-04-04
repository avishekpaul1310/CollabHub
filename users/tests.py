from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from users.models import Profile, OnlineStatus
from users.forms import UserRegisterForm, UserUpdateForm, ProfileUpdateForm


class UserModelTests(TestCase):
    """Tests for User-related models"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword123'
        )

    def test_profile_creation(self):
        """Test that a Profile is automatically created when a User is created"""
        # Profile should be created by the signal
        self.assertTrue(hasattr(self.user, 'profile'))
        self.assertIsInstance(self.user.profile, Profile)

    def test_online_status_creation(self):
        """Test creation of online status"""
        # Create an online status manually to test the model
        status = OnlineStatus.objects.create(
            user=self.user,
            status='online',
            status_message='Working on tests'
        )
        self.assertEqual(status.user, self.user)
        self.assertEqual(status.status, 'online')
        self.assertEqual(status.status_message, 'Working on tests')

    def test_profile_str_representation(self):
        """Test the string representation of Profile"""
        expected_str = f'{self.user.username} Profile'
        self.assertEqual(str(self.user.profile), expected_str)

    def test_online_status_str_representation(self):
        """Test the string representation of OnlineStatus"""
        status = OnlineStatus.objects.create(
            user=self.user,
            status='online'
        )
        expected_str = f"{self.user.username}: online"
        self.assertEqual(str(status), expected_str)

    def test_profile_default_values(self):
        """Test that Profile is created with default values"""
        self.assertEqual(self.user.profile.avatar, 'default.png')
        self.assertEqual(self.user.profile.bio, '')


class UserFormsTests(TestCase):
    """Tests for User-related forms"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword123'
        )

    def test_user_register_form_valid(self):
        """Test UserRegisterForm with valid data"""
        form_data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'complex_password123',
            'password2': 'complex_password123'
        }
        form = UserRegisterForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_user_register_form_invalid_password_mismatch(self):
        """Test UserRegisterForm with password mismatch"""
        form_data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'complex_password123',
            'password2': 'different_password123'
        }
        form = UserRegisterForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('password2', form.errors)

    def test_user_register_form_invalid_email(self):
        """Test UserRegisterForm with invalid email"""
        form_data = {
            'username': 'newuser',
            'email': 'invalid-email',
            'password1': 'complex_password123',
            'password2': 'complex_password123'
        }
        form = UserRegisterForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_user_update_form_valid(self):
        """Test UserUpdateForm with valid data"""
        form_data = {
            'username': 'updated_user',
            'email': 'updated@example.com'
        }
        form = UserUpdateForm(data=form_data, instance=self.user)
        self.assertTrue(form.is_valid())

    def test_profile_update_form_valid(self):
        """Test ProfileUpdateForm with valid data"""
        form_data = {
            'bio': 'This is my updated bio'
        }
        form = ProfileUpdateForm(data=form_data, instance=self.user.profile)
        self.assertTrue(form.is_valid())

    def test_profile_update_form_with_image(self):
        """Test ProfileUpdateForm with image upload"""
        # Create a better test image with correct content type
        image_content = b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x00\x00\x00\x21\xf9\x04\x01\x0a\x00\x01\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x4c\x01\x00\x3b'
        image = SimpleUploadedFile(
            "test_image.gif",
            image_content,
            content_type="image/gif"
        )
        
        form_data = {
            'bio': 'Bio with image'
        }
        
        form_files = {
            'avatar': image
        }
        
        form = ProfileUpdateForm(
            data=form_data,
            files=form_files,
            instance=self.user.profile
        )
        
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")


class UserViewsTests(TestCase):
    """Tests for User-related views"""

    def setUp(self):
        """Set up test data and client"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword123'
        )
        self.register_url = reverse('register')
        self.login_url = reverse('login')
        self.logout_url = reverse('logout')
        self.profile_url = reverse('profile')

    def test_register_view_get(self):
        """Test GET request to register view"""
        response = self.client.get(self.register_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/register.html')
        self.assertIsInstance(response.context['form'], UserRegisterForm)

    def test_register_view_post_valid(self):
        """Test POST request to register view with valid data"""
        form_data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'complex_password123',
            'password2': 'complex_password123'
        }
        response = self.client.post(self.register_url, form_data)
        
        # Should redirect to login page after successful registration
        self.assertRedirects(response, self.login_url)
        
        # Check that user was created
        self.assertTrue(User.objects.filter(username='newuser').exists())
        
        # Check that profile was created
        new_user = User.objects.get(username='newuser')
        self.assertTrue(hasattr(new_user, 'profile'))

    def test_register_view_post_invalid(self):
        """Test POST request to register view with invalid data"""
        form_data = {
            'username': '',  # Invalid: empty username
            'email': 'newuser@example.com',
            'password1': 'complex_password123',
            'password2': 'complex_password123'
        }
        response = self.client.post(self.register_url, form_data)
        
        # Should stay on the same page with form errors
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/register.html')
        self.assertFalse(response.context['form'].is_valid())
        
        # Check that no user was created
        self.assertFalse(User.objects.filter(email='newuser@example.com').exists())

    def test_login_view(self):
        """Test login functionality"""
        # First check that unauthenticated user can access login page
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/login.html')
        
        # Test login with valid credentials
        login_data = {
            'username': 'testuser',
            'password': 'testpassword123'
        }
        response = self.client.post(self.login_url, login_data)
        
        # Should redirect to dashboard after successful login
        # We need to get the redirect URL dynamically
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(reverse('dashboard')))
        
        # Verify that user is logged in
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_login_view_invalid(self):
        """Test login with invalid credentials"""
        login_data = {
            'username': 'testuser',
            'password': 'wrongpassword'
        }
        response = self.client.post(self.login_url, login_data)
        
        # Should stay on login page with error
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/login.html')
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_logout_view(self):
        """Test logout functionality"""
        # First login
        self.client.login(username='testuser', password='testpassword123')
        
        # Then logout
        response = self.client.get(self.logout_url)
        
        # Should redirect to logout page
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/logout.html')
        
        # Verify that user is logged out
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_profile_view_unauthenticated(self):
        """Test that unauthenticated user cannot access profile page"""
        response = self.client.get(self.profile_url)
        
        # Should redirect to login page
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('login')))

    def test_profile_view_authenticated(self):
        """Test profile view for authenticated user"""
        self.client.login(username='testuser', password='testpassword123')
        response = self.client.get(self.profile_url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/profile.html')
        self.assertIsInstance(response.context['u_form'], UserUpdateForm)
        self.assertIsInstance(response.context['p_form'], ProfileUpdateForm)
        
    def test_profile_update(self):
        """Test updating profile information"""
        self.client.login(username='testuser', password='testpassword123')
        
        # Data for updating profile
        form_data = {
            'username': 'updated_user',
            'email': 'updated@example.com',
            'bio': 'This is my updated bio'
        }
        
        response = self.client.post(self.profile_url, form_data)
        
        # Should redirect to profile page after update
        self.assertRedirects(response, self.profile_url)
        
        # Refresh user from database to see changes
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        
        # Check that user and profile were updated
        self.assertEqual(self.user.username, 'updated_user')
        self.assertEqual(self.user.email, 'updated@example.com')
        self.assertEqual(self.user.profile.bio, 'This is my updated bio')


class UserSignalsTests(TestCase):
    """Tests for User-related signals"""
    
    def test_profile_created_for_new_user(self):
        """Test that a profile is automatically created for a new user"""
        # Create a new user
        user = User.objects.create_user(
            username='signaltest',
            email='signal@example.com',
            password='password123'
        )
        
        # Check that a profile was created
        self.assertTrue(hasattr(user, 'profile'))
        self.assertIsInstance(user.profile, Profile)
    
    def test_profile_created_if_deleted_for_existing_user(self):
        """Test that a profile is created if deleted for an existing user"""
        # Create a user (which also creates a profile)
        user = User.objects.create_user(
            username='profiledeleted',
            email='deleted@example.com',
            password='password123'
        )
        
        # Delete the profile
        user.profile.delete()
        
        # Refresh user and check profile does not exist
        user.refresh_from_db()
        with self.assertRaises(Profile.DoesNotExist):
            profile = user.profile
        
        # Trigger the signal by saving the user
        user.save()
        
        # Refresh and check that a new profile was created
        user.refresh_from_db()
        self.assertTrue(hasattr(user, 'profile'))
        self.assertIsInstance(user.profile, Profile)


class UserManagementCommandTests(TestCase):
    """Tests for management commands"""
    
    def test_create_profiles_command(self):
        """Test the create_profiles management command"""
        # Create users without profiles
        user1 = User.objects.create_user(
            username='cmduser1',
            email='cmd1@example.com',
            password='password123'
        )
        user2 = User.objects.create_user(
            username='cmduser2',
            email='cmd2@example.com',
            password='password123'
        )
        
        # Delete their profiles to simulate the case where profiles are missing
        Profile.objects.filter(user=user1).delete()
        Profile.objects.filter(user=user2).delete()
        
        # Refresh users
        user1.refresh_from_db()
        user2.refresh_from_db()
        
        # Verify profiles are missing
        with self.assertRaises(Profile.DoesNotExist):
            profile1 = user1.profile
        with self.assertRaises(Profile.DoesNotExist):
            profile2 = user2.profile
        
        # Call the command
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command('create_profiles', stdout=out)
        
        # Refresh users again
        user1.refresh_from_db()
        user2.refresh_from_db()
        
        # Verify profiles were created
        self.assertTrue(hasattr(user1, 'profile'))
        self.assertTrue(hasattr(user2, 'profile'))
        
        # Check command output
        output = out.getvalue()
        self.assertIn('Created profiles for users', output)
        self.assertIn('cmduser1', output)
        self.assertIn('cmduser2', output)
    
    def test_create_profiles_command_no_missing_profiles(self):
        """Test create_profiles command when no profiles are missing"""
        # Create a user with a profile
        user = User.objects.create_user(
            username='profileexists',
            email='exists@example.com',
            password='password123'
        )
        
        # Call the command
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command('create_profiles', stdout=out)
        
        # Check command output
        output = out.getvalue()
        self.assertIn('All users already have profiles', output)