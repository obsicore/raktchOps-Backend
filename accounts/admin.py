"""
Django admin registration for the accounts app.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, InviteToken, EmailVerificationToken, PasswordResetToken


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['email', 'account_status', 'is_staff', 'is_active', 'date_joined']
    list_filter = ['account_status', 'is_staff', 'is_active']
    search_fields = ['email']
    ordering = ['email']

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Account State', {'fields': ('account_status', 'failed_login_attempts', 'locked_until')}),
        ('Permissions', {'fields': ('is_staff', 'is_active', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates', {'fields': ('date_joined', 'last_login')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'account_status'),
        }),
    )
    readonly_fields = ['date_joined', 'last_login']

    # BaseUserAdmin uses 'username' by default; override for email-based auth
    filter_horizontal = ('groups', 'user_permissions')


@admin.register(InviteToken)
class InviteTokenAdmin(admin.ModelAdmin):
    list_display = ['email', 'role', 'status', 'invited_by', 'expires_at', 'consumed_at', 'created_at']
    list_filter = ['status', 'role']
    search_fields = ['email']
    readonly_fields = ['token', 'created_at', 'consumed_at']
    ordering = ['-created_at']


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'expires_at', 'used_at', 'created_at']
    list_filter = ['used_at']
    search_fields = ['user__email']
    readonly_fields = ['token', 'created_at', 'used_at']
    ordering = ['-created_at']


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'expires_at', 'used_at', 'created_at']
    list_filter = ['used_at']
    search_fields = ['user__email']
    readonly_fields = ['token', 'created_at', 'used_at']
    ordering = ['-created_at']
