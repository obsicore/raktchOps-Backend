"""
Role-Based Access Control models.
UserRole stores the assigned role for each user.
A user may have at most one primary role.
"""

import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    SUPER_ADMIN = 'super_admin', 'Super Admin'
    ADMIN = 'admin', 'Admin'
    PROJECT_MANAGER = 'project_manager', 'Project Manager'
    TEAM_LEAD = 'team_lead', 'Team Lead'
    STAFF = 'staff', 'Staff'


class UserRole(models.Model):
    """Associates a user with a role. Only one role may be primary per user."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='user_roles',
    )
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.STAFF)
    is_primary = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'user role'
        verbose_name_plural = 'user roles'
        unique_together = [('user', 'role')]
        ordering = ['user', 'role']

    def __str__(self):
        return f'{self.user.email} — {self.role}'

    def save(self, *args, **kwargs):
        # Enforce single primary role per user
        if self.is_primary:
            UserRole.objects.filter(user=self.user, is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_user_role(user) -> str:
    """
    Return the primary role string for a user.
    Django superusers always return super_admin regardless of UserRole entries.
    Falls back to 'staff' if no role is assigned.
    """
    if getattr(user, 'is_superuser', False):
        return Role.SUPER_ADMIN
    try:
        return UserRole.objects.get(user=user, is_primary=True).role
    except UserRole.DoesNotExist:
        return Role.STAFF


def has_role(user, *roles) -> bool:
    """Return True if the user's primary role is among the given roles."""
    return get_user_role(user) in roles


def is_super_admin(user) -> bool:
    return has_role(user, Role.SUPER_ADMIN)


def is_admin(user) -> bool:
    return has_role(user, Role.SUPER_ADMIN, Role.ADMIN)


def is_project_manager(user) -> bool:
    return has_role(user, Role.PROJECT_MANAGER)


def is_team_lead(user) -> bool:
    return has_role(user, Role.TEAM_LEAD)


def is_staff(user) -> bool:
    return has_role(user, Role.STAFF)


def is_admin_or_pm(user) -> bool:
    return has_role(user, Role.SUPER_ADMIN, Role.ADMIN, Role.PROJECT_MANAGER)


def is_admin_or_pm_or_lead(user) -> bool:
    return has_role(user, Role.SUPER_ADMIN, Role.ADMIN, Role.PROJECT_MANAGER, Role.TEAM_LEAD)
