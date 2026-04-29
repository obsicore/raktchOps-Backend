"""
People app models: EmployeeProfile linked 1:1 to accounts.User.
Stores all internal directory fields for employee records.
"""

import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class EmploymentStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'
    INACTIVE = 'inactive', 'Inactive'
    ON_LEAVE = 'on_leave', 'On Leave'


class EmployeeProfile(models.Model):
    """
    Internal directory record for an employee.
    Created when a user is promoted to active status.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='employee_profile',
    )

    # Core identity fields
    full_name = models.CharField(max_length=200)
    work_email = models.EmailField(unique=True, db_index=True)
    job_title = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=30, blank=True)

    # Org structure links (nullable FKs to org app models)
    department = models.ForeignKey(
        'org.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
    )
    team = models.ForeignKey(
        'org.Team',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
    )
    manager = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='direct_reports',
    )

    employment_status = models.CharField(
        max_length=20,
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.ACTIVE,
        db_index=True,
    )

    # Optional avatar path (relative to MEDIA_ROOT)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'employee profile'
        verbose_name_plural = 'employee profiles'
        ordering = ['full_name']

    def __str__(self):
        return f'{self.full_name} <{self.work_email}>'

    @property
    def role(self):
        """Return the user's primary role string."""
        from rbac.models import get_user_role
        return get_user_role(self.user)
