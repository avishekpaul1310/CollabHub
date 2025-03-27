from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from users.models import Profile
from users.forms import UserRegisterForm, UserUpdateForm, ProfileUpdateForm
from django.core.files.uploadedfile import SimpleUploadedFile


class UserModelTest(TestCase):
    """Tests for the User model and its Profile relationship."""
    
    def test_profile_creation(self):
        """Test that a profile is automatically created when a user is created."""
        user = User.objects.create_user(username='testuser', email='test@example.com', password='password123')
        self.assertTrue(hasattr(user, 'profile'))
        self.assertIsInstance(user.profile, Profile)
    
    def test_profile_str_representation(self):
        """Test the string representation of a Profile."""
        user = User.objects.create_user(username='testuser', email='test@example.com', password='password123')
        self.assertEqual(str(user.profile), 'testuser Profile')


class UserRegisterViewTest(TestCase):
    """Tests for the user registration view."""
    
    def setUp(self):
        self.client = Client()
        self.register_url = reverse('register')
        self.dashboard_url = reverse('dashboard')
        self.login_url = reverse('login')
    
    def test_register_view_get(self):
        """Test that the register page loads correctly."""
        response = self.client.get(self.register_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/register.html')
        self.assertIsInstance(response.context['form'], UserRegisterForm)
    
    def test_register_view_post_valid(self):
        """Test successful user registration."""
        data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'complex_password123',
            'password2': 'complex_password123',
        }
        response = self.client.post(self.register_url, data)
        
        # Check that user was created
        self.assertEqual(User.objects.count(), 1)
        # Check redirect to login page
        self.assertRedirects(response, self.login_url)
        # Check success message
        messages = list(response.wsgi_request._messages)
        self.assertEqual(len(messages), 1)
        self.assertIn('Account created for newuser!', str(messages[0]))
    
    def test_register_view_post_invalid(self):
        """Test registration with invalid data."""
        # Password mismatch
        data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'complex_password123',
            'password2': 'different_password',
        }
        response = self.client.post(self.register_url, data)
        
        # Form should display error and not create user
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 0)
        self.assertFormError(response, 'form', 'password2', "The two password fields didn't match.")
    
    def test_register_view_existing_username(self):
        """Test registration with an existing username."""
        # Create a user first
        User.objects.create_user(username='existinguser', email='existing@example.com', password='password123')
        
        # Try to register with the same username
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


class UserLoginTest(TestCase):
    """Tests for user login functionality."""
    
    def setUp(self):
        self.client = Client()
        self.login_url = reverse('login')
        self.dashboard_url = reverse('dashboard')
        self.user = User.objects.create_user(username='testuser', email='test@example.com', password='password123')
    
    def test_login_view_get(self):
        """Test that the login page loads correctly."""
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/login.html')
    
    def test_login_successful(self):
        """Test successful login."""
        data = {
            'username': 'testuser',
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
            'username': 'testuser',
            'password': 'wrongpassword',
        }
        response = self.client.post(self.login_url, data)
        
        # Form should display error
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertFormError(response, 'form', None, 'Please enter a correct username and password. Note that both fields may be case-sensitive.')


class UserLogoutTest(TestCase):
    """Tests for user logout functionality."""
    
    def setUp(self):
        self.client = Client()
        self.logout_url = reverse('logout')
        self.login_url = reverse('login')
        self.user = User.objects.create_user(username='testuser', email='test@example.com', password='password123')
        self.client.login(username='testuser', password='password123')
    
    def test_logout_view(self):
        """Test logout functionality."""
        response = self.client.get(self.logout_url)
        
        # Check template used
        self.assertTemplateUsed(response, 'users/logout.html')
        # Verify user is logged out
        self.assertFalse(response.wsgi_request.user.is_authenticated)


class UserProfileViewTest(TestCase):
    """Tests for the user profile view."""
    
    def setUp(self):
        self.client = Client()
        self.profile_url = reverse('profile')
        self.login_url = reverse('login')
        self.user = User.objects.create_user(username='testuser', email='test@example.com', password='password123')
        # Create a test avatar image
        self.avatar = SimpleUploadedFile(
            name='test_avatar.jpg',
            content=b'',  # Empty content for testing
            content_type='image/jpeg'
        )
    
    def test_profile_view_not_logged_in(self):
        """Test that the profile view redirects if user is not logged in."""
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
    
    def test_profile_update(self):
        """Test updating a user's profile."""
        self.client.login(username='testuser', password='password123')
        
        # Update profile with new data
        data = {
            'username': 'updated_user',
            'email': 'updated@example.com',
            'bio': 'This is my updated bio',
        }
        
        # If using MultiValueDict for files
        response = self.client.post(self.profile_url, data)
        
        # Refresh user from database
        self.user.refresh_from_db()
        
        # Check that user info was updated
        self.assertEqual(self.user.username, 'updated_user')
        self.assertEqual(self.user.email, 'updated@example.com')
        self.assertEqual(self.user.profile.bio, 'This is my updated bio')
        
        # Check for success message
        messages = list(response.wsgi_request._messages)
        self.assertEqual(len(messages), 1)
        self.assertIn('Your profile has been updated!', str(messages[0]))
    
    def test_profile_update_with_avatar(self):
        """Test updating a user's profile with an avatar image."""
        self.client.login(username='testuser', password='password123')
        
        # Update profile with new data including avatar
        data = {
            'username': 'image_user',
            'email': 'image@example.com',
            'bio': 'Profile with image',
            'avatar': self.avatar,
        }
        
        response = self.client.post(self.profile_url, data, format='multipart')
        
        # Refresh user from database
        self.user.refresh_from_db()
        
        # Check that user info was updated
        self.assertEqual(self.user.username, 'image_user')
        self.assertEqual(self.user.email, 'image@example.com')
        self.assertEqual(self.user.profile.bio, 'Profile with image')
        
        # Check for success message
        messages = list(response.wsgi_request._messages)
        self.assertEqual(len(messages), 1)
        self.assertIn('Your profile has been updated!', str(messages[0]))


class UserFormsTest(TestCase):
    """Tests for user-related forms."""
    
    def test_user_register_form_valid(self):
        """Test valid user registration form."""
        form_data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'complex_password123',
            'password2': 'complex_password123',
        }
        form = UserRegisterForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_user_register_form_password_mismatch(self):
        """Test registration form with mismatched passwords."""
        form_data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'complex_password123',
            'password2': 'different_password',
        }
        form = UserRegisterForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('password2', form.errors)
    
    def test_user_update_form_valid(self):
        """Test valid user update form."""
        user = User.objects.create_user(username='testuser', email='test@example.com', password='password123')
        
        form_data = {
            'username': 'updated_user',
            'email': 'updated@example.com',
        }
        form = UserUpdateForm(data=form_data, instance=user)
        self.assertTrue(form.is_valid())
    
    def test_profile_update_form_valid(self):
        """Test valid profile update form."""
        user = User.objects.create_user(username='testuser', email='test@example.com', password='password123')
        
        form_data = {
            'bio': 'This is my test bio',
        }
        form = ProfileUpdateForm(data=form_data, instance=user.profile)
        self.assertTrue(form.is_valid())


class UserProfileSignalTest(TestCase):
    """Tests for user profile signals (create/save profile)."""
    
    def test_profile_created_on_user_creation(self):
        """Test that a profile is created when a user is created."""
        self.assertEqual(Profile.objects.count(), 0)
        user = User.objects.create_user(username='signaltest', email='signal@example.com', password='password123')
        self.assertEqual(Profile.objects.count(), 1)
        self.assertEqual(Profile.objects.first().user, user)
    
    def test_profile_updated_on_user_save(self):
        """Test that an existing profile is saved when the user is saved."""
        # Create user and modify profile
        user = User.objects.create_user(username='updateuser', email='update@example.com', password='password123')
        user.profile.bio = 'Original bio'
        user.profile.save()
        
        # Change and save the user
        user.username = 'changed_username'
        user.save()
        
        # Refresh the profile from the database
        profile = Profile.objects.get(user=user)
        self.assertEqual(profile.bio, 'Original bio')
        self.assertEqual(profile.user.username, 'changed_username')
    
    def test_create_profile_command(self):
        """Test the create_profiles management command (simulated)."""
        # Create a user without a profile
        user = User.objects.create_user(username='noprofile', email='noprofile@example.com', password='password123')
        # Delete their profile to simulate a user without one
        Profile.objects.filter(user=user).delete()
        
        # Verify no profile exists
        with self.assertRaises(Profile.DoesNotExist):
            Profile.objects.get(user=user)
        
        # Simulate the command by running the signal manually
        from users.signals import create_profile
        create_profile(sender=User, instance=user, created=False)
        
        # Verify profile now exists
        self.assertTrue(Profile.objects.filter(user=user).exists())