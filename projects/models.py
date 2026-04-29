"""
Projects app models: Project and ProjectMember.

Repository field stores a GitHub URL only (validated in serializer and via settings).
No GitHub API integration — URL storage and display only.
"""

import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class ProjectStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'
    ON_HOLD = 'on_hold', 'On Hold'
    COMPLETED = 'completed', 'Completed'
    CANCELLED = 'cancelled', 'Cancelled'
    ARCHIVED = 'archived', 'Archived'


class ProjectHealth(models.TextChoices):
    ON_TRACK = 'on_track', 'On Track'
    AT_RISK = 'at_risk', 'At Risk'
    OFF_TRACK = 'off_track', 'Off Track'


class ProjectType(models.TextChoices):
    INTERNAL = 'internal', 'Internal'
    CLIENT = 'client', 'Client'


class Project(models.Model):
    """
    Core project record.
    - owner: the employee profile who manages the project
    - repository_url: optional GitHub URL (validated at save; stored only, no sync)
    - status / health / dates drive display in the frontend
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, blank=True, db_index=True)
    description = models.TextField(blank=True)

    type = models.CharField(
        max_length=20,
        choices=ProjectType.choices,
        default=ProjectType.INTERNAL,
    )

    owner = models.ForeignKey(
        'people.EmployeeProfile',
        on_delete=models.PROTECT,
        related_name='owned_projects',
    )

    status = models.CharField(
        max_length=20,
        choices=ProjectStatus.choices,
        default=ProjectStatus.ACTIVE,
        db_index=True,
    )
    health = models.CharField(
        max_length=20,
        choices=ProjectHealth.choices,
        default=ProjectHealth.ON_TRACK,
        db_index=True,
    )

    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)

    # GitHub URL only — no token, no API sync.
    repository_url = models.URLField(max_length=300, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'project'
        verbose_name_plural = 'projects'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class ProjectMember(models.Model):
    """
    Junction: employee ↔ project membership.
    An employee can be a member of multiple projects.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    employee = models.ForeignKey(
        'people.EmployeeProfile',
        on_delete=models.CASCADE,
        related_name='project_memberships',
    )
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'project member'
        verbose_name_plural = 'project members'
        unique_together = [('project', 'employee')]
        ordering = ['project', 'employee']

    def __str__(self):
        return f'{self.employee.full_name} → {self.project.name}'
