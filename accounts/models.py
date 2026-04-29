"""
Custom User model for RAKTCH.
Uses email as the unique identifier (not username).
Tracks account lifecycle state for onboarding and access control.
"""

import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class AccountStatus(models.TextChoices):
    INVITED = 'invited', 'Invited'
    PENDING_VERIFICATION = 'pending_verification', 'Pending Verification'
    PENDING_APPROVAL = 'pending_approval', 'Pending Approval'
    ACTIVE = 'active', 'Active'
    LOCKED = 'locked', 'Locked'
    DISABLED = 'disabled', 'Disabled'


class CustomUserManager(BaseUserManager):
    """Manager for email-based user authentication."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email address is required.')
        email = self.normalize_email(email)
        extra_fields.setdefault('account_status', AccountStatus.PENDING_VERIFICATION)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('account_status', AccountStatus.ACTIVE)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Core authentication user.
    Extended profile data lives in people.EmployeeProfile.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)

    # Django built-in flags
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    # Lifecycle state
    account_status = models.CharField(
        max_length=30,
        choices=AccountStatus.choices,
        default=AccountStatus.PENDING_VERIFICATION,
        db_index=True,
    )

    # Rate limiting / lockout support
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    date_joined = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(null=True, blank=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = 'user'
        verbose_name_plural = 'users'
        ordering = ['email']

    def __str__(self):
        return self.email

    @property
    def is_account_active(self):
        return self.account_status == AccountStatus.ACTIVE

    def is_locked_out(self):
        if self.locked_until and self.locked_until > timezone.now():
            return True
        return False

    def reset_lockout(self):
        self.failed_login_attempts = 0
        self.locked_until = None
        self.save(update_fields=['failed_login_attempts', 'locked_until'])


class InviteRoleChoices(models.TextChoices):
    SUPER_ADMIN = 'super_admin', 'Super Admin'
    ADMIN = 'admin', 'Admin'
    PROJECT_MANAGER = 'project_manager', 'Project Manager'
    TEAM_LEAD = 'team_lead', 'Team Lead'
    STAFF = 'staff', 'Staff'


class InviteStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    CONSUMED = 'consumed', 'Consumed'
    EXPIRED = 'expired', 'Expired'


class InviteToken(models.Model):
    """Tracks outbound invitations. Each token is single-use with an expiry."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(db_index=True)
    role = models.CharField(
        max_length=30,
        choices=InviteRoleChoices.choices,
        default=InviteRoleChoices.STAFF,
    )
    invited_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_invites',
    )
    token = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=InviteStatus.choices,
        default=InviteStatus.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'invite token'
        verbose_name_plural = 'invite tokens'
        ordering = ['-created_at']

    def __str__(self):
        return f'Invite({self.email}, {self.status})'

    @property
    def is_valid(self):
        return (
            self.status == InviteStatus.PENDING
            and self.expires_at > timezone.now()
        )


class EmailVerificationToken(models.Model):
    """Single-use token for verifying a user's email address."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='verification_tokens',
    )
    token = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'email verification token'
        verbose_name_plural = 'email verification tokens'
        ordering = ['-created_at']

    def __str__(self):
        return f'VerifyToken({self.user.email})'

    @property
    def is_valid(self):
        return self.used_at is None and self.expires_at > timezone.now()


class PasswordResetToken(models.Model):
    """Single-use token for resetting a user's password."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='password_reset_tokens',
    )
    token = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'password reset token'
        verbose_name_plural = 'password reset tokens'
        ordering = ['-created_at']

    def __str__(self):
        return f'ResetToken({self.user.email})'

    @property
    def is_valid(self):
        return self.used_at is None and self.expires_at > timezone.now()


class AllowedDomain(models.Model):
    """
    Domains allowed for self-signup.
    Managed exclusively by super admin from the frontend dashboard.
    """

    domain = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        'accounts.User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_domains',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'allowed domain'
        verbose_name_plural = 'allowed domains'
        ordering = ['domain']

    def save(self, *args, **kwargs):
        self.domain = self.domain.lower().strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.domain


class UserTodo(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='todos',
    )
    text = models.CharField(max_length=500)
    is_done = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.user.email}: {self.text[:50]}'
