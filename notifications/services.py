"""Notification helper services for consistent fanout behavior."""

from __future__ import annotations

from collections.abc import Iterable

from accounts.models import AccountStatus, User
from rbac.models import Role, UserRole

from .models import Notification, NotificationType


def _active_user_ids_for_roles(roles: Iterable[str]) -> set:
    role_values = {role for role in roles if role}
    if not role_values:
        return set()

    user_ids = set(
        UserRole.objects.filter(
            role__in=role_values,
            user__account_status=AccountStatus.ACTIVE,
        ).values_list('user_id', flat=True)
    )

    # Django superusers should always behave as super admins.
    if Role.SUPER_ADMIN in role_values:
        user_ids.update(
            User.objects.filter(
                is_superuser=True,
                account_status=AccountStatus.ACTIVE,
            ).values_list('id', flat=True)
        )

    return user_ids


def _normalize_user_ids(recipient_ids: Iterable | None) -> set:
    if not recipient_ids:
        return set()

    normalized = set()
    for recipient in recipient_ids:
        if recipient is None:
            continue
        user_id = getattr(recipient, 'pk', recipient)
        if user_id:
            normalized.add(user_id)
    return normalized


def _keep_only_active_user_ids(user_ids: Iterable | None) -> set:
    normalized = _normalize_user_ids(user_ids)
    if not normalized:
        return set()
    return set(
        User.objects.filter(
            id__in=normalized,
            account_status=AccountStatus.ACTIVE,
        ).values_list('id', flat=True)
    )


def project_related_user_ids(
    *,
    project,
    include_admins: bool = True,
    extra_user_ids: Iterable | None = None,
) -> set:
    """
    Return active user IDs related to a project:
    - project owner
    - project members
    - optionally admin/super-admin roles
    - optional extra explicit user IDs
    """
    targets = set()

    owner_user_id = getattr(getattr(project, 'owner', None), 'user_id', None)
    if owner_user_id:
        targets.add(owner_user_id)

    try:
        targets.update(
            project.memberships.values_list('employee__user_id', flat=True)
        )
    except Exception:
        pass

    if include_admins:
        targets.update(_active_user_ids_for_roles([Role.ADMIN, Role.SUPER_ADMIN]))

    targets.update(_normalize_user_ids(extra_user_ids))
    return _keep_only_active_user_ids(targets)


def create_notification_fanout(
    *,
    recipient_ids: Iterable | None,
    notification_type: str = NotificationType.GENERAL,
    title: str,
    body: str = '',
    link: str = '',
    include_super_admins: bool = False,
    exclude_user_ids: Iterable | None = None,
) -> int:
    """
    Create identical notifications for multiple recipients in one call.
    Returns the number of notifications created.
    """
    targets = _keep_only_active_user_ids(recipient_ids)

    if include_super_admins:
        targets.update(_active_user_ids_for_roles([Role.SUPER_ADMIN]))

    targets.difference_update(_normalize_user_ids(exclude_user_ids))
    if not targets:
        return 0

    notifications = [
        Notification(
            recipient_id=user_id,
            type=notification_type,
            title=title,
            body=body,
            link=link,
        )
        for user_id in targets
    ]
    Notification.objects.bulk_create(notifications)
    return len(notifications)


def notify_admins_and_super_admins(
    *,
    notification_type: str = NotificationType.GENERAL,
    title: str,
    body: str = '',
    link: str = '',
) -> int:
    recipient_ids = _active_user_ids_for_roles([Role.ADMIN, Role.SUPER_ADMIN])
    return create_notification_fanout(
        recipient_ids=recipient_ids,
        notification_type=notification_type,
        title=title,
        body=body,
        link=link,
    )


def notify_users_with_super_admins(
    *,
    recipient_ids: Iterable | None,
    notification_type: str = NotificationType.GENERAL,
    title: str,
    body: str = '',
    link: str = '',
) -> int:
    return create_notification_fanout(
        recipient_ids=recipient_ids,
        notification_type=notification_type,
        title=title,
        body=body,
        link=link,
        include_super_admins=True,
    )


def notify_project_lead_and_admins(
    *,
    project,
    notification_type: str = NotificationType.GENERAL,
    title: str,
    body: str = '',
    link: str = '',
) -> int:
    recipient_ids = _active_user_ids_for_roles([Role.ADMIN, Role.SUPER_ADMIN])
    leader_user_id = getattr(getattr(project, 'owner', None), 'user_id', None)
    if leader_user_id:
        recipient_ids.add(leader_user_id)

    return create_notification_fanout(
        recipient_ids=recipient_ids,
        notification_type=notification_type,
        title=title,
        body=body,
        link=link,
    )


def notify_project_related_users(
    *,
    project,
    notification_type: str = NotificationType.GENERAL,
    title: str,
    body: str = '',
    link: str = '',
    include_admins: bool = True,
    extra_user_ids: Iterable | None = None,
    exclude_user_ids: Iterable | None = None,
) -> int:
    recipients = project_related_user_ids(
        project=project,
        include_admins=include_admins,
        extra_user_ids=extra_user_ids,
    )
    return create_notification_fanout(
        recipient_ids=recipients,
        notification_type=notification_type,
        title=title,
        body=body,
        link=link,
        exclude_user_ids=exclude_user_ids,
    )
