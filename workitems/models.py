"""
Work items app models: WorkItem, Comment, WorkItemDependency, MoveLog.
"""

import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class WorkItemType(models.TextChoices):
    EPIC = 'epic', 'Epic'
    FEATURE = 'feature', 'Feature'
    STORY = 'story', 'Story'
    TASK = 'task', 'Task'
    SUBTASK = 'subtask', 'Subtask'
    BUG = 'bug', 'Bug'
    INCIDENT = 'incident', 'Incident'
    IMPROVEMENT = 'improvement', 'Improvement'
    CHANGE_REQUEST = 'change_request', 'Change Request'


class WorkItemStatus(models.TextChoices):
    BACKLOG = 'backlog', 'Backlog'
    TODO = 'todo', 'To Do'
    IN_PROGRESS = 'in_progress', 'In Progress'
    IN_REVIEW = 'in_review', 'In Review'
    DONE = 'done', 'Done'
    CANCELLED = 'cancelled', 'Cancelled'


class WorkItemPriority(models.TextChoices):
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'
    CRITICAL = 'critical', 'Critical'


# Valid status transitions for Kanban move validation
VALID_TRANSITIONS: dict[str, list[str]] = {
    'backlog':     ['todo', 'cancelled'],
    'todo':        ['in_progress', 'backlog', 'cancelled'],
    'in_progress': ['in_review', 'todo', 'done', 'cancelled'],
    'in_review':   ['in_progress', 'done', 'cancelled'],
    'done':        ['in_review'],          # allow reopen
    'cancelled':   ['backlog', 'todo'],    # allow reopen
}


class WorkItem(models.Model):
    """
    Core work item — maps to a Kanban card.
    Optional parent FK supports epics/features containing stories/tasks.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300)
    type = models.CharField(max_length=20, choices=WorkItemType.choices, default=WorkItemType.TASK, db_index=True)
    description = models.TextField(blank=True)

    status = models.CharField(
        max_length=20, choices=WorkItemStatus.choices,
        default=WorkItemStatus.BACKLOG, db_index=True
    )
    priority = models.CharField(
        max_length=20, choices=WorkItemPriority.choices,
        default=WorkItemPriority.MEDIUM, db_index=True
    )

    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='work_items',
    )
    sprint = models.ForeignKey(
        'planning.Sprint',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='work_items',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='children',
    )

    assignee = models.ForeignKey(
        'people.EmployeeProfile',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_items',
    )
    reporter = models.ForeignKey(
        'people.EmployeeProfile',
        on_delete=models.PROTECT,
        related_name='reported_items',
    )

    due_date = models.DateField(null=True, blank=True)
    progress = models.PositiveSmallIntegerField(default=0)  # 0–100
    is_blocked = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'work item'
        verbose_name_plural = 'work items'
        ordering = ['-created_at']

    def __str__(self):
        return f'[{self.type.upper()}] {self.title}'

    @property
    def is_overdue(self):
        if self.due_date and self.status not in ('done', 'cancelled'):
            from datetime import date
            return self.due_date < date.today()
        return False


class Comment(models.Model):
    """User comment on a work item."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    work_item = models.ForeignKey(WorkItem, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(
        'people.EmployeeProfile',
        on_delete=models.SET_NULL,
        null=True,
        related_name='comments',
    )
    body = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'Comment on {self.work_item_id}'


class WorkItemDependency(models.Model):
    """
    Directed dependency: blocked_by → blocks.
    'this item is blocked by that item'.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    from_item = models.ForeignKey(WorkItem, on_delete=models.CASCADE, related_name='blocked_by_set')
    to_item = models.ForeignKey(WorkItem, on_delete=models.CASCADE, related_name='blocks_set')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [('from_item', 'to_item')]

    def __str__(self):
        return f'{self.from_item_id} blocked by {self.to_item_id}'


class MoveLog(models.Model):
    """Audit log of Kanban status transitions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    work_item = models.ForeignKey(WorkItem, on_delete=models.CASCADE, related_name='move_log')
    moved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )
    from_status = models.CharField(max_length=20)
    to_status = models.CharField(max_length=20)
    moved_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-moved_at']

    def __str__(self):
        return f'{self.work_item_id}: {self.from_status} → {self.to_status}'
