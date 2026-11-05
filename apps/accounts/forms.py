import re
from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import CustomerProfile

User = get_user_model()


class UserLoginForm(forms.Form):
    """
    Form for user login supporting authentication by either username or email,
    along with session 'Remember Me' persistence.
    """
    username = forms.CharField(
        label="Email",
        max_length=254,
        required=True,
        widget=forms.TextInput(attrs={
            'id': 'username',
            'placeholder': 'Enter your email',
            'autocomplete': 'username',
        })
    )
    password = forms.CharField(
        label="Password",
        required=True,
        widget=forms.PasswordInput(attrs={
            'id': 'password',
            'placeholder': '••••••••',
            'autocomplete': 'current-password',
        })
    )
    remember_me = forms.BooleanField(
        label="Remember Me",
        required=False,
        widget=forms.CheckboxInput(attrs={
            'id': 'remember_me',
        })
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        username_or_email = cleaned_data.get('username', '').strip()
        password = cleaned_data.get('password')

        if username_or_email and password:
            self.user_cache = authenticate(
                self.request,
                username=username_or_email,
                password=password
            )

            if self.user_cache is None:
                raise ValidationError(
                    "Invalid email/username or password. Please try again.",
                    code='invalid_login'
                )
            elif not self.user_cache.is_active:
                raise ValidationError(
                    "This account has been deactivated. Please contact support.",
                    code='inactive'
                )

        return cleaned_data

    def get_user(self):
        return self.user_cache


class UserRegistrationForm(forms.Form):
    """
    Form for registering a new customer account on CarVistaHub.
    Enforces strict validation on unique username/email, strong passwords,
    valid Indian phone numbers, and terms agreement.
    """
    first_name = forms.CharField(
        label="First Name",
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={
            'id': 'firstName',
            'placeholder': 'First Name',
            'autocomplete': 'given-name',
        })
    )
    last_name = forms.CharField(
        label="Last Name",
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={
            'id': 'lastName',
            'placeholder': 'Last Name',
            'autocomplete': 'family-name',
        })
    )
    username = forms.CharField(
        label="Username",
        max_length=150,
        min_length=4,
        required=True,
        widget=forms.TextInput(attrs={
            'id': 'username',
            'placeholder': 'Choose a unique username',
            'autocomplete': 'username',
        })
    )
    email = forms.EmailField(
        label="Email Address",
        required=True,
        widget=forms.EmailInput(attrs={
            'id': 'email',
            'placeholder': 'name@example.com',
            'autocomplete': 'email',
        })
    )
    phone_number = forms.CharField(
        label="Phone Number",
        max_length=15,
        min_length=10,
        required=True,
        widget=forms.TextInput(attrs={
            'id': 'phone',
            'placeholder': '9876543210',
            'pattern': r'[0-9]{10}',
            'maxlength': '10',
            'autocomplete': 'tel',
        })
    )
    password = forms.CharField(
        label="Password",
        required=True,
        widget=forms.PasswordInput(attrs={
            'id': 'password',
            'placeholder': '••••••••',
            'autocomplete': 'new-password',
        })
    )
    confirm_password = forms.CharField(
        label="Confirm Password",
        required=True,
        widget=forms.PasswordInput(attrs={
            'id': 'confirmPassword',
            'placeholder': '••••••••',
            'autocomplete': 'new-password',
        })
    )
    terms = forms.BooleanField(
        label="I agree to the Terms & Conditions",
        required=True,
        widget=forms.CheckboxInput(attrs={
            'id': 'terms',
        }),
        error_messages={
            'required': 'You must agree to the Terms & Conditions to create an account.'
        }
    )

    def clean_first_name(self):
        first_name = self.cleaned_data.get('first_name', '').strip()
        if not first_name:
            raise ValidationError("Please enter your first name.")
        return first_name

    def clean_last_name(self):
        last_name = self.cleaned_data.get('last_name', '').strip()
        if not last_name:
            raise ValidationError("Please enter your last name.")
        return last_name

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if not re.match(r'^[\w.@+-]+$', username):
            raise ValidationError(
                "Usernames may only contain letters, numbers, and @/./+/-/_ characters."
            )
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("This username is already taken. Please choose another.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email address already exists.")
        return email

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number', '').strip()
        digits = re.sub(r'\D', '', phone)
        if len(digits) != 10 or digits[0] not in '6789':
            raise ValidationError(
                "Please enter a valid 10-digit Indian mobile number starting with 6, 7, 8, or 9."
            )
        return digits

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password:
            if password != confirm_password:
                self.add_error('confirm_password', "Passwords do not match.")
            else:
                temp_user = User(
                    username=cleaned_data.get('username', ''),
                    email=cleaned_data.get('email', '')
                )
                try:
                    validate_password(password, user=temp_user)
                except ValidationError as error:
                    for err in error:
                        self.add_error('password', err)

        return cleaned_data

    def save(self):
        cleaned_data = self.cleaned_data
        user = User(
            username=cleaned_data['username'],
            email=cleaned_data['email'],
            first_name=cleaned_data['first_name'],
            last_name=cleaned_data['last_name'],
            phone_number=cleaned_data['phone_number'],
            user_type=User.UserType.CUSTOMER,
            is_verified=False,
            is_staff=False,
            is_superuser=False,
            is_active=True
        )
        user.set_password(cleaned_data['password'])
        user.save()

        CustomerProfile.objects.get_or_create(user=user)
        return user
