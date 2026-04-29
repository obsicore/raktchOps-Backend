"""
Notifications app: Notification model and event triggers.
"""
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class NotificationType(models.TextChoices):
    WORK_ITEM_ASSIGNED = 'work_item_assigned', 'Work Item Assigned'
    COMMENT_ADDED = 'comment_added', 'Comment Added'
    STATUS_CHANGED = 'status_changed', 'Status Changed'
    SPRINT_STARTED = 'sprint_started', 'Sprint Started'
    MILESTONE_DUE = 'milestone_due', 'Milestone Due Soon'
    DEPLOYMENT_STATUS = 'deployment_status', 'Deployment Status'
    PROJECT_ADDED = 'project_added', 'Added to Project'
    GENERAL = 'general', 'General'


class Notification(models.Model):
    """
    In-app notification for a user.
    Created programmatically by helper functions (see signals.py or service layer).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    type = models.CharField(max_length=30, choices=NotificationType.choices, default=NotificationType.GENERAL, db_index=True)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    # Optional deep-link to the related object
    link = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'notification'

    def __str__(self):
        return f'[{self.type}] → {self.recipient.email}'

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])
