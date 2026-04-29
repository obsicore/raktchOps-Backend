"""
Accounts app URL configuration.
All routes are mounted under /api/v1/auth/ by the root URLconf.
"""

from django.urls import path
from .views import (
    LoginView,
    LogoutView,
    UserMeView,
    InviteAcceptView,
    EmailVerificationView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    AdminApproveUserView,
    AdminInviteView,
    PendingUsersView,
    # New views
    SignupView,
    AllowedDomainListCreateView,
    AllowedDomainDetailView,
    UserListCreateView,
    UserDetailView,
    UserApproveView,
    UserDeactivateView,
    UserActivateView,
    UserChangeRoleView,
    ChangePasswordView,
    UserTodoListCreateView,
    UserTodoDetailView,
)

urlpatterns = [
    # Public auth endpoints
    path('login/', LoginView.as_view(), name='auth-login'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('me/', UserMeView.as_view(), name='auth-me'),
    path('signup/', SignupView.as_view(), name='auth-signup'),

    # Invite acceptance
    path('invite/accept/', InviteAcceptView.as_view(), name='auth-invite-accept'),

    # Email verification
    path('verify-email/', EmailVerificationView.as_view(), name='auth-verify-email'),

    # Password reset
    path('password-reset/', PasswordResetRequestView.as_view(), name='auth-password-reset-request'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='auth-password-reset-confirm'),

    # Password change (authenticated)
    path('change-password/', ChangePasswordView.as_view(), name='auth-change-password'),

    # Allowed domains CRUD (super admin)
    path('allowed-domains/', AllowedDomainListCreateView.as_view(), name='auth-allowed-domains'),
    path('allowed-domains/<int:pk>/', AllowedDomainDetailView.as_view(), name='auth-allowed-domain-detail'),

    # User management (super admin)
    path('users/', UserListCreateView.as_view(), name='auth-user-list'),
    path('users/<uuid:pk>/', UserDetailView.as_view(), name='auth-user-detail'),
    path('users/<uuid:pk>/approve/', UserApproveView.as_view(), name='auth-user-approve'),
    path('users/<uuid:pk>/deactivate/', UserDeactivateView.as_view(), name='auth-user-deactivate'),
    path('users/<uuid:pk>/activate/', UserActivateView.as_view(), name='auth-user-activate'),
    path('users/<uuid:pk>/change-role/', UserChangeRoleView.as_view(), name='auth-user-change-role'),

    # Personal todos
    path('todos/', UserTodoListCreateView.as_view(), name='user-todos'),
    path('todos/<uuid:pk>/', UserTodoDetailView.as_view(), name='user-todo-detail'),

    # Legacy admin endpoints (keep for backward compat)
    path('admin/approve/<uuid:user_id>/', AdminApproveUserView.as_view(), name='auth-admin-approve'),
    path('admin/invite/', AdminInviteView.as_view(), name='auth-admin-invite'),
    path('admin/pending-users/', PendingUsersView.as_view(), name='auth-admin-pending-users'),
]
