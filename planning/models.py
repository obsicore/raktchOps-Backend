"""
Planning app models: Sprint and Milestone.
Both are scoped to a project. Sprints contain WorkItems.
"""

import uuid
from django.db import models
from django.utils import timezone


class SprintStatus(models.TextChoices):
    PLANNING = 'planning', 'Planning'
    ACTIVE = 'active', 'Active'
    COMPLETED = 'completed', 'Completed'
    CANCELLED = 'cancelled', 'Cancelled'


class Sprint(models.Model):
    """
    A time-boxed iteration for work items.
    Only one sprint can be active per project at a time (enforced in serializer).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='sprints',
    )
    name = models.CharField(max_length=200)
    status = models.CharField(
        max_length=20,
        choices=SprintStatus.choices,
        default=SprintStatus.PLANNING,
        db_index=True,
    )
    start_date = models.DateField()
    end_date = models.DateField()
    capacity = models.PositiveSmallIntegerField(null=True, blank=True, help_text='Story points or item count capacity')
    goal = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'sprint'
        verbose_name_plural = 'sprints'
        ordering = ['-start_date']

    def __str__(self):
        return f'{self.project.name} — {self.name}'

    @property
    def progress_summary(self):
        """Returns {total, done, in_progress} work item counts."""
        items = self.work_items.all()
        total = items.count()
        done = items.filter(status='done').count()
        in_progress = items.filter(status='in_progress').count()
        return {'total': total, 'done': done, 'in_progress': in_progress}


class MilestoneStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    IN_PROGRESS = 'in_progress', 'In Progress'
    ACHIEVED = 'achieved', 'Achieved'
    MISSED = 'missed', 'Missed'


class Milestone(models.Model):
    """
    A key deliverable date for a project.
    Not directly linked to sprints — project-level marker.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='milestones',
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    target_date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=MilestoneStatus.choices,
        default=MilestoneStatus.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'milestone'
        verbose_name_plural = 'milestones'
        ordering = ['target_date']

    def __str__(self):
        return f'{self.project.name} — {self.name}'
