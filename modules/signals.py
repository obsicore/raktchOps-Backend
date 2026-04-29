"""Signals for the modules app — create notifications on deadline changes."""

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver


@receiver(pre_save, sender='modules.Module')
def _capture_old_deadline(sender, instance, **kwargs):
    """Store old deadline before save so post_save can detect changes."""
    if instance.pk:
        try:
            old = sender.objects.get(pk=instance.pk)
            instance._old_deadline = old.deadline
        except sender.DoesNotExist:
            instance._old_deadline = None
    else:
        instance._old_deadline = None


@receiver(post_save, sender='modules.Module')
def _notify_deadline_change(sender, instance, created, **kwargs):
    """Notify project lead/admins when a module deadline changes."""
    if created:
        return
    old_deadline = getattr(instance, '_old_deadline', None)
    if old_deadline == instance.deadline:
        return

    try:
        from notifications.models import NotificationType
        from notifications.services import notify_project_lead_and_admins

        notify_project_lead_and_admins(
            project=instance.project,
            notification_type=NotificationType.GENERAL,
            title=f'Module deadline changed: {instance.name}',
            body=(
                f"The deadline for module '{instance.name}' in project "
                f"'{instance.project.name}' was updated to {instance.deadline}."
            ),
            link=f'/projects/{instance.project_id}/modules/{instance.pk}/',
        )
    except Exception:
        pass
