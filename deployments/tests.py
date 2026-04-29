"""Tests for deployments app."""
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from accounts.models import User, AccountStatus
from rbac.models import UserRole, Role
from people.models import EmployeeProfile
from projects.models import Project
from .models import Environment, Release, ReleaseStatus


def make_user(email, role=Role.PROJECT_MANAGER):
    user = User.objects.create_user(email=email, password='Pass123!', account_status=AccountStatus.ACTIVE)
    UserRole.objects.create(user=user, role=role, is_primary=True)
    return user

def make_profile(user): return EmployeeProfile.objects.create(user=user, full_name=user.email.split('@')[0], work_email=user.email)
def auth_client(user):
    c = APIClient(); refresh = RefreshToken.for_user(user)
    c.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}'); return c
def make_project(owner): return Project.objects.create(name='Project', owner=owner)


class EnvironmentTests(TestCase):
    def setUp(self):
        self.pm_user = make_user('pm@t.com')
        self.pm = make_profile(self.pm_user)
        self.staff_user = make_user('staff@t.com', Role.STAFF)
        self.project = make_project(self.pm)

    def test_pm_can_create_environment(self):
        client = auth_client(self.pm_user)
        resp = client.post('/api/v1/deployments/environments/', {'project': str(self.project.id), 'name': 'staging', 'type': 'staging'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_staff_cannot_create_environment(self):
        client = auth_client(self.staff_user)
        resp = client.post('/api/v1/deployments/environments/', {'project': str(self.project.id), 'name': 'prod', 'type': 'production'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_name_per_project_rejected(self):
        Environment.objects.create(project=self.project, name='staging', type='staging')
        client = auth_client(self.pm_user)
        resp = client.post('/api/v1/deployments/environments/', {'project': str(self.project.id), 'name': 'staging', 'type': 'staging'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class ReleaseTests(TestCase):
    def setUp(self):
        self.pm_user = make_user('pm@t.com')
        self.pm = make_profile(self.pm_user)
        self.project = make_project(self.pm)
        self.staff_user = make_user('staff@t.com', Role.STAFF)

    def test_pm_can_create_release(self):
        client = auth_client(self.pm_user)
        resp = client.post('/api/v1/deployments/releases/', {
            'project': str(self.project.id), 'version': '1.0.0', 'created_by': str(self.pm.id),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_staff_cannot_create_release(self):
        client = auth_client(self.staff_user)
        make_profile(self.staff_user)
        resp = client.post('/api/v1/deployments/releases/', {
            'project': str(self.project.id), 'version': '1.0.0', 'created_by': str(self.pm.id),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_version_per_project_rejected(self):
        Release.objects.create(project=self.project, version='2.0.0', created_by=self.pm)
        client = auth_client(self.pm_user)
        resp = client.post('/api/v1/deployments/releases/', {
            'project': str(self.project.id), 'version': '2.0.0', 'created_by': str(self.pm.id),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class DeploymentTests(TestCase):
    def setUp(self):
        self.pm_user = make_user('pm@t.com')
        self.pm = make_profile(self.pm_user)
        self.project = make_project(self.pm)
        self.env = Environment.objects.create(project=self.project, name='staging', type='staging')
        self.protected_env = Environment.objects.create(project=self.project, name='prod', type='production', is_protected=True)
        self.release = Release.objects.create(project=self.project, version='1.0.0', created_by=self.pm)

    def test_can_deploy_to_unprotected_env(self):
        client = auth_client(self.pm_user)
        resp = client.post('/api/v1/deployments/deployments/', {
            'release': str(self.release.id), 'environment': str(self.env.id), 'deployed_by': str(self.pm.id),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_protected_env_requires_approved_release(self):
        client = auth_client(self.pm_user)
        resp = client.post('/api/v1/deployments/deployments/', {
            'release': str(self.release.id), 'environment': str(self.protected_env.id), 'deployed_by': str(self.pm.id),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_mismatched_project_rejected(self):
        other_pm_user = make_user('other@t.com')
        other_pm = make_profile(other_pm_user)
        other_project = make_project(other_pm)
        other_env = Environment.objects.create(project=other_project, name='staging', type='staging')
        client = auth_client(self.pm_user)
        resp = client.post('/api/v1/deployments/deployments/', {
            'release': str(self.release.id), 'environment': str(other_env.id), 'deployed_by': str(self.pm.id),
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
