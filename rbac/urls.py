"""
RBAC app URL configuration.
All routes are mounted under /api/v1/rbac/ by the root URLconf.
"""

from django.urls import path
from .views import UserRoleView

urlpatterns = [
    path('users/<uuid:user_id>/role/', UserRoleView.as_view(), name='rbac-user-role'),
]
