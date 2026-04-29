"""
Org app models: Department, Team, TeamMembership.
Supports archive behavior so historical references are preserved.
"""

import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class Department(models.Model):
    """Represents a company department. Archived departments are not deleted."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    head = models.ForeignKey(
        'people.EmployeeProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='headed_departments',
    )
    is_archived = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'department'
        verbose_name_plural = 'departments'
        ordering = ['name']

    def __str__(self):
        return self.name


class Team(models.Model):
    """Represents a team within a department. May be archived but not deleted."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='teams',
    )
    team_lead = models.ForeignKey(
        'people.EmployeeProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='led_teams',
    )
    is_archived = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'team'
        verbose_name_plural = 'teams'
        ordering = ['name']
        unique_together = [('name', 'department')]

    def __str__(self):
        return self.name


class TeamMembership(models.Model):
    """Junction: employee ↔ team. An employee can be in multiple teams."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    employee = models.ForeignKey(
        'people.EmployeeProfile',
        on_delete=models.CASCADE,
        related_name='team_memberships',
    )
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'team membership'
        verbose_name_plural = 'team memberships'
        unique_together = [('team', 'employee')]
        ordering = ['team', 'employee']

    def __str__(self):
        return f'{self.employee.full_name} → {self.team.name}'
