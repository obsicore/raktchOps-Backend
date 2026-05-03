"""Permission helpers for the modules app."""

from rbac.models import get_user_role, Role


def can_manage_module(user, project):
    """
    Super admin / admin / PM / team lead: always.
    Project leader (owner): allowed for their project.
    Others: read-only.
    """
    role = get_user_role(user)
    if role in (Role.SUPER_ADMIN, Role.ADMIN, Role.PROJECT_MANAGER, Role.TEAM_LEAD):
        return True
    try:
        return project.owner.user == user
    except Exception:
        return False
