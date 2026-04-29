"""Permission helpers for the tasks app."""

from rbac.models import get_user_role, Role


def can_manage_task(user, task):
    """
    Admin/PM: always.
    Project owner (leader): within their project.
    Assignee: can update their own task.
    Others: read-only.
    """
    role = get_user_role(user)
    if role in (Role.SUPER_ADMIN, Role.ADMIN, Role.PROJECT_MANAGER):
        return True
    try:
        if task.module.project.owner.user == user:
            return True
    except Exception:
        pass
    # Assignee can update their own task
    if task.assignee and task.assignee == user:
        return True
    return False


def can_manage_task_in_project(user, project):
    """Can the user create/edit tasks in this project?"""
    role = get_user_role(user)
    if role in (Role.SUPER_ADMIN, Role.ADMIN, Role.PROJECT_MANAGER):
        return True
    try:
        return project.owner.user == user
    except Exception:
        return False
