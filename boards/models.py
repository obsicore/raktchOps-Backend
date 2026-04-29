"""
Boards app: KanbanBoard ties a project to a Kanban configuration.
Boards app is intentionally thin — Kanban state lives on WorkItem.status.
"""

import uuid
from django.db import models
from django.utils import timezone


class KanbanBoard(models.Model):
    """
    A named Kanban board for a project.
    One project can have one board (enforced by unique project FK).
    The board columns are the WorkItemStatus choices — no separate Column model.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.OneToOneField(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='kanban_board',
    )
    name = models.CharField(max_length=200, default='Kanban')
    # WIP limits per column (stored as JSON: {"in_progress": 5, ...})
    wip_limits = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'kanban board'
        verbose_name_plural = 'kanban boards'

    def __str__(self):
        return f'{self.project.name} — {self.name}'
