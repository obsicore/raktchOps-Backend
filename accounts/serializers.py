"""
Serializers for accounts app — onboarding, auth, password reset.
"""

import logging
from django.conf import settings
from django.contrib.auth import authenticate
from django.utils import timezone
from datetime import timedelta
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    User,
    AccountStatus,
    InviteToken,
    InviteStatus,
    InviteRoleChoices,
    EmailVerificationToken,
    PasswordResetToken,
    AllowedDomain,
    UserTodo,
)
from rbac.models import UserRole, Role, get_user_role

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_allowed_domains():
    """Return active allowed domains from DB. Fall back to settings only if no DB records exist at all."""
    try:
        total_db = AllowedDomain.objects.count()
        if total_db > 0:
            # DB is the authority: return only active domains (may be empty list)
            return list(AllowedDomain.objects.filter(is_active=True).values_list('domain', flat=True))
    except Exception:
        pass
    return [d.lower().strip() for d in getattr(settings, 'ALLOWED_DOMAINS', ['raktch.com'])]


def _email_domain_allowed(email: str) -> bool:
    try:
        domain = email.split('@')[1].lower()
    except IndexError:
        return False
    return domain in _get_allowed_domains()


def _tokens_for_user(user):
    """Return a {access, refresh} dict for the given user."""
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


def _user_role_str(user) -> str:
    try:
        return get_user_role(user)
    except Exception:
        return Role.STAFF


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data['email'].lower().strip()
        password = data['password']
        request = self.context.get('request')

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                {'non_field_errors': ['Invalid credentials.']}
            )

        # Check lockout before attempting auth
        if user.is_locked_out():
            raise serializers.ValidationError(
                {'non_field_errors': [
                    'Your account is temporarily locked due to too many failed login attempts. '
                    'Please try again later.'
                ]}
            )

        # Check non-active states
        status_messages = {
            AccountStatus.INVITED: 'You must accept your invitation before logging in.',
            AccountStatus.PENDING_VERIFICATION: 'Please verify your email address before logging in.',
            AccountStatus.PENDING_APPROVAL: 'Your account is pending administrator approval.',
            AccountStatus.LOCKED: 'Your account has been locked. Please contact an administrator.',
            AccountStatus.DISABLED: 'Your account has been disabled. Please contact an administrator.',
        }
        if user.account_status in status_messages:
            raise serializers.ValidationError(
                {'non_field_errors': [status_messages[user.account_status]]}
            )

        # Authenticate password
        auth_user = authenticate(request=request, username=email, password=password)
        if auth_user is None:
            # Increment failed attempts
            user.failed_login_attempts += 1
            rate_limit = getattr(settings, 'AUTH_LOGIN_RATE_LIMIT', 5)
            lockout_minutes = getattr(settings, 'AUTH_LOCKOUT_MINUTES', 15)
            if user.failed_login_attempts >= rate_limit:
                user.locked_until = timezone.now() + timedelta(minutes=lockout_minutes)
                user.account_status = AccountStatus.LOCKED
                user.save(update_fields=['failed_login_attempts', 'locked_until', 'account_status'])
                raise serializers.ValidationError(
                    {'non_field_errors': [
                        f'Too many failed attempts. Your account has been locked for {lockout_minutes} minutes.'
                    ]}
                )
            user.save(update_fields=['failed_login_attempts'])
            raise serializers.ValidationError(
                {'non_field_errors': ['Invalid credentials.']}
            )

        # Successful login
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login = timezone.now()
        user.save(update_fields=['failed_login_attempts', 'locked_until', 'last_login'])

        data['user'] = user
        return data

    def to_representation(self, validated_data):
        user = validated_data['user']
        tokens = _tokens_for_user(user)

        # Fetch name from EmployeeProfile if available
        first_name = ''
        last_name = ''
        try:
            profile = user.employee_profile
            parts = (profile.full_name or '').split(' ', 1)
            first_name = parts[0] if parts else ''
            last_name = parts[1] if len(parts) > 1 else ''
        except Exception:
            pass

        return {
            'access': tokens['access'],
            'refresh': tokens['refresh'],
            'user': {
                'id': str(user.id),
                'email': user.email,
                'account_status': user.account_status,
                'role': _user_role_str(user),
                'first_name': first_name,
                'last_name': last_name,
            },
        }


# ---------------------------------------------------------------------------
# Invite accept
# ---------------------------------------------------------------------------

class InviteAcceptSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        token_value = data['token']
        email = data['email'].lower().strip()
        password = data['password']
        confirm = data['confirm_password']

        # Token lookup
        try:
            invite = InviteToken.objects.get(token=token_value)
        except InviteToken.DoesNotExist:
            raise serializers.ValidationError({'token': ['Invalid invite token.']})

        if invite.status == InviteStatus.CONSUMED:
            raise serializers.ValidationError({'token': ['This invite has already been used.']})

        if invite.status == InviteStatus.EXPIRED or invite.expires_at <= timezone.now():
            if invite.status != InviteStatus.EXPIRED:
                invite.status = InviteStatus.EXPIRED
                invite.save(update_fields=['status'])
            raise serializers.ValidationError({'token': ['This invite link has expired.']})

        # Email match
        if invite.email.lower() != email:
            raise serializers.ValidationError(
                {'email': ['The email address does not match the invitation.']}
            )

        # Domain check
        if not _email_domain_allowed(email):
            allowed = ', '.join(_get_allowed_domains())
            raise serializers.ValidationError(
                {'email': [f'Only email addresses from these domains are allowed: {allowed}']}
            )

        # Email uniqueness
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                {'email': ['A user with this email already exists.']}
            )

        # Passwords match
        if password != confirm:
            raise serializers.ValidationError({'confirm_password': ['Passwords do not match.']})

        data['invite'] = invite
        return data


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------

class EmailVerificationSerializer(serializers.Serializer):
    token = serializers.UUIDField()

    def validate(self, data):
        token_value = data['token']

        try:
            vtoken = EmailVerificationToken.objects.select_related('user').get(token=token_value)
        except EmailVerificationToken.DoesNotExist:
            raise serializers.ValidationError({'token': ['Invalid verification token.']})

        if vtoken.used_at is not None:
            raise serializers.ValidationError({'token': ['This verification link has already been used.']})

        if vtoken.expires_at <= timezone.now():
            raise serializers.ValidationError({'token': ['This verification link has expired.']})

        data['verification_token'] = vtoken
        return data


# ---------------------------------------------------------------------------
# Password reset request
# ---------------------------------------------------------------------------

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.lower().strip()


# ---------------------------------------------------------------------------
# Password reset confirm
# ---------------------------------------------------------------------------

class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        token_value = data['token']
        new_password = data['new_password']
        confirm = data['confirm_password']

        try:
            rtoken = PasswordResetToken.objects.select_related('user').get(token=token_value)
        except PasswordResetToken.DoesNotExist:
            raise serializers.ValidationError({'token': ['Invalid or expired reset token.']})

        if rtoken.used_at is not None:
            raise serializers.ValidationError({'token': ['This reset link has already been used.']})

        if rtoken.expires_at <= timezone.now():
            raise serializers.ValidationError({'token': ['This reset link has expired.']})

        if new_password != confirm:
            raise serializers.ValidationError({'confirm_password': ['Passwords do not match.']})

        data['reset_token'] = rtoken
        return data


# ---------------------------------------------------------------------------
# Current user (me)
# ---------------------------------------------------------------------------

class UserMeSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    first_name = serializers.SerializerMethodField()
    last_name = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    designation = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'account_status', 'date_joined', 'last_login', 'role', 'first_name', 'last_name', 'phone', 'designation']
        read_only_fields = fields

    def get_role(self, obj):
        return _user_role_str(obj)

    def get_first_name(self, obj):
        try:
            parts = (obj.employee_profile.full_name or '').split(' ', 1)
            return parts[0] if parts else ''
        except Exception:
            return ''

    def get_last_name(self, obj):
        try:
            parts = (obj.employee_profile.full_name or '').split(' ', 1)
            return parts[1] if len(parts) > 1 else ''
        except Exception:
            return ''

    def get_phone(self, obj):
        try:
            return obj.employee_profile.phone or ''
        except Exception:
            return ''

    def get_designation(self, obj):
        try:
            return obj.employee_profile.job_title or ''
        except Exception:
            return ''


# ---------------------------------------------------------------------------
# Admin: invite creation
# ---------------------------------------------------------------------------

class AdminInviteSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=InviteRoleChoices.choices, default=InviteRoleChoices.STAFF)

    def validate_email(self, value):
        email = value.lower().strip()
        if not _email_domain_allowed(email):
            allowed = ', '.join(_get_allowed_domains())
            raise serializers.ValidationError(
                f'Only email addresses from these domains are allowed: {allowed}'
            )
        return email


# ---------------------------------------------------------------------------
# Admin: pending user list
# ---------------------------------------------------------------------------

class PendingUserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'account_status', 'date_joined', 'role']
        read_only_fields = fields

    def get_role(self, obj):
        return _user_role_str(obj)


# ---------------------------------------------------------------------------
# RBAC: user role serializer
# ---------------------------------------------------------------------------

class UserRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Role.choices)


# ---------------------------------------------------------------------------
# Signup (open self-registration)
# ---------------------------------------------------------------------------

class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)

    def validate_email(self, value):
        email = value.lower().strip()
        try:
            domain = email.split('@')[1].lower()
        except IndexError:
            raise serializers.ValidationError('Invalid email address.')

        allowed = _get_allowed_domains()
        if domain not in allowed:
            raise serializers.ValidationError(
                f"Email domain '{domain}' is not allowed for registration."
            )

        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError('A user with this email address already exists.')

        return email

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({'confirm_password': ['Passwords do not match.']})
        return data


# ---------------------------------------------------------------------------
# AllowedDomain CRUD
# ---------------------------------------------------------------------------

class AllowedDomainSerializer(serializers.ModelSerializer):
    created_by_email = serializers.SerializerMethodField()

    class Meta:
        model = AllowedDomain
        fields = ['id', 'domain', 'is_active', 'notes', 'created_by', 'created_by_email', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_by', 'created_by_email', 'created_at', 'updated_at']

    def get_created_by_email(self, obj):
        if obj.created_by:
            return obj.created_by.email
        return None

    def validate_domain(self, value):
        value = value.lower().strip()
        # Basic domain format check
        import re
        if not re.match(r'^[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?(\.[a-z]{2,})+$', value):
            raise serializers.ValidationError(f"'{value}' does not look like a valid domain.")
        return value


# ---------------------------------------------------------------------------
# User management (admin)
# ---------------------------------------------------------------------------

class UserListSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    first_name = serializers.SerializerMethodField()
    last_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'account_status', 'is_active',
            'date_joined', 'last_login', 'role', 'full_name',
            'first_name', 'last_name',
        ]
        read_only_fields = fields

    def get_role(self, obj):
        return _user_role_str(obj)

    def get_full_name(self, obj):
        try:
            return obj.employee_profile.full_name
        except Exception:
            return ''

    def get_first_name(self, obj):
        try:
            parts = (obj.employee_profile.full_name or '').split(' ', 1)
            return parts[0]
        except Exception:
            return ''

    def get_last_name(self, obj):
        try:
            parts = (obj.employee_profile.full_name or '').split(' ', 1)
            return parts[1] if len(parts) > 1 else ''
        except Exception:
            return ''


class UserCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150, default='')
    last_name = serializers.CharField(max_length=150, default='')
    role = serializers.ChoiceField(choices=Role.choices, default=Role.STAFF)
    account_status = serializers.ChoiceField(choices=AccountStatus.choices, default=AccountStatus.ACTIVE)

    def validate_email(self, value):
        email = value.lower().strip()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError('A user with this email address already exists.')
        return email


class UserDetailSerializer(serializers.ModelSerializer):
    """Serializer for admin user detail/update. Email is read-only."""
    role = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'account_status', 'is_active',
            'failed_login_attempts', 'locked_until',
            'date_joined', 'last_login', 'role', 'full_name',
        ]
        read_only_fields = ['id', 'email', 'date_joined', 'last_login', 'failed_login_attempts', 'locked_until', 'role', 'full_name']

    def get_role(self, obj):
        return _user_role_str(obj)

    def get_full_name(self, obj):
        try:
            return obj.employee_profile.full_name
        except Exception:
            return ''


# ---------------------------------------------------------------------------
# Password change (authenticated user)
# ---------------------------------------------------------------------------

class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_new_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if data['new_password'] != data['confirm_new_password']:
            raise serializers.ValidationError({'confirm_new_password': ['Passwords do not match.']})
        return data


# ---------------------------------------------------------------------------
# UserTodo
# ---------------------------------------------------------------------------

class UserTodoSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserTodo
        fields = ['id', 'text', 'is_done', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
