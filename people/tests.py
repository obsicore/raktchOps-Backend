"""
Tests for people app: employee directory, detail, and permission enforcement.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User, AccountStatus
from rbac.models import UserRole, Role
from .models import EmployeeProfile


def make_user(email, role=Role.STAFF, account_status=AccountStatus.ACTIVE, password='Str0ngPass!'):
    user = User.objects.create_user(
        email=email,
        password=password,
        account_status=account_status,
    )
    UserRole.objects.create(user=user, role=role, is_primary=True)
    return user


def make_profile(user, full_name=None, work_email=None):
    return EmployeeProfile.objects.create(
        user=user,
        full_name=full_name or user.email.split('@')[0],
        work_email=work_email or user.email,
    )


def auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return client


class EmployeeListTests(TestCase):
    def setUp(self):
        self.admin = make_user('admin@raktch.com', role=Role.ADMIN)
        self.staff = make_user('staff@raktch.com', role=Role.STAFF)
        self.admin_profile = make_profile(self.admin, 'Admin User', 'admin@raktch.com')
        self.staff_profile = make_profile(self.staff, 'Staff User', 'staff@raktch.com')

    def test_any_active_user_can_list(self):
        client = auth_client(self.staff)
        resp = client.get('/api/v1/people/employees/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('results', resp.data)

    def test_results_default_to_active_employees(self):
        inactive_user = make_user('inactive@raktch.com')
        inactive_profile = make_profile(inactive_user, 'Inactive User', 'inactive@raktch.com')
        inactive_profile.employment_status = 'inactive'
        inactive_profile.save()

        client = auth_client(self.staff)
        resp = client.get('/api/v1/people/employees/')
        emails = [e['work_email'] for e in resp.data['results']]
        self.assertNotIn('inactive@raktch.com', emails)

    def test_search_by_name(self):
        client = auth_client(self.staff)
        resp = client.get('/api/v1/people/employees/', {'search': 'Admin'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(any('Admin' in e['full_name'] for e in resp.data['results']))

    def test_unauthenticated_blocked(self):
        client = APIClient()
        resp = client.get('/api/v1/people/employees/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class EmployeeCreateTests(TestCase):
    def setUp(self):
        self.admin = make_user('admin@raktch.com', role=Role.ADMIN)
        self.staff = make_user('staff@raktch.com', role=Role.STAFF)

    def test_admin_can_create_profile(self):
        target = make_user('new@raktch.com')
        client = auth_client(self.admin)
        resp = client.post('/api/v1/people/employees/', {
            'user': str(target.id),
            'full_name': 'New Employee',
            'work_email': 'new@raktch.com',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(EmployeeProfile.objects.filter(user=target).exists())

    def test_staff_cannot_create_profile(self):
        target = make_user('target@raktch.com')
        client = auth_client(self.staff)
        resp = client.post('/api/v1/people/employees/', {
            'user': str(target.id),
            'full_name': 'Target',
            'work_email': 'target@raktch.com',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_create_profile_for_inactive_user(self):
        inactive = make_user('inactive@raktch.com', account_status=AccountStatus.PENDING_VERIFICATION)
        client = auth_client(self.admin)
        resp = client.post('/api/v1/people/employees/', {
            'user': str(inactive.id),
            'full_name': 'Inactive',
            'work_email': 'inactive@raktch.com',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_work_email_rejected(self):
        existing = make_user('existing@raktch.com')
        make_profile(existing, 'Existing', 'existing@raktch.com')
        another = make_user('another@raktch.com')
        client = auth_client(self.admin)
        resp = client.post('/api/v1/people/employees/', {
            'user': str(another.id),
            'full_name': 'Another',
            'work_email': 'existing@raktch.com',  # duplicate
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class EmployeeDetailTests(TestCase):
    def setUp(self):
        self.admin = make_user('admin@raktch.com', role=Role.ADMIN)
        self.staff = make_user('staff@raktch.com', role=Role.STAFF)
        self.staff_profile = make_profile(self.staff, 'Staff User', 'staff@raktch.com')

    def test_any_user_can_get_detail(self):
        client = auth_client(self.admin)
        resp = client.get(f'/api/v1/people/employees/{self.staff_profile.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['work_email'], 'staff@raktch.com')

    def test_staff_can_patch_own_allowed_fields(self):
        client = auth_client(self.staff)
        resp = client.patch(
            f'/api/v1/people/employees/{self.staff_profile.id}/',
            {'full_name': 'Updated Name', 'job_title': 'Dev'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.staff_profile.refresh_from_db()
        self.assertEqual(self.staff_profile.full_name, 'Updated Name')

    def test_staff_cannot_patch_restricted_fields(self):
        client = auth_client(self.staff)
        resp = client.patch(
            f'/api/v1/people/employees/{self.staff_profile.id}/',
            {'employment_status': 'inactive'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_cannot_patch_other_profile(self):
        other = make_user('other@raktch.com')
        other_profile = make_profile(other, 'Other', 'other@raktch.com')
        client = auth_client(self.staff)
        resp = client.patch(
            f'/api/v1/people/employees/{other_profile.id}/',
            {'full_name': 'Hacked'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_patch_any_profile(self):
        client = auth_client(self.admin)
        resp = client.patch(
            f'/api/v1/people/employees/{self.staff_profile.id}/',
            {'employment_status': 'inactive'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_404_for_nonexistent_profile(self):
        import uuid
        client = auth_client(self.staff)
        resp = client.get(f'/api/v1/people/employees/{uuid.uuid4()}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_my_profile_endpoint(self):
        client = auth_client(self.staff)
        resp = client.get('/api/v1/people/me/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['work_email'], 'staff@raktch.com')

    def test_my_profile_no_profile_returns_404(self):
        no_profile_user = make_user('noprofile@raktch.com')
        client = auth_client(no_profile_user)
        resp = client.get('/api/v1/people/me/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
