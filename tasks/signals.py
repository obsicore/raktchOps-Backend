"""Signals for the tasks app — notifications on assignment and status changes."""

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver


@receiver(pre_save, sender='tasks.Task')
def _capture_old_state(sender, instance, **kwargs):
    """Capture old assignee and status before save."""
    if instance.pk:
        try:
            old = sender.objects.select_related('assignee').get(pk=instance.pk)
            instance._old_assignee_id = old.assignee_id
            instance._old_status = old.status
        except sender.DoesNotExist:
            instance._old_assignee_id = None
            instance._old_status = None
    else:
        instance._old_assignee_id = None
        instance._old_status = None


@receiver(post_save, sender='tasks.Task')
def _notify_task_changes(sender, instance, created, **kwargs):
    """
    - New task with assignee: notify assignee + super admins.
    - Assignee change: notify new assignee + super admins.
    - Status change to 'done': notify project lead + admins + super admins.
    """
    try:
        from notifications.models import NotificationType
        from notifications.services import (
            notify_project_lead_and_admins,
            notify_users_with_super_admins,
        )

        project_link = f'/projects/{instance.module.project_id}/board/'

        if created and instance.assignee_id:
            notify_users_with_super_admins(
                recipient_ids=[instance.assignee_id],
                notification_type=NotificationType.WORK_ITEM_ASSIGNED,
                title=f'Task assigned to you: {instance.title}',
                body=(
                    f"You have been assigned task '{instance.title}' "
                    f"in module '{instance.module.name}', "
                    f"project '{instance.module.project.name}'."
                ),
                link=project_link,
            )
            return

        if not created:
            old_assignee_id = getattr(instance, '_old_assignee_id', None)
            old_status = getattr(instance, '_old_status', None)

            # Assignee changed
            if instance.assignee_id and instance.assignee_id != old_assignee_id:
                notify_users_with_super_admins(
                    recipient_ids=[instance.assignee_id],
                    notification_type=NotificationType.WORK_ITEM_ASSIGNED,
                    title=f'Task assigned to you: {instance.title}',
                    body=(
                        f"You have been assigned task '{instance.title}' "
                        f"in module '{instance.module.name}', "
                        f"project '{instance.module.project.name}'."
                    ),
                    link=project_link,
                )

            # Status changed to done — notify leader
            if old_status != 'done' and instance.status == 'done':
                notify_project_lead_and_admins(
                    project=instance.module.project,
                    notification_type=NotificationType.STATUS_CHANGED,
                    title=f'Task completed: {instance.title}',
                    body=(
                        f"Task '{instance.title}' in module '{instance.module.name}' "
                        f"has been marked as done."
                    ),
                    link=project_link,
                )

    except Exception:
        pass
