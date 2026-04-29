"""
Centralized DRF permission classes for RAKTCH.
All permission logic must pass through these classes rather than
being scattered across views.
"""

from rest_framework.permissions import BasePermission
from .models import get_user_role, Role, is_admin as _is_admin_role


class IsActiveUser(BasePermission):
    """Allow only users with account_status == active."""

    message = 'Your account is not active.'

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.account_status == 'active'
        )


class IsAdmin(BasePermission):
    """Allow super_admin or admin role."""

    message = 'Admin role required.'

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and _is_admin_role(request.user)
        )


class IsSuperAdmin(BasePermission):
    """Allow only super_admin role (or Django superuser)."""
    message = 'Super admin role required.'

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        from .models import get_user_role, Role
        return get_user_role(request.user) == Role.SUPER_ADMIN


class IsAdminOrProjectManager(BasePermission):
    """Allow super_admin, admin, or project_manager roles."""

    message = 'Admin or Project Manager role required.'

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return get_user_role(request.user) in (Role.SUPER_ADMIN, Role.ADMIN, Role.PROJECT_MANAGER)


class IsAdminOrProjectManagerOrTeamLead(BasePermission):
    """Allow super_admin, admin, project_manager, or team_lead roles."""

    message = 'Admin, Project Manager, or Team Lead role required.'

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return get_user_role(request.user) in (
            Role.SUPER_ADMIN, Role.ADMIN, Role.PROJECT_MANAGER, Role.TEAM_LEAD
        )


class IsAdminOrReadOnly(BasePermission):
    """Allow read access to any authenticated active user; write only to admins."""

    message = 'Admin role required for write operations.'

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        return _is_admin_role(request.user)


class IsOwnerOrAdmin(BasePermission):
    """Object-level: allow owner of the object or admin."""

    message = 'You do not have permission to access this object.'

    def has_object_permission(self, request, view, obj):
        if not (request.user and request.user.is_authenticated):
            return False
        if _is_admin_role(request.user):
            return True
        # obj must expose an 'owner' or 'user' attribute
        owner = getattr(obj, 'owner', None) or getattr(obj, 'user', None)
        return owner == request.user
