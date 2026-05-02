"""
Tests for accounts app: AllowedDomain, signup, user management, password change.
"""

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from accounts.models import User, AccountStatus, AllowedDomain
from rbac.models import UserRole, Role
from notifications.models import Notification


def _make_admin(email='admin@raktch.com', password='AdminPass1!'):
    user = User.objects.create_user(
        email=email,
        password=password,
        account_status=AccountStatus.ACTIVE,
    )
    UserRole.objects.create(user=user, role=Role.ADMIN, is_primary=True)
    return user


def _make_staff(email='staff@raktch.com', password='StaffPass1!'):
    user = User.objects.create_user(
        email=email,
        password=password,
        account_status=AccountStatus.ACTIVE,
    )
    UserRole.objects.create(user=user, role=Role.STAFF, is_primary=True)
    return user


def _make_super_admin(email='superadmin@raktch.com', password='SuperPass1!'):
    user = User.objects.create_user(
        email=email,
        password=password,
        account_status=AccountStatus.ACTIVE,
    )
    UserRole.objects.create(user=user, role=Role.SUPER_ADMIN, is_primary=True)
    return user


def _auth(client, user, password=None):
    if password is None:
        password = 'AdminPass1!' if 'admin' in user.email else 'StaffPass1!'
    resp = client.post('/api/v1/auth/login/', {'email': user.email, 'password': password}, format='json')
    token = resp.data.get('access')
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')


class AllowedDomainTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = _make_admin()
        _auth(self.client, self.admin)
        AllowedDomain.objects.create(domain='raktch.com', is_active=True, created_by=self.admin)

    def test_list_allowed_domains(self):
        resp = self.client.get('/api/v1/auth/allowed-domains/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('results', resp.data)
        self.assertEqual(resp.data['count'], 1)

    def test_create_allowed_domain(self):
        resp = self.client.post('/api/v1/auth/allowed-domains/', {'domain': 'example.com'}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(AllowedDomain.objects.filter(domain='example.com').count(), 1)

    def test_create_invalid_domain(self):
        resp = self.client.post('/api/v1/auth/allowed-domains/', {'domain': 'not-a-domain'}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_delete_domain(self):
        domain = AllowedDomain.objects.create(domain='todelete.com')
        resp = self.client.delete(f'/api/v1/auth/allowed-domains/{domain.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(AllowedDomain.objects.filter(domain='todelete.com').exists())

    def test_staff_cannot_manage_domains(self):
        staff = _make_staff()
        staff_client = APIClient()
        _auth(staff_client, staff)
        resp = staff_client.get('/api/v1/auth/allowed-domains/')
        self.assertEqual(resp.status_code, 403)

    def test_deactivate_domain(self):
        domain = AllowedDomain.objects.create(domain='inactive.com', is_active=True)
        resp = self.client.patch(f'/api/v1/auth/allowed-domains/{domain.pk}/', {'is_active': False}, format='json')
        self.assertEqual(resp.status_code, 200)
        domain.refresh_from_db()
        self.assertFalse(domain.is_active)


class SignupTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = _make_admin()
        self.super_admin = User.objects.create_user(
            email='superadmin@raktch.com',
            password='SuperPass1!',
            account_status=AccountStatus.ACTIVE,
        )
        UserRole.objects.create(user=self.super_admin, role=Role.SUPER_ADMIN, is_primary=True)
        AllowedDomain.objects.create(domain='raktch.com', is_active=True, created_by=self.admin)

    def test_signup_allowed_domain(self):
        resp = self.client.post('/api/v1/auth/signup/', {
            'email': 'newuser@raktch.com',
            'password': 'NewPass1!Strong',
            'confirm_password': 'NewPass1!Strong',
            'first_name': 'New',
            'last_name': 'User',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        user = User.objects.get(email='newuser@raktch.com')
        self.assertEqual(user.account_status, AccountStatus.PENDING_APPROVAL)
        from rbac.models import get_user_role
        self.assertEqual(get_user_role(user), 'staff')

    def test_signup_disallowed_domain(self):
        resp = self.client.post('/api/v1/auth/signup/', {
            'email': 'newuser@notallowed.com',
            'password': 'NewPass1!Strong',
            'confirm_password': 'NewPass1!Strong',
            'first_name': 'New',
            'last_name': 'User',
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('notallowed.com', str(resp.data))

    def test_signup_duplicate_email(self):
        _make_staff('existing@raktch.com')
        resp = self.client.post('/api/v1/auth/signup/', {
            'email': 'existing@raktch.com',
            'password': 'NewPass1!Strong',
            'confirm_password': 'NewPass1!Strong',
            'first_name': 'New',
            'last_name': 'User',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_signup_password_mismatch(self):
        resp = self.client.post('/api/v1/auth/signup/', {
            'email': 'newuser@raktch.com',
            'password': 'NewPass1!Strong',
            'confirm_password': 'DifferentPass1!',
            'first_name': 'New',
            'last_name': 'User',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_signup_inactive_domain_blocked(self):
        AllowedDomain.objects.filter(domain='raktch.com').update(is_active=False)
        resp = self.client.post('/api/v1/auth/signup/', {
            'email': 'newuser@raktch.com',
            'password': 'NewPass1!Strong',
            'confirm_password': 'NewPass1!Strong',
            'first_name': 'New',
            'last_name': 'User',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_signup_pending_approval_notifies_admin_and_super_admin(self):
        resp = self.client.post('/api/v1/auth/signup/', {
            'email': 'notifyme@raktch.com',
            'password': 'NewPass1!Strong',
            'confirm_password': 'NewPass1!Strong',
            'first_name': 'Notify',
            'last_name': 'Me',
        }, format='json')
        self.assertEqual(resp.status_code, 201)

        self.assertTrue(
            Notification.objects.filter(
                recipient=self.admin,
                title__icontains='pending approval',
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.super_admin,
                title__icontains='pending approval',
            ).exists()
        )


class UserManagementTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = _make_admin()
        self.super_admin = _make_super_admin()
        _auth(self.client, self.admin)

    def test_list_users(self):
        resp = self.client.get('/api/v1/auth/users/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('results', resp.data)

    def test_approve_user(self):
        user = _make_staff('pending@raktch.com')
        user.account_status = AccountStatus.PENDING_APPROVAL
        user.save()
        resp = self.client.post(f'/api/v1/auth/users/{user.pk}/approve/')
        self.assertEqual(resp.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.account_status, AccountStatus.ACTIVE)

    def test_deactivate_user(self):
        user = _make_staff('todeactivate@raktch.com')
        resp = self.client.post(f'/api/v1/auth/users/{user.pk}/deactivate/')
        self.assertEqual(resp.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.account_status, AccountStatus.DISABLED)

    def test_cannot_deactivate_self(self):
        resp = self.client.post(f'/api/v1/auth/users/{self.admin.pk}/deactivate/')
        self.assertEqual(resp.status_code, 400)

    def test_change_role(self):
        user = _make_staff('rolechange@raktch.com')
        resp = self.client.post(f'/api/v1/auth/users/{user.pk}/change-role/', {'role': 'project_manager'}, format='json')
        self.assertEqual(resp.status_code, 200)
        from rbac.models import get_user_role
        self.assertEqual(get_user_role(user), 'project_manager')

    def test_email_is_readonly_on_update(self):
        user = _make_staff('emailtest@raktch.com')
        resp = self.client.patch(f'/api/v1/auth/users/{user.pk}/', {'email': 'changed@raktch.com', 'account_status': 'active'}, format='json')
        self.assertEqual(resp.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.email, 'emailtest@raktch.com')

    def test_staff_cannot_manage_users(self):
        staff = _make_staff()
        staff_client = APIClient()
        _auth(staff_client, staff)
        resp = staff_client.get('/api/v1/auth/users/')
        self.assertEqual(resp.status_code, 403)

    def test_admin_cannot_create_super_admin_user(self):
        resp = self.client.post('/api/v1/auth/users/', {
            'email': 'new-super@raktch.com',
            'password': 'StrongPass1!',
            'first_name': 'New',
            'last_name': 'Super',
            'role': 'super_admin',
        }, format='json')
        self.assertEqual(resp.status_code, 403)

    def test_admin_cannot_promote_user_to_super_admin(self):
        user = _make_staff('promote@raktch.com')
        resp = self.client.post(f'/api/v1/auth/users/{user.pk}/change-role/', {'role': 'super_admin'}, format='json')
        self.assertEqual(resp.status_code, 403)

    def test_super_admin_can_create_super_admin_user(self):
        sa_client = APIClient()
        _auth(sa_client, self.super_admin, 'SuperPass1!')
        resp = sa_client.post('/api/v1/auth/users/', {
            'email': 'createdbysa@raktch.com',
            'password': 'StrongPass1!',
            'first_name': 'Created',
            'last_name': 'BySa',
            'role': 'super_admin',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        created = User.objects.get(email='createdbysa@raktch.com')
        from rbac.models import get_user_role
        self.assertEqual(get_user_role(created), 'super_admin')

    def test_super_admin_can_promote_user_to_super_admin(self):
        user = _make_staff('promotebysa@raktch.com')
        sa_client = APIClient()
        _auth(sa_client, self.super_admin, 'SuperPass1!')
        resp = sa_client.post(f'/api/v1/auth/users/{user.pk}/change-role/', {'role': 'super_admin'}, format='json')
        self.assertEqual(resp.status_code, 200)
        from rbac.models import get_user_role
        self.assertEqual(get_user_role(user), 'super_admin')

    def test_admin_cannot_invite_super_admin(self):
        resp = self.client.post('/api/v1/auth/admin/invite/', {
            'email': 'invite-super@raktch.com',
            'role': 'super_admin',
        }, format='json')
        self.assertEqual(resp.status_code, 403)

    def test_super_admin_can_invite_super_admin(self):
        sa_client = APIClient()
        _auth(sa_client, self.super_admin, 'SuperPass1!')
        resp = sa_client.post('/api/v1/auth/admin/invite/', {
            'email': 'invite-super2@raktch.com',
            'role': 'super_admin',
        }, format='json')
        self.assertEqual(resp.status_code, 201)


class ChangePasswordTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.staff = _make_staff()
        _auth(self.client, self.staff)

    def test_change_password_success(self):
        resp = self.client.post('/api/v1/auth/change-password/', {
            'current_password': 'StaffPass1!',
            'new_password': 'NewStaffPass1!',
            'confirm_password': 'NewStaffPass1!',
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.check_password('NewStaffPass1!'))

    def test_wrong_current_password(self):
        resp = self.client.post('/api/v1/auth/change-password/', {
            'current_password': 'WrongPassword',
            'new_password': 'NewStaffPass1!',
            'confirm_password': 'NewStaffPass1!',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_password_mismatch(self):
        resp = self.client.post('/api/v1/auth/change-password/', {
            'current_password': 'StaffPass1!',
            'new_password': 'NewStaffPass1!',
            'confirm_password': 'DifferentPass1!',
        }, format='json')
        self.assertEqual(resp.status_code, 400)
