"""
Tests for org app: departments, teams, memberships, and permission enforcement.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User, AccountStatus
from rbac.models import UserRole, Role
from people.models import EmployeeProfile
from .models import Department, Team, TeamMembership


def make_user(email, role=Role.STAFF, password='Str0ngPass!'):
    user = User.objects.create_user(
        email=email,
        password=password,
        account_status=AccountStatus.ACTIVE,
    )
    UserRole.objects.create(user=user, role=role, is_primary=True)
    return user


def make_profile(user, full_name=None):
    return EmployeeProfile.objects.create(
        user=user,
        full_name=full_name or user.email.split('@')[0],
        work_email=user.email,
    )


def auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return client


class DepartmentTests(TestCase):
    def setUp(self):
        self.admin = make_user('admin@raktch.com', role=Role.ADMIN)
        self.staff = make_user('staff@raktch.com', role=Role.STAFF)

    def test_staff_can_list_departments(self):
        Department.objects.create(name='Engineering')
        client = auth_client(self.staff)
        resp = client.get('/api/v1/org/departments/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(resp.data['count'], 1)

    def test_admin_can_create_department(self):
        client = auth_client(self.admin)
        resp = client.post('/api/v1/org/departments/', {'name': 'Product'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Department.objects.filter(name='Product').exists())

    def test_staff_cannot_create_department(self):
        client = auth_client(self.staff)
        resp = client.post('/api/v1/org/departments/', {'name': 'Stealth'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_name_rejected(self):
        Department.objects.create(name='HR')
        client = auth_client(self.admin)
        resp = client.post('/api/v1/org/departments/', {'name': 'HR'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_can_patch_department(self):
        dept = Department.objects.create(name='Sales')
        client = auth_client(self.admin)
        resp = client.patch(f'/api/v1/org/departments/{dept.id}/', {'name': 'Sales & Marketing'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        dept.refresh_from_db()
        self.assertEqual(dept.name, 'Sales & Marketing')

    def test_admin_can_archive_department(self):
        dept = Department.objects.create(name='Archived Dept')
        client = auth_client(self.admin)
        resp = client.delete(f'/api/v1/org/departments/{dept.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        dept.refresh_from_db()
        self.assertTrue(dept.is_archived)

    def test_archived_departments_excluded_by_default(self):
        Department.objects.create(name='Visible Dept')
        hidden = Department.objects.create(name='Hidden Dept', is_archived=True)
        client = auth_client(self.staff)
        resp = client.get('/api/v1/org/departments/')
        names = [d['name'] for d in resp.data['results']]
        self.assertNotIn('Hidden Dept', names)

    def test_staff_cannot_archive_department(self):
        dept = Department.objects.create(name='Protected Dept')
        client = auth_client(self.staff)
        resp = client.delete(f'/api/v1/org/departments/{dept.id}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class TeamTests(TestCase):
    def setUp(self):
        self.admin = make_user('admin@raktch.com', role=Role.ADMIN)
        self.staff = make_user('staff@raktch.com', role=Role.STAFF)
        self.dept = Department.objects.create(name='Engineering')

    def test_admin_can_create_team(self):
        client = auth_client(self.admin)
        resp = client.post('/api/v1/org/teams/', {
            'name': 'Backend',
            'department': str(self.dept.id),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_staff_can_list_teams(self):
        Team.objects.create(name='Frontend', department=self.dept)
        client = auth_client(self.staff)
        resp = client.get('/api/v1/org/teams/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_staff_cannot_archive_team(self):
        team = Team.objects.create(name='DevOps', department=self.dept)
        client = auth_client(self.staff)
        resp = client.delete(f'/api/v1/org/teams/{team.id}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_archive_team(self):
        team = Team.objects.create(name='Legacy', department=self.dept)
        client = auth_client(self.admin)
        resp = client.delete(f'/api/v1/org/teams/{team.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        team.refresh_from_db()
        self.assertTrue(team.is_archived)


class TeamMembershipTests(TestCase):
    def setUp(self):
        self.admin = make_user('admin@raktch.com', role=Role.ADMIN)
        self.staff_user = make_user('staff@raktch.com', role=Role.STAFF)
        self.staff_profile = make_profile(self.staff_user, 'Staff User')
        self.dept = Department.objects.create(name='Engineering')
        self.team = Team.objects.create(name='Backend', department=self.dept)

    def test_admin_can_add_member(self):
        client = auth_client(self.admin)
        resp = client.post(f'/api/v1/org/teams/{self.team.id}/members/', {
            'employee': str(self.staff_profile.id),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(TeamMembership.objects.filter(team=self.team, employee=self.staff_profile).exists())

    def test_duplicate_membership_rejected(self):
        TeamMembership.objects.create(team=self.team, employee=self.staff_profile)
        client = auth_client(self.admin)
        resp = client.post(f'/api/v1/org/teams/{self.team.id}/members/', {
            'employee': str(self.staff_profile.id),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_staff_cannot_add_member(self):
        client = auth_client(self.staff_user)
        resp = client.post(f'/api/v1/org/teams/{self.team.id}/members/', {
            'employee': str(self.staff_profile.id),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_remove_member(self):
        membership = TeamMembership.objects.create(team=self.team, employee=self.staff_profile)
        client = auth_client(self.admin)
        resp = client.delete(f'/api/v1/org/teams/{self.team.id}/members/{membership.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(TeamMembership.objects.filter(pk=membership.id).exists())

    def test_cannot_add_to_archived_team(self):
        self.team.is_archived = True
        self.team.save()
        client = auth_client(self.admin)
        resp = client.post(f'/api/v1/org/teams/{self.team.id}/members/', {
            'employee': str(self.staff_profile.id),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
