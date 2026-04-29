"""
Tests for the projects app: CRUD, permissions, repository URL validation,
member management, and the GitHub-URL-only enforcement.
"""

from datetime import date
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User, AccountStatus
from rbac.models import UserRole, Role
from people.models import EmployeeProfile
from .models import Project, ProjectMember
from notifications.models import Notification


def make_user(email, role=Role.STAFF, password='Str0ngPass!'):
    user = User.objects.create_user(
        email=email, password=password, account_status=AccountStatus.ACTIVE
    )
    UserRole.objects.create(user=user, role=role, is_primary=True)
    return user


def make_profile(user, full_name=None):
    profile, _ = EmployeeProfile.objects.get_or_create(
        user=user,
        defaults={
            'full_name': full_name or user.email.split('@')[0],
            'work_email': user.email,
        },
    )
    if full_name and profile.full_name != full_name:
        profile.full_name = full_name
        profile.save(update_fields=['full_name'])
    return profile


def make_project(owner, name='Test Project', status='active'):
    return Project.objects.create(
        name=name,
        owner=owner,
        status=status,
    )


def auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return client


class ProjectCreateTests(TestCase):
    def setUp(self):
        self.admin_user = make_user('admin@raktch.com', role=Role.ADMIN)
        self.admin = make_profile(self.admin_user, 'Admin')
        self.pm_user = make_user('pm@raktch.com', role=Role.PROJECT_MANAGER)
        self.pm = make_profile(self.pm_user, 'PM')
        self.staff_user = make_user('staff@raktch.com', role=Role.STAFF)
        self.staff = make_profile(self.staff_user, 'Staff')

    def test_admin_can_create_project(self):
        client = auth_client(self.admin_user)
        resp = client.post('/api/v1/projects/', {
            'name': 'Alpha',
            'owner': str(self.admin.id),
            'type': 'internal',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['name'], 'Alpha')

    def test_pm_can_create_project(self):
        client = auth_client(self.pm_user)
        resp = client.post('/api/v1/projects/', {
            'name': 'Beta',
            'owner': str(self.pm.id),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_staff_cannot_create_project(self):
        client = auth_client(self.staff_user)
        resp = client.post('/api/v1/projects/', {
            'name': 'Stealth',
            'owner': str(self.staff.id),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_due_date_before_start_date_rejected(self):
        client = auth_client(self.admin_user)
        resp = client.post('/api/v1/projects/', {
            'name': 'Bad Dates',
            'owner': str(self.admin.id),
            'start_date': '2026-06-01',
            'due_date': '2026-01-01',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class RepositoryUrlValidationTests(TestCase):
    def setUp(self):
        self.admin_user = make_user('admin@raktch.com', role=Role.ADMIN)
        self.admin = make_profile(self.admin_user, 'Admin')

    def test_valid_github_url_accepted(self):
        client = auth_client(self.admin_user)
        resp = client.post('/api/v1/projects/', {
            'name': 'Repo Project',
            'owner': str(self.admin.id),
            'repository_url': 'https://github.com/raktch/api',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['repository_url'], 'https://github.com/raktch/api')

    def test_non_github_url_rejected(self):
        client = auth_client(self.admin_user)
        resp = client.post('/api/v1/projects/', {
            'name': 'Bad Repo',
            'owner': str(self.admin.id),
            'repository_url': 'https://gitlab.com/raktch/api',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_http_url_rejected(self):
        client = auth_client(self.admin_user)
        resp = client.post('/api/v1/projects/', {
            'name': 'HTTP Repo',
            'owner': str(self.admin.id),
            'repository_url': 'http://github.com/raktch/api',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_repo_url_accepted(self):
        client = auth_client(self.admin_user)
        resp = client.post('/api/v1/projects/', {
            'name': 'No Repo',
            'owner': str(self.admin.id),
            'repository_url': '',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


class ProjectVisibilityTests(TestCase):
    def setUp(self):
        self.admin_user = make_user('admin@raktch.com', role=Role.ADMIN)
        self.admin = make_profile(self.admin_user, 'Admin')
        self.super_admin_user = make_user('superadmin@raktch.com', role=Role.SUPER_ADMIN)
        self.super_admin = make_profile(self.super_admin_user, 'Super Admin')
        self.staff_user = make_user('staff@raktch.com', role=Role.STAFF)
        self.staff = make_profile(self.staff_user, 'Staff')
        self.project = make_project(self.admin, 'Visible Project')
        self.private = make_project(self.admin, 'Private Project')

    def test_admin_sees_all_projects(self):
        client = auth_client(self.admin_user)
        resp = client.get('/api/v1/projects/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 2)

    def test_staff_can_view_all_projects(self):
        client = auth_client(self.staff_user)
        resp = client.get('/api/v1/projects/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 2)

    def test_staff_can_view_non_member_project_detail(self):
        client = auth_client(self.staff_user)
        resp = client.get(f'/api/v1/projects/{self.private.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_project_owner_can_edit(self):
        # Make staff the owner
        self.private.owner = self.staff
        self.private.save()
        client = auth_client(self.staff_user)
        resp = client.patch(f'/api/v1/projects/{self.private.id}/', {
            'name': 'Updated Name'
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_status_filter(self):
        make_project(self.admin, 'Completed', status='completed')
        client = auth_client(self.admin_user)
        resp = client.get('/api/v1/projects/', {'status': 'completed'})
        self.assertEqual(resp.data['count'], 1)
        self.assertEqual(resp.data['results'][0]['name'], 'Completed')

    def test_search_by_name(self):
        client = auth_client(self.admin_user)
        resp = client.get('/api/v1/projects/', {'search': 'Visible'})
        self.assertEqual(resp.data['count'], 1)

    def test_project_completion_notifies_admin_and_super_admin(self):
        client = auth_client(self.admin_user)
        resp = client.patch(f'/api/v1/projects/{self.project.id}/', {
            'status': 'completed',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertTrue(
            Notification.objects.filter(
                recipient=self.admin_user,
                title__icontains='Project completed',
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.super_admin_user,
                title__icontains='Project completed',
            ).exists()
        )


class ProjectArchiveTests(TestCase):
    def setUp(self):
        self.admin_user = make_user('admin@raktch.com', role=Role.ADMIN)
        self.admin = make_profile(self.admin_user, 'Admin')
        self.pm_user = make_user('pm@raktch.com', role=Role.PROJECT_MANAGER)
        self.pm = make_profile(self.pm_user, 'PM')
        self.project = make_project(self.admin, 'To Archive')

    def test_admin_can_archive(self):
        client = auth_client(self.admin_user)
        resp = client.delete(f'/api/v1/projects/{self.project.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, 'archived')

    def test_pm_cannot_archive(self):
        client = auth_client(self.pm_user)
        resp = client.delete(f'/api/v1/projects/{self.project.id}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class ProjectMemberTests(TestCase):
    def setUp(self):
        self.admin_user = make_user('admin@raktch.com', role=Role.ADMIN)
        self.admin = make_profile(self.admin_user, 'Admin')
        self.super_admin_user = make_user('superadmin@raktch.com', role=Role.SUPER_ADMIN)
        self.super_admin = make_profile(self.super_admin_user, 'Super Admin')
        self.staff_user = make_user('staff@raktch.com', role=Role.STAFF)
        self.staff = make_profile(self.staff_user, 'Staff')
        self.project = make_project(self.admin, 'Members Project')

    def test_admin_can_add_member(self):
        client = auth_client(self.admin_user)
        resp = client.post(f'/api/v1/projects/{self.project.id}/members/', {
            'employee': str(self.staff.id),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_project_lead_can_add_member(self):
        self.project.owner = self.staff
        self.project.save(update_fields=['owner'])
        candidate_user = make_user('candidate@raktch.com', role=Role.STAFF)
        candidate = make_profile(candidate_user, 'Candidate')

        client = auth_client(self.staff_user)
        resp = client.post(f'/api/v1/projects/{self.project.id}/members/', {
            'employee': str(candidate.id),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_add_member_triggers_member_and_super_admin_notifications(self):
        client = auth_client(self.admin_user)
        resp = client.post(f'/api/v1/projects/{self.project.id}/members/', {
            'employee': str(self.staff.id),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        self.assertTrue(
            Notification.objects.filter(
                recipient=self.staff_user,
                title__icontains='Added to project',
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.super_admin_user,
                title__icontains='Added to project',
            ).exists()
        )

    def test_duplicate_member_rejected(self):
        ProjectMember.objects.create(project=self.project, employee=self.staff)
        client = auth_client(self.admin_user)
        resp = client.post(f'/api/v1/projects/{self.project.id}/members/', {
            'employee': str(self.staff.id),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_can_remove_member(self):
        membership = ProjectMember.objects.create(project=self.project, employee=self.staff)
        client = auth_client(self.admin_user)
        resp = client.delete(f'/api/v1/projects/{self.project.id}/members/{membership.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(ProjectMember.objects.filter(pk=membership.id).exists())

    def test_staff_cannot_add_member(self):
        client = auth_client(self.staff_user)
        other = make_user('other@raktch.com')
        other_profile = make_profile(other, 'Other')
        resp = client.post(f'/api/v1/projects/{self.project.id}/members/', {
            'employee': str(other_profile.id),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
