"""
RBAC management views.
Role assignment is admin-only.
"""

import logging
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from rbac.models import UserRole, Role, get_user_role
from rbac.permissions import IsAdmin, IsActiveUser

logger = logging.getLogger(__name__)


class UserRoleView(APIView):
    """
    GET  /api/v1/rbac/users/<user_id>/role/  — retrieve a user's current role
    PUT  /api/v1/rbac/users/<user_id>/role/  — set a user's primary role (admin only)
    """
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdmin]

    def _is_super_admin(self, user) -> bool:
        return get_user_role(user) == Role.SUPER_ADMIN

    def _get_user(self, user_id):
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return None

    def get(self, request, user_id):
        user = self._get_user(user_id)
        if user is None:
            return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        current_role = get_user_role(user)
        return Response({
            'user_id': str(user.id),
            'email': user.email,
            'role': current_role,
        })

    def put(self, request, user_id):
        user = self._get_user(user_id)
        if user is None:
            return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        role_value = request.data.get('role')
        valid_roles = [r[0] for r in Role.choices]
        if role_value not in valid_roles:
            return Response(
                {
                    'detail': 'Validation error.',
                    'errors': {'role': [f'Invalid role. Choose one of: {", ".join(valid_roles)}']},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if role_value == Role.SUPER_ADMIN and not self._is_super_admin(request.user):
            return Response(
                {
                    'detail': 'Permission denied.',
                    'errors': {
                        'role': ['Only super admins can assign the super_admin role.'],
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Remove any existing primary role and set the new one
        UserRole.objects.filter(user=user, is_primary=True).update(is_primary=False)
        UserRole.objects.update_or_create(
            user=user,
            role=role_value,
            defaults={'is_primary': True},
        )

        logger.info(
            "Admin %s set role '%s' for user %s",
            request.user.email,
            role_value,
            user.email,
        )

        return Response({
            'detail': f"Role updated to '{role_value}' for {user.email}.",
            'user_id': str(user.id),
            'email': user.email,
            'role': role_value,
        })
