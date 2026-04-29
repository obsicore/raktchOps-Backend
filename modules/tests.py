"""Tests for modules app."""

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from accounts.models import User, AccountStatus
from rbac.models import UserRole, Role
from people.models import EmployeeProfile
from projects.models import Project, ProjectMember
from modules.models import Module
from notifications.models import Notification


def _make_user(email, role=Role.STAFF, password='Pass1!word', account_status=AccountStatus.ACTIVE):
    user = User.objects.create_user(email=email, password=password, account_status=account_status)
    UserRole.objects.create(user=user, role=role, is_primary=True)
    profile, _ = EmployeeProfile.objects.get_or_create(user=user, defaults={'full_name': email.split('@')[0], 'work_email': email})
    return user, profile


def _auth(client, user, password='Pass1!word'):
    resp = client.post('/api/v1/auth/login/', {'email': user.email, 'password': password}, format='json')
    token = resp.data.get('access')
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')


class ModuleTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin, self.admin_profile = _make_user('admin@raktch.com', Role.ADMIN)
        self.staff, self.staff_profile = _make_user('staff@raktch.com', Role.STAFF)

        self.project = Project.objects.create(
            name='Test Project',
            owner=self.admin_profile,
            status='active',
        )
        ProjectMember.objects.create(project=self.project, employee=self.staff_profile)
        _auth(self.client, self.admin)

    def test_list_modules_empty(self):
        resp = self.client.get(f'/api/v1/projects/{self.project.pk}/modules/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 0)

    def test_create_module(self):
        resp = self.client.post(f'/api/v1/projects/{self.project.pk}/modules/', {
            'name': 'Module One',
            'description': 'Test module',
            'status': 'todo',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Module.objects.filter(project=self.project).count(), 1)

    def test_module_progress_zero_tasks(self):
        resp = self.client.post(f'/api/v1/projects/{self.project.pk}/modules/', {
            'name': 'No Tasks Module',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['progress'], 0)

    def test_duplicate_module_name_rejected(self):
        Module.objects.create(project=self.project, name='Duplicate', created_by=self.admin)
        resp = self.client.post(f'/api/v1/projects/{self.project.pk}/modules/', {
            'name': 'Duplicate',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_staff_cannot_create_module(self):
        staff_client = APIClient()
        _auth(staff_client, self.staff)
        resp = staff_client.post(f'/api/v1/projects/{self.project.pk}/modules/', {
            'name': 'Staff Module',
        }, format='json')
        self.assertEqual(resp.status_code, 403)

    def test_staff_can_read_modules(self):
        Module.objects.create(project=self.project, name='Readable Module', created_by=self.admin)
        staff_client = APIClient()
        _auth(staff_client, self.staff)
        resp = staff_client.get(f'/api/v1/projects/{self.project.pk}/modules/')
        self.assertEqual(resp.status_code, 200)

    def test_delete_module(self):
        module = Module.objects.create(project=self.project, name='To Delete', created_by=self.admin)
        resp = self.client.delete(f'/api/v1/projects/{self.project.pk}/modules/{module.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Module.objects.filter(pk=module.pk).exists())

    def test_update_module(self):
        module = Module.objects.create(project=self.project, name='Old Name', created_by=self.admin)
        resp = self.client.patch(f'/api/v1/projects/{self.project.pk}/modules/{module.pk}/', {
            'name': 'New Name',
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        module.refresh_from_db()
        self.assertEqual(module.name, 'New Name')

    def test_module_crud_emits_notifications(self):
        create_resp = self.client.post(f'/api/v1/projects/{self.project.pk}/modules/', {
            'name': 'Notify Module',
            'description': 'Notify',
        }, format='json')
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        module_id = create_resp.data['id']

        patch_resp = self.client.patch(f'/api/v1/projects/{self.project.pk}/modules/{module_id}/', {
            'status': 'in_progress',
        }, format='json')
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)

        delete_resp = self.client.delete(f'/api/v1/projects/{self.project.pk}/modules/{module_id}/')
        self.assertEqual(delete_resp.status_code, status.HTTP_200_OK)

        self.assertTrue(Notification.objects.filter(title__icontains='Module created').exists())
        self.assertTrue(Notification.objects.filter(title__icontains='Module status changed').exists())
        self.assertTrue(Notification.objects.filter(title__icontains='Module deleted').exists())
