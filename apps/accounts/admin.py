from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, CustomerProfile


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'phone_number', 'user_type', 'is_verified', 'is_staff', 'date_joined')
    list_filter = ('user_type', 'is_verified', 'is_staff', 'is_superuser', 'is_active')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'phone_number')
    ordering = ('-date_joined',)

    fieldsets = BaseUserAdmin.fieldsets + (
        ('Custom Attributes', {'fields': ('phone_number', 'user_type', 'is_verified')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Custom Attributes', {'fields': ('email', 'phone_number', 'user_type', 'is_verified')}),
    )

    def save_model(self, request, obj, form, change):
        obj.full_clean()
        super().save_model(request, obj, form, change)


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'city', 'state', 'driving_license_number')
    search_fields = ('user__username', 'user__email', 'city', 'state', 'driving_license_number')
    list_filter = ('state', 'city')
    ordering = ('user',)
