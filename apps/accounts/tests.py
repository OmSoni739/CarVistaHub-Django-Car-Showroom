from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.cars.models import Car

User = get_user_model()


class AccountsAuthenticationTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Create a test customer user
        self.customer = User.objects.create_user(
            username='johndoe',
            email='john@example.com',
            password='ComplexPassword123!',
            first_name='John',
            last_name='Doe',
            phone_number='9876543210',
            user_type=User.UserType.CUSTOMER
        )
        # Create an admin user to verify admin login
        self.admin = User.objects.create_superuser(
            username='adminuser',
            email='adminuser@example.com',
            password='AdminPassword123!',
            first_name='Super',
            last_name='Admin'
        )

    def test_login_page_loads(self):
        """Login page loads with 200 OK and proper template."""
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/login.html')
        self.assertContains(response, 'Welcome Back to CarVistaHub')
        self.assertContains(response, 'Sign In')
        self.assertContains(response, 'CarVistaHub')
        self.assertContains(response, 'csrfmiddlewaretoken')

    def test_register_page_loads(self):
        """Registration page loads with 200 OK and proper template."""
        response = self.client.get(reverse('accounts:register'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/register.html')
        self.assertContains(response, 'Create Your CarVistaHub Account')
        self.assertContains(response, 'Browse Cars')
        self.assertContains(response, 'Compare Cars')
        self.assertContains(response, '+91')
        self.assertContains(response, 'csrfmiddlewaretoken')

    def test_valid_registration_creates_customer_account(self):
        """Valid registration creates customer account with hashed password and profile."""
        reg_data = {
            'first_name': 'Aarav',
            'last_name': 'Patel',
            'username': 'aarav_p',
            'email': 'aarav@example.com',
            'phone_number': '9820098200',
            'password': 'SecurePassWord789!',
            'confirm_password': 'SecurePassWord789!',
            'terms': True
        }
        response = self.client.post(reverse('accounts:register'), reg_data, follow=True)
        self.assertEqual(response.status_code, 200)

        # Check DB
        user = User.objects.get(username='aarav_p')
        self.assertEqual(user.email, 'aarav@example.com')
        self.assertEqual(user.first_name, 'Aarav')
        self.assertEqual(user.last_name, 'Patel')
        self.assertEqual(user.phone_number, '9820098200')
        self.assertEqual(user.user_type, User.UserType.CUSTOMER)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertNotEqual(user.password, 'SecurePassWord789!')
        self.assertTrue(user.check_password('SecurePassWord789!'))
        self.assertTrue(hasattr(user, 'profile'))

    def test_duplicate_username_rejected(self):
        """Registration fails if username already exists."""
        reg_data = {
            'first_name': 'John',
            'last_name': 'Duplicate',
            'username': 'johndoe',  # already exists
            'email': 'unique@example.com',
            'phone_number': '9820098201',
            'password': 'SecurePassWord789!',
            'confirm_password': 'SecurePassWord789!',
            'terms': True
        }
        response = self.client.post(reverse('accounts:register'), reg_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This username is already taken')

    def test_duplicate_email_rejected(self):
        """Registration fails if email already exists."""
        reg_data = {
            'first_name': 'Another',
            'last_name': 'User',
            'username': 'unique_user',
            'email': 'john@example.com',  # already exists
            'phone_number': '9820098202',
            'password': 'SecurePassWord789!',
            'confirm_password': 'SecurePassWord789!',
            'terms': True
        }
        response = self.client.post(reverse('accounts:register'), reg_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'An account with this email address already exists')

    def test_password_mismatch_rejected(self):
        """Registration fails if passwords do not match."""
        reg_data = {
            'first_name': 'Test',
            'last_name': 'User',
            'username': 'test_mismatch',
            'email': 'mismatch@example.com',
            'phone_number': '9820098203',
            'password': 'SecurePassWord789!',
            'confirm_password': 'DifferentPassword789!',
            'terms': True
        }
        response = self.client.post(reverse('accounts:register'), reg_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Passwords do not match')

    def test_terms_required_rejected(self):
        """Registration fails if Terms & Conditions checkbox is not checked."""
        reg_data = {
            'first_name': 'Test',
            'last_name': 'User',
            'username': 'test_terms',
            'email': 'terms@example.com',
            'phone_number': '9820098204',
            'password': 'SecurePassWord789!',
            'confirm_password': 'SecurePassWord789!',
        }
        response = self.client.post(reverse('accounts:register'), reg_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'You must agree to the Terms &amp; Conditions')

    def test_invalid_phone_rejected(self):
        """Registration fails on invalid phone number starting with invalid digit."""
        reg_data = {
            'first_name': 'Test',
            'last_name': 'User',
            'username': 'test_phone',
            'email': 'phone@example.com',
            'phone_number': '1234567890',
            'password': 'SecurePassWord789!',
            'confirm_password': 'SecurePassWord789!',
            'terms': True
        }
        response = self.client.post(reverse('accounts:register'), reg_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'valid 10-digit Indian mobile number')

    def test_invalid_login_shows_error(self):
        """Invalid login displays informative error message."""
        response = self.client.post(reverse('accounts:login'), {
            'username': 'johndoe',
            'password': 'WrongPassword123'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid email/username or password')

    def test_valid_login_with_username(self):
        """User can log in using their username."""
        response = self.client.post(reverse('accounts:login'), {
            'username': 'johndoe',
            'password': 'ComplexPassword123!'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['user'].is_authenticated)
        self.assertEqual(response.context['user'].username, 'johndoe')

    def test_valid_login_with_email(self):
        """User can log in using their email address."""
        response = self.client.post(reverse('accounts:login'), {
            'username': 'john@example.com',
            'password': 'ComplexPassword123!'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['user'].is_authenticated)
        self.assertEqual(response.context['user'].username, 'johndoe')

    def test_admin_login_works(self):
        """Administrator user can authenticate."""
        response = self.client.post(reverse('accounts:login'), {
            'username': 'adminuser',
            'password': 'AdminPassword123!'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['user'].is_authenticated)
        self.assertTrue(response.context['user'].is_staff)

    def test_remember_me_session_expiry(self):
        """Remember me sets extended session expiry."""
        self.client.post(reverse('accounts:login'), {
            'username': 'johndoe',
            'password': 'ComplexPassword123!',
            'remember_me': False
        })
        self.assertTrue(self.client.session.get_expire_at_browser_close())

        self.client.logout()
        self.client.post(reverse('accounts:login'), {
            'username': 'johndoe',
            'password': 'ComplexPassword123!',
            'remember_me': True
        })
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertEqual(self.client.session.get_expiry_age(), 1209600)

    def test_logout_via_post(self):
        """Logout via POST properly clears authentication."""
        self.client.login(username='johndoe', password='ComplexPassword123!')
        response = self.client.post(reverse('accounts:logout'), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['user'].is_authenticated)

    def test_navbar_logged_out_state(self):
        """Logged out visitors see Sign In and Register in navbar."""
        response = self.client.get(reverse('cars:home'))
        self.assertContains(response, 'Sign In')
        self.assertContains(response, 'Register')

    def test_navbar_logged_in_state(self):
        """Logged in users see their display name and Sign Out in navbar."""
        self.client.login(username='johndoe', password='ComplexPassword123!')
        response = self.client.get(reverse('cars:home'))
        self.assertContains(response, 'John')
        self.assertContains(response, 'Sign Out')
