"""
Auth, onboarding, and account management views for the accounts app.
All endpoints are under /api/v1/auth/.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone

from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from rbac.permissions import IsAdmin, IsActiveUser, IsSuperAdmin
from rbac.models import UserRole, Role

from .models import (
    User,
    AccountStatus,
    InviteToken,
    InviteStatus,
    EmailVerificationToken,
    PasswordResetToken,
    AllowedDomain,
    UserTodo,
)
from .serializers import (
    LoginSerializer,
    InviteAcceptSerializer,
    EmailVerificationSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    UserMeSerializer,
    AdminInviteSerializer,
    PendingUserSerializer,
    SignupSerializer,
    AllowedDomainSerializer,
    UserListSerializer,
    UserCreateSerializer,
    UserDetailSerializer,
    ChangePasswordSerializer,
    UserTodoSerializer,
)
from .emails import (
    send_invite_email,
    send_verification_email,
    send_password_reset_email,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------

class LoginView(APIView):
    """POST /api/v1/auth/login/"""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(
                {'detail': 'Authentication failed.', 'errors': serializer.errors},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(serializer.to_representation(serializer.validated_data))


class LogoutView(APIView):
    """POST /api/v1/auth/logout/"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                # Blacklisting requires rest_framework_simplejwt.token_blacklist app.
                # Since it may not be installed, we fail gracefully.
                token.blacklist()
            except (TokenError, AttributeError, Exception):
                # Token already invalid or blacklisting not available — that is fine.
                pass
        return Response({'detail': 'Logged out successfully.'}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------

class UserMeView(APIView):
    """GET/PATCH /api/v1/auth/me/"""
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        serializer = UserMeSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        from people.models import EmployeeProfile

        first_name = (request.data.get('first_name') or '').strip()
        last_name = (request.data.get('last_name') or '').strip()
        phone = (request.data.get('phone') or '').strip()
        designation = (request.data.get('designation') or '').strip()

        if not first_name:
            return Response(
                {'detail': 'Validation failed.', 'errors': {'first_name': ['First name is required.']}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        full_name = f'{first_name} {last_name}'.strip()

        try:
            profile = request.user.employee_profile
            profile.full_name = full_name
            if phone:
                profile.phone = phone
            if designation:
                profile.job_title = designation
            profile.save(update_fields=['full_name', 'phone', 'job_title', 'updated_at'])
        except EmployeeProfile.DoesNotExist:
            EmployeeProfile.objects.create(
                user=request.user,
                full_name=full_name,
                work_email=request.user.email,
                phone=phone,
                job_title=designation,
            )

        logger.info('%s updated their profile', request.user.email)
        return Response(UserMeSerializer(request.user).data)


# ---------------------------------------------------------------------------
# Invite acceptance
# ---------------------------------------------------------------------------

class InviteAcceptView(APIView):
    """POST /api/v1/auth/invite/accept/ — no auth required."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = InviteAcceptSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'detail': 'Invite acceptance failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        invite = data['invite']
        email = data['email'].lower().strip()
        password = data['password']

        # Validate password against Django validators
        try:
            validate_password(password)
        except DjangoValidationError as exc:
            return Response(
                {'detail': 'Password is not strong enough.', 'errors': {'password': list(exc.messages)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create user
        user = User.objects.create_user(
            email=email,
            password=password,
            account_status=AccountStatus.PENDING_VERIFICATION,
        )

        # Assign role from invite
        UserRole.objects.create(user=user, role=invite.role, is_primary=True)

        # Consume invite
        invite.status = InviteStatus.CONSUMED
        invite.consumed_at = timezone.now()
        invite.save(update_fields=['status', 'consumed_at'])

        # Create verification token
        expiry_hours = getattr(settings, 'AUTH_EMAIL_VERIFICATION_EXPIRY_HOURS', 24)
        vtoken = EmailVerificationToken.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=expiry_hours),
        )

        # Send verification email (fail-safe)
        send_verification_email(user, vtoken)

        return Response(
            {
                'detail': (
                    'Account created. Please check your email to verify your address.'
                )
            },
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------

class EmailVerificationView(APIView):
    """POST /api/v1/auth/verify-email/ — no auth required."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = EmailVerificationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'detail': 'Verification failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vtoken = serializer.validated_data['verification_token']
        user = vtoken.user

        # Mark token used
        vtoken.used_at = timezone.now()
        vtoken.save(update_fields=['used_at'])

        # Advance account status
        require_approval = getattr(settings, 'AUTH_REQUIRE_APPROVAL', True)
        if require_approval:
            user.account_status = AccountStatus.PENDING_APPROVAL
            msg = 'Email verified. Your account is now pending administrator approval.'
        else:
            user.account_status = AccountStatus.ACTIVE
            msg = 'Email verified. Your account is now active.'

        user.save(update_fields=['account_status'])

        if require_approval:
            try:
                from notifications.models import NotificationType
                from notifications.services import notify_admins_and_super_admins

                notify_admins_and_super_admins(
                    notification_type=NotificationType.GENERAL,
                    title='New account pending approval',
                    body=(
                        f'User {user.email} completed email verification and is '
                        'waiting for account approval.'
                    ),
                    link='/dashboard/admin/users',
                )
            except Exception:
                pass

        return Response({'detail': msg})


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

class PasswordResetRequestView(APIView):
    """POST /api/v1/auth/password-reset/ — no auth required."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            # Always return 200 to avoid leaking whether an email exists
            return Response({'detail': 'If that email is registered, a reset link has been sent.'})

        email = serializer.validated_data['email']
        expiry_minutes = getattr(settings, 'AUTH_PASSWORD_RESET_EXPIRY_MINUTES', 30)

        try:
            user = User.objects.get(email=email)
            if user.account_status in (AccountStatus.ACTIVE, AccountStatus.PENDING_APPROVAL):
                rtoken = PasswordResetToken.objects.create(
                    user=user,
                    expires_at=timezone.now() + timedelta(minutes=expiry_minutes),
                )
                send_password_reset_email(user, rtoken)
        except User.DoesNotExist:
            pass  # Do not leak

        return Response({'detail': 'If that email is registered, a reset link has been sent.'})


class PasswordResetConfirmView(APIView):
    """POST /api/v1/auth/password-reset/confirm/ — no auth required."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'detail': 'Password reset failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rtoken = serializer.validated_data['reset_token']
        new_password = serializer.validated_data['new_password']

        # Validate password strength
        try:
            validate_password(new_password, user=rtoken.user)
        except DjangoValidationError as exc:
            return Response(
                {'detail': 'Password is not strong enough.', 'errors': {'new_password': list(exc.messages)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = rtoken.user
        user.set_password(new_password)
        user.save(update_fields=['password'])

        rtoken.used_at = timezone.now()
        rtoken.save(update_fields=['used_at'])

        return Response({'detail': 'Password has been reset successfully. You may now log in.'})


# ---------------------------------------------------------------------------
# Admin: approve pending user
# ---------------------------------------------------------------------------

class AdminApproveUserView(APIView):
    """POST /api/v1/auth/admin/approve/<user_id>/"""
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdmin]

    def post(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        if user.account_status != AccountStatus.PENDING_APPROVAL:
            return Response(
                {'detail': f'User account status is "{user.account_status}", not pending_approval.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.account_status = AccountStatus.ACTIVE
        user.save(update_fields=['account_status'])

        try:
            from notifications.models import NotificationType
            from notifications.services import notify_users_with_super_admins

            notify_users_with_super_admins(
                recipient_ids=[user.id],
                notification_type=NotificationType.STATUS_CHANGED,
                title='Account approved',
                body='Your account has been approved and activated.',
                link='/dashboard/staff',
            )
        except Exception:
            pass

        return Response({'detail': f'User {user.email} has been approved and activated.'})


# ---------------------------------------------------------------------------
# Admin: send invite
# ---------------------------------------------------------------------------

class AdminInviteView(APIView):
    """POST /api/v1/auth/admin/invite/"""
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdmin]

    def post(self, request):
        serializer = AdminInviteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'detail': 'Invite creation failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = serializer.validated_data['email']
        role = serializer.validated_data['role']

        # Check for an already active user
        if User.objects.filter(email=email).exists():
            return Response(
                {'detail': 'A user with this email address already exists.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Expire any previous pending invites for the same email
        InviteToken.objects.filter(
            email=email, status=InviteStatus.PENDING
        ).update(status=InviteStatus.EXPIRED)

        expiry_hours = getattr(settings, 'AUTH_INVITE_EXPIRY_HOURS', 72)
        invite = InviteToken.objects.create(
            email=email,
            role=role,
            invited_by=request.user,
            expires_at=timezone.now() + timedelta(hours=expiry_hours),
        )

        send_invite_email(invite)

        return Response(
            {
                'detail': f'Invitation sent to {email}.',
                'invite_id': str(invite.id),
            },
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Admin: list pending users
# ---------------------------------------------------------------------------

class PendingUsersView(APIView):
    """GET /api/v1/auth/admin/pending-users/"""
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdmin]

    def get(self, request):
        users = User.objects.filter(
            account_status=AccountStatus.PENDING_APPROVAL
        ).order_by('date_joined')
        serializer = PendingUserSerializer(users, many=True)
        return Response({'count': users.count(), 'results': serializer.data})


# ---------------------------------------------------------------------------
# Signup (self-registration via allowed domain)
# ---------------------------------------------------------------------------

class SignupView(APIView):
    """POST /api/v1/auth/signup/ — public, no auth required."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        serializer = SignupSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'detail': 'Signup failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        password = data['password']

        try:
            validate_password(password)
        except DjangoValidationError as exc:
            return Response(
                {'detail': 'Password is not strong enough.', 'errors': {'password': list(exc.messages)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.create_user(
            email=data['email'],
            password=password,
            account_status=AccountStatus.PENDING_APPROVAL,
        )

        # Assign default staff role
        from rbac.models import UserRole, Role
        UserRole.objects.create(user=user, role=Role.STAFF, is_primary=True)

        # Create employee profile with name info
        from people.models import EmployeeProfile
        full_name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip() or data['email']
        EmployeeProfile.objects.get_or_create(
            user=user,
            defaults={
                'full_name': full_name,
                'work_email': data['email'],
            },
        )

        try:
            from notifications.models import NotificationType
            from notifications.services import notify_admins_and_super_admins

            notify_admins_and_super_admins(
                notification_type=NotificationType.GENERAL,
                title='New signup pending approval',
                body=f'User {user.email} signed up and is waiting for approval.',
                link='/dashboard/admin/users',
            )
        except Exception:
            pass

        return Response(
            {'detail': 'Account created. Your account is pending administrator approval.'},
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# AllowedDomain CRUD (super admin only)
# ---------------------------------------------------------------------------

from rest_framework.pagination import PageNumberPagination


class AllowedDomainListCreateView(APIView):
    """
    GET  /api/v1/auth/allowed-domains/
    POST /api/v1/auth/allowed-domains/
    """
    permission_classes = [IsAuthenticated, IsActiveUser, IsSuperAdmin]

    def get(self, request):
        qs = AllowedDomain.objects.all().order_by('domain')
        serializer = AllowedDomainSerializer(qs, many=True)
        return Response({'count': qs.count(), 'results': serializer.data})

    def post(self, request):
        serializer = AllowedDomainSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'detail': 'Validation failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        domain = serializer.save(created_by=request.user)
        logger.info('%s created allowed domain %s', request.user.email, domain.domain)
        return Response(AllowedDomainSerializer(domain).data, status=status.HTTP_201_CREATED)


class AllowedDomainDetailView(APIView):
    """
    GET    /api/v1/auth/allowed-domains/<id>/
    PATCH  /api/v1/auth/allowed-domains/<id>/
    DELETE /api/v1/auth/allowed-domains/<id>/
    """
    permission_classes = [IsAuthenticated, IsActiveUser, IsSuperAdmin]

    def _get_domain(self, pk):
        try:
            return AllowedDomain.objects.get(pk=pk)
        except AllowedDomain.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound('Allowed domain not found.')

    def get(self, request, pk):
        return Response(AllowedDomainSerializer(self._get_domain(pk)).data)

    def patch(self, request, pk):
        domain_obj = self._get_domain(pk)
        serializer = AllowedDomainSerializer(domain_obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(
                {'detail': 'Validation failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        domain_obj = serializer.save()
        logger.info('%s updated allowed domain %s', request.user.email, domain_obj.domain)
        return Response(AllowedDomainSerializer(domain_obj).data)

    def put(self, request, pk):
        return self.patch(request, pk)

    def delete(self, request, pk):
        domain_obj = self._get_domain(pk)
        name = domain_obj.domain
        domain_obj.delete()
        logger.info('%s deleted allowed domain %s', request.user.email, name)
        return Response({'detail': f"Domain '{name}' deleted."})


# ---------------------------------------------------------------------------
# User management (super admin)
# ---------------------------------------------------------------------------

class UserListCreateView(APIView):
    """
    GET  /api/v1/auth/users/   — list all users (admin only)
    POST /api/v1/auth/users/   — create user (admin only)
    """
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdmin]

    def get(self, request):
        qs = User.objects.all().order_by('email')

        # Filters
        account_status_filter = request.query_params.get('account_status')
        if account_status_filter:
            qs = qs.filter(account_status=account_status_filter)

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(email__icontains=search)

        paginator = PageNumberPagination()
        paginator.page_size = 20
        page = paginator.paginate_queryset(qs, request)
        serializer = UserListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = UserCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'detail': 'Validation failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = serializer.validated_data
        user = User.objects.create_user(
            email=data['email'],
            password=data['password'],
            account_status=data.get('account_status', AccountStatus.ACTIVE),
        )

        from rbac.models import UserRole
        role = data.get('role', 'staff')
        UserRole.objects.create(user=user, role=role, is_primary=True)

        from people.models import EmployeeProfile
        first = data.get('first_name', '')
        last = data.get('last_name', '')
        full_name = f'{first} {last}'.strip() or data['email']
        EmployeeProfile.objects.get_or_create(
            user=user,
            defaults={'full_name': full_name, 'work_email': data['email']},
        )

        logger.info('%s created user %s', request.user.email, user.email)
        return Response(UserListSerializer(user).data, status=status.HTTP_201_CREATED)


class UserDetailView(APIView):
    """
    GET   /api/v1/auth/users/<id>/
    PATCH /api/v1/auth/users/<id>/
    """
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdmin]

    def _get_user(self, pk):
        try:
            return User.objects.get(pk=pk)
        except User.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound('User not found.')

    def get(self, request, pk):
        return Response(UserDetailSerializer(self._get_user(pk)).data)

    def patch(self, request, pk):
        user = self._get_user(pk)
        # Never allow email update
        data = {k: v for k, v in request.data.items() if k != 'email'}
        serializer = UserDetailSerializer(user, data=data, partial=True)
        if not serializer.is_valid():
            return Response(
                {'detail': 'Validation failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer.save()
        return Response(UserDetailSerializer(user).data)


class UserApproveView(APIView):
    """POST /api/v1/auth/users/<id>/approve/"""
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdmin]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
        user.account_status = AccountStatus.ACTIVE
        user.save(update_fields=['account_status'])

        try:
            from notifications.models import NotificationType
            from notifications.services import notify_users_with_super_admins

            notify_users_with_super_admins(
                recipient_ids=[user.id],
                notification_type=NotificationType.STATUS_CHANGED,
                title='Account approved',
                body='Your account has been approved and activated.',
                link='/dashboard/staff',
            )
        except Exception:
            pass

        return Response({'detail': f'User {user.email} approved and activated.'})


class UserDeactivateView(APIView):
    """POST /api/v1/auth/users/<id>/deactivate/"""
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdmin]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
        if user == request.user:
            return Response({'detail': 'You cannot deactivate yourself.'}, status=status.HTTP_400_BAD_REQUEST)
        user.account_status = AccountStatus.DISABLED
        user.save(update_fields=['account_status'])
        return Response({'detail': f'User {user.email} deactivated.'})


class UserActivateView(APIView):
    """POST /api/v1/auth/users/<id>/activate/"""
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdmin]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
        user.account_status = AccountStatus.ACTIVE
        user.save(update_fields=['account_status'])
        return Response({'detail': f'User {user.email} activated.'})


class UserChangeRoleView(APIView):
    """POST /api/v1/auth/users/<id>/change-role/"""
    permission_classes = [IsAuthenticated, IsActiveUser, IsAdmin]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        from rbac.models import UserRole, Role
        role = request.data.get('role')
        if role not in [r[0] for r in Role.choices]:
            return Response({'detail': 'Invalid role.', 'errors': {'role': [f'Must be one of: {", ".join([r[0] for r in Role.choices])}']}}, status=status.HTTP_400_BAD_REQUEST)

        UserRole.objects.filter(user=user).update(is_primary=False)
        UserRole.objects.update_or_create(
            user=user, role=role,
            defaults={'is_primary': True},
        )
        logger.info('%s changed role of %s to %s', request.user.email, user.email, role)
        return Response({'detail': f'Role changed to {role}.', 'role': role})


# ---------------------------------------------------------------------------
# Password change (authenticated user)
# ---------------------------------------------------------------------------

class ChangePasswordView(APIView):
    """POST /api/v1/auth/change-password/"""
    permission_classes = [IsAuthenticated, IsActiveUser]

    def post(self, request):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        serializer = ChangePasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'detail': 'Validation failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        user = request.user

        if not user.check_password(data['current_password']):
            return Response(
                {'detail': 'Current password is incorrect.', 'errors': {'current_password': ['Incorrect password.']}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_password(data['new_password'], user=user)
        except DjangoValidationError as exc:
            return Response(
                {'detail': 'Password is not strong enough.', 'errors': {'new_password': list(exc.messages)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(data['new_password'])
        user.save(update_fields=['password'])
        logger.info('%s changed their password', user.email)
        return Response({'detail': 'Password changed successfully.'})


# ---------------------------------------------------------------------------
# Personal todos
# ---------------------------------------------------------------------------

class UserTodoListCreateView(APIView):
    """
    GET  /api/v1/auth/todos/    — list own todos
    POST /api/v1/auth/todos/    — create todo
    """
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        todos = UserTodo.objects.filter(user=request.user)
        return Response(UserTodoSerializer(todos, many=True).data)

    def post(self, request):
        text = str(request.data.get('text', '')).strip()
        if not text:
            return Response({'detail': 'text is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(text) > 500:
            return Response({'detail': 'text too long (max 500 chars).'}, status=status.HTTP_400_BAD_REQUEST)
        todo = UserTodo.objects.create(user=request.user, text=text)
        return Response(UserTodoSerializer(todo).data, status=status.HTTP_201_CREATED)


class UserTodoDetailView(APIView):
    """
    PATCH  /api/v1/auth/todos/<pk>/   — toggle done or update text
    DELETE /api/v1/auth/todos/<pk>/   — delete
    """
    permission_classes = [IsAuthenticated, IsActiveUser]

    def _get(self, request, pk):
        try:
            return UserTodo.objects.get(pk=pk, user=request.user)
        except UserTodo.DoesNotExist:
            raise NotFound('Todo not found.')

    def patch(self, request, pk):
        todo = self._get(request, pk)
        if 'is_done' in request.data:
            todo.is_done = bool(request.data['is_done'])
        if 'text' in request.data:
            text = str(request.data['text']).strip()
            if text:
                todo.text = text
        todo.save()
        return Response(UserTodoSerializer(todo).data)

    def delete(self, request, pk):
        todo = self._get(request, pk)
        todo.delete()
        return Response({'detail': 'Deleted.'}, status=status.HTTP_204_NO_CONTENT)
