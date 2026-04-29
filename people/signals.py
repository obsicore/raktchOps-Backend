"""
Auto-create an EmployeeProfile for superusers (and any user created with
account_status='active' who doesn't already have one).
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_employee_profile(sender, instance, created, **kwargs):
    """
    If a user is a superuser or has account_status='active', make sure they
    have an EmployeeProfile. This handles the Django createsuperuser flow and
    any direct DB user creation.
    """
    from people.models import EmployeeProfile

    needs_profile = getattr(instance, 'is_superuser', False) or getattr(instance, 'account_status', None) == 'active'
    if not needs_profile:
        return

    try:
        # Already has one — nothing to do.
        _ = instance.employee_profile
    except EmployeeProfile.DoesNotExist:
        EmployeeProfile.objects.create(
            user=instance,
            full_name=instance.email.split('@')[0],
            work_email=instance.email,
        )
    except Exception:
        pass
