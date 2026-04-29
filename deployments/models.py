"""
Deployments app: Environment, Release, Deployment.
No external integrations — record-keeping and approval state only.
"""
import uuid
from django.db import models
from django.utils import timezone


class Environment(models.Model):
    """Named deployment target (e.g. staging, production)."""
    TYPES = [('development', 'Development'), ('staging', 'Staging'), ('production', 'Production'), ('other', 'Other')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey('projects.Project', on_delete=models.CASCADE, related_name='environments')
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=TYPES, default='staging')
    url = models.URLField(max_length=300, blank=True)
    is_protected = models.BooleanField(default=False, help_text='Protected environments require explicit approval')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [('project', 'name')]
        ordering = ['type', 'name']

    def __str__(self):
        return f'{self.project.name} — {self.name}'


class ReleaseStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    PENDING = 'pending', 'Pending Approval'
    APPROVED = 'approved', 'Approved'
    RELEASED = 'released', 'Released'
    ROLLED_BACK = 'rolled_back', 'Rolled Back'


class Release(models.Model):
    """A versioned release bundle for a project."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey('projects.Project', on_delete=models.CASCADE, related_name='releases')
    version = models.CharField(max_length=50)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=ReleaseStatus.choices, default=ReleaseStatus.DRAFT, db_index=True)
    created_by = models.ForeignKey('people.EmployeeProfile', on_delete=models.PROTECT, related_name='releases_created')
    released_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('project', 'version')]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.project.name} v{self.version}'


class DeploymentStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    RUNNING = 'running', 'Running'
    SUCCESS = 'success', 'Success'
    FAILED = 'failed', 'Failed'
    ROLLED_BACK = 'rolled_back', 'Rolled Back'


class Deployment(models.Model):
    """A deployment event of a release to an environment."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    release = models.ForeignKey(Release, on_delete=models.CASCADE, related_name='deployments')
    environment = models.ForeignKey(Environment, on_delete=models.CASCADE, related_name='deployments')
    status = models.CharField(max_length=20, choices=DeploymentStatus.choices, default=DeploymentStatus.PENDING, db_index=True)
    deployed_by = models.ForeignKey('people.EmployeeProfile', on_delete=models.PROTECT, related_name='deployments_made')
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    # Rollback reference
    rolled_back_by = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='rollbacks'
    )

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f'{self.release} → {self.environment.name} [{self.status}]'
