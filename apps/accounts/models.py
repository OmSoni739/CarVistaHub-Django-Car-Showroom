from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError


class User(AbstractUser):
    """
    Custom User Model for CarVistaHub platform supporting Customers,
    Showroom Managers, and Administrators.
    """
    class UserType(models.TextChoices):
        CUSTOMER = 'CUSTOMER', 'Customer'
        MANAGER = 'MANAGER', 'Showroom Manager'
        ADMIN = 'ADMIN', 'Administrator'

    email = models.EmailField(unique=True, verbose_name="Email Address")
    phone_number = models.CharField(max_length=15, blank=True, verbose_name="Phone Number")
    user_type = models.CharField(
        max_length=20,
        choices=UserType.choices,
        default=UserType.CUSTOMER,
        verbose_name="User Type"
    )
    is_verified = models.BooleanField(default=False, verbose_name="Verified Account")

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ['-date_joined']

    def clean(self):
        super().clean()
        # Enforce single active Manager constraint
        if self.user_type == self.UserType.MANAGER and self.is_active:
            existing_manager_qs = User.objects.filter(
                user_type=self.UserType.MANAGER,
                is_active=True
            )
            if self.pk:
                existing_manager_qs = existing_manager_qs.exclude(pk=self.pk)
            if existing_manager_qs.exists():
                active_manager = existing_manager_qs.first()
                raise ValidationError({
                    'user_type': (
                        f"Only one active Showroom Manager account is allowed. "
                        f"'{active_manager.username}' is currently the active manager. "
                        f"Deactivate that account before activating a new manager."
                    )
                })

    @classmethod
    def get_active_manager(cls):
        """
        Retrieves the single active Showroom Manager account.
        Returns None if no active manager exists.
        """
        return cls.objects.filter(user_type=cls.UserType.MANAGER, is_active=True).first()

    def __str__(self):
        return f"{self.username} ({self.get_user_type_display()})"


class CustomerProfile(models.Model):
    """
    Extended profile information for customers including driving license details.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name="User Account"
    )
    profile_picture = models.ImageField(
        upload_to='profiles/',
        blank=True,
        null=True,
        verbose_name="Profile Picture"
    )
    address = models.TextField(blank=True, verbose_name="Address")
    city = models.CharField(max_length=100, blank=True, verbose_name="City")
    state = models.CharField(max_length=100, blank=True, verbose_name="State")
    zip_code = models.CharField(max_length=10, blank=True, verbose_name="ZIP Code")
    driving_license_number = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Driving License Number"
    )

    class Meta:
        verbose_name = "Customer Profile"
        verbose_name_plural = "Customer Profiles"

    def __str__(self):
        return f"Profile of {self.user.username}"
