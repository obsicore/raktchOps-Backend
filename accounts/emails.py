"""
Email helper functions for the accounts app.
All functions fail safely: exceptions are caught and logged so they never
crash the calling view. The console backend is used in development.
"""

import logging
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)


def send_invite_email(invite_token):
    """
    Send an invitation email to the invited address.
    invite_token: InviteToken instance
    """
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    accept_url = f"{frontend_url}/auth/invite?token={invite_token.token}"
    subject = f"You have been invited to {getattr(settings, 'APP_NAME', 'RAKTCH')}"
    message = (
        f"Hello,\n\n"
        f"You have been invited to join RAKTCH as {invite_token.get_role_display()}.\n\n"
        f"Accept your invitation here:\n{accept_url}\n\n"
        f"This link expires in {getattr(settings, 'AUTH_INVITE_EXPIRY_HOURS', 72)} hours.\n\n"
        f"If you did not expect this invitation, please ignore this email."
    )
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invite_token.email],
            fail_silently=False,
        )
    except Exception as exc:
        logger.error(
            "Failed to send invite email to %s: %s",
            invite_token.email,
            exc,
            exc_info=True,
        )


def send_verification_email(user, verification_token):
    """
    Send an email verification link to the user.
    user: User instance
    verification_token: EmailVerificationToken instance
    """
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    verify_url = f"{frontend_url}/auth/verify-email?token={verification_token.token}"
    subject = "Verify your email address — RAKTCH"
    message = (
        f"Hello,\n\n"
        f"Please verify your email address by clicking the link below:\n"
        f"{verify_url}\n\n"
        f"This link expires in {getattr(settings, 'AUTH_EMAIL_VERIFICATION_EXPIRY_HOURS', 24)} hours.\n\n"
        f"If you did not register for RAKTCH, please ignore this email."
    )
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception as exc:
        logger.error(
            "Failed to send verification email to %s: %s",
            user.email,
            exc,
            exc_info=True,
        )


def send_password_reset_email(user, reset_token):
    """
    Send a password reset link to the user.
    user: User instance
    reset_token: PasswordResetToken instance
    """
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    reset_url = (
        f"{frontend_url}/auth/reset-password"
        f"?token={reset_token.token}&uid={user.id}"
    )
    subject = "Reset your password — RAKTCH"
    message = (
        f"Hello,\n\n"
        f"We received a request to reset your RAKTCH password.\n\n"
        f"Click the link below to choose a new password:\n"
        f"{reset_url}\n\n"
        f"This link expires in {getattr(settings, 'AUTH_PASSWORD_RESET_EXPIRY_MINUTES', 30)} minutes.\n\n"
        f"If you did not request a password reset, please ignore this email."
    )
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception as exc:
        logger.error(
            "Failed to send password reset email to %s: %s",
            user.email,
            exc,
            exc_info=True,
        )
