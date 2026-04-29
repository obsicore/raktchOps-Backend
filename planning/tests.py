"""Tests for planning app: Sprint and Milestone."""
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from accounts.models import User, AccountStatus
from rbac.models import UserRole, Role
from people.models import EmployeeProfile
from projects.models import Project
from .models import Sprint


def make_user(email, role=Role.PROJECT_MANAGER):
    user = User.objects.create_user(email=email, password='Pass123!', account_status=AccountStatus.ACTIVE)
    UserRole.objects.create(user=user, role=role, is_primary=True)
    return user

def make_profile(user): return EmployeeProfile.objects.create(user=user, full_name=user.email.split('@')[0], work_email=user.email)
def auth_client(user):
    c = APIClient(); refresh = RefreshToken.for_user(user)
    c.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}'); return c
def make_project(owner): return Project.objects.create(name='Project', owner=owner)


class SprintTests(TestCase):
    def setUp(self):
        self.pm_user = make_user('pm@t.com')
        self.pm = make_profile(self.pm_user)
        self.staff_user = make_user('staff@t.com', Role.STAFF)
        self.project = make_project(self.pm)

    def test_pm_can_create_sprint(self):
        client = auth_client(self.pm_user)
        resp = client.post('/api/v1/planning/sprints/', {
            'project': str(self.project.id), 'name': 'Sprint 1',
            'start_date': '2026-05-01', 'end_date': '2026-05-14',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_staff_cannot_create_sprint(self):
        client = auth_client(self.staff_user)
        resp = client.post('/api/v1/planning/sprints/', {
            'project': str(self.project.id), 'name': 'S', 'start_date': '2026-05-01', 'end_date': '2026-05-14',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_end_before_start_rejected(self):
        client = auth_client(self.pm_user)
        resp = client.post('/api/v1/planning/sprints/', {
            'project': str(self.project.id), 'name': 'Bad Sprint',
            'start_date': '2026-05-14', 'end_date': '2026-05-01',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_only_one_active_sprint_per_project(self):
        client = auth_client(self.pm_user)
        client.post('/api/v1/planning/sprints/', {
            'project': str(self.project.id), 'name': 'S1', 'status': 'active',
            'start_date': '2026-05-01', 'end_date': '2026-05-14',
        }, format='json')
        resp = client.post('/api/v1/planning/sprints/', {
            'project': str(self.project.id), 'name': 'S2', 'status': 'active',
            'start_date': '2026-05-15', 'end_date': '2026-05-28',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class MilestoneTests(TestCase):
    def setUp(self):
        self.pm_user = make_user('pm@t.com')
        self.pm = make_profile(self.pm_user)
        self.staff_user = make_user('staff@t.com', Role.STAFF)
        self.project = make_project(self.pm)

    def test_pm_can_create_milestone(self):
        client = auth_client(self.pm_user)
        resp = client.post('/api/v1/planning/milestones/', {
            'project': str(self.project.id), 'name': 'MVP', 'target_date': '2026-06-01',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_staff_cannot_create_milestone(self):
        client = auth_client(self.staff_user)
        resp = client.post('/api/v1/planning/milestones/', {
            'project': str(self.project.id), 'name': 'Hack', 'target_date': '2026-06-01',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_blank_name_rejected(self):
        client = auth_client(self.pm_user)
        resp = client.post('/api/v1/planning/milestones/', {
            'project': str(self.project.id), 'name': '   ', 'target_date': '2026-06-01',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
