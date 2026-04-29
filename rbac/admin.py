"""
Django admin registration for the rbac app.
"""

from django.contrib import admin
from .models import UserRole


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'is_primary', 'created_at']
    list_filter = ['role', 'is_primary']
    search_fields = ['user__email']
    readonly_fields = ['created_at']
    ordering = ['user', 'role']
