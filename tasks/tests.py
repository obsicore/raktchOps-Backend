"""Tests for tasks app: CRUD, assignment validation, kanban move."""

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User, AccountStatus
from rbac.models import UserRole, Role
from people.models import EmployeeProfile
from projects.models import Project, ProjectMember
from modules.models import Module
from tasks.models import Task
from notifications.models import Notification


def _make_user(email, role=Role.STAFF, password='Pass1!word'):
    user = User.objects.create_user(email=email, password=password, account_status=AccountStatus.ACTIVE)
    UserRole.objects.create(user=user, role=role, is_primary=True)
    profile, _ = EmployeeProfile.objects.get_or_create(
        user=user, defaults={'full_name': email.split('@')[0], 'work_email': email}
    )
    return user, profile


def _auth(client, user, password='Pass1!word'):
    resp = client.post('/api/v1/auth/login/', {'email': user.email, 'password': password}, format='json')
    token = resp.data.get('access')
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')


class TaskTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin, self.admin_profile = _make_user('admin@raktch.com', Role.ADMIN)
        self.super_admin, self.super_admin_profile = _make_user('superadmin@raktch.com', Role.SUPER_ADMIN)
        self.member, self.member_profile = _make_user('member@raktch.com', Role.STAFF)
        self.outsider, self.outsider_profile = _make_user('outsider@raktch.com', Role.STAFF)

        self.project = Project.objects.create(name='Project', owner=self.admin_profile, status='active')
        ProjectMember.objects.create(project=self.project, employee=self.member_profile)

        self.module = Module.objects.create(
            project=self.project, name='Module', created_by=self.admin
        )
        _auth(self.client, self.admin)

    def test_list_tasks_empty(self):
        resp = self.client.get(f'/api/v1/modules/{self.module.pk}/tasks/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 0)

    def test_create_task(self):
        resp = self.client.post(f'/api/v1/modules/{self.module.pk}/tasks/', {
            'title': 'Test Task',
            'status': 'todo',
            'priority': 'medium',
        }, format='json')
        self.assertEqual(resp.status_code, 201)

    def test_assignee_must_be_project_member(self):
        resp = self.client.post(f'/api/v1/modules/{self.module.pk}/tasks/', {
            'title': 'Task with outsider',
            'assignee': str(self.outsider.pk),
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_assignee_valid_member(self):
        resp = self.client.post(f'/api/v1/modules/{self.module.pk}/tasks/', {
            'title': 'Task with member',
            'assignee': str(self.member.pk),
        }, format='json')
        self.assertEqual(resp.status_code, 201)

    def test_assignee_can_move_own_task(self):
        task = Task.objects.create(
            module=self.module, title='Assignee Task',
            assignee=self.member, created_by=self.admin
        )
        member_client = APIClient()
        _auth(member_client, self.member)
        resp = member_client.patch(f'/api/v1/tasks/{task.pk}/move/', {'status': 'done'}, format='json')
        self.assertEqual(resp.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, 'done')

    def test_non_assignee_cannot_move_task(self):
        task = Task.objects.create(module=self.module, title='Task', created_by=self.admin)
        outsider_client = APIClient()
        _auth(outsider_client, self.outsider)
        resp = outsider_client.patch(f'/api/v1/tasks/{task.pk}/move/', {'status': 'done'}, format='json')
        # Outsider is not even a project member, should get 403
        self.assertIn(resp.status_code, [403, 404])

    def test_project_board_returns_grouped_tasks(self):
        Task.objects.create(module=self.module, title='Todo Task', status='todo', created_by=self.admin)
        Task.objects.create(module=self.module, title='Done Task', status='done', created_by=self.admin)
        resp = self.client.get(f'/api/v1/projects/{self.project.pk}/board/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('todo', resp.data)
        self.assertIn('done', resp.data)
        self.assertEqual(len(resp.data['todo']), 1)
        self.assertEqual(len(resp.data['done']), 1)

    def test_project_progress_zero_tasks(self):
        from rest_framework.test import APIClient
        resp = self.client.get(f'/api/v1/projects/{self.project.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['progress'], 0)

    def test_project_progress_computed(self):
        Task.objects.create(module=self.module, title='T1', status='done', created_by=self.admin)
        Task.objects.create(module=self.module, title='T2', status='todo', created_by=self.admin)
        resp = self.client.get(f'/api/v1/projects/{self.project.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['progress'], 50)

    def test_assignment_notifies_assignee_and_super_admin(self):
        resp = self.client.post(f'/api/v1/modules/{self.module.pk}/tasks/', {
            'title': 'Notify assignment',
            'assignee': str(self.member.pk),
        }, format='json')
        self.assertEqual(resp.status_code, 201)

        self.assertTrue(
            Notification.objects.filter(
                recipient=self.member,
                title__icontains='Task assigned',
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.super_admin,
                title__icontains='Task assigned',
            ).exists()
        )

    def test_done_notifies_project_lead_admin_and_super_admin(self):
        task = Task.objects.create(
            module=self.module,
            title='Done notification',
            assignee=self.member,
            status='todo',
            created_by=self.admin,
        )

        member_client = APIClient()
        _auth(member_client, self.member)
        resp = member_client.patch(f'/api/v1/tasks/{task.pk}/move/', {'status': 'done'}, format='json')
        self.assertEqual(resp.status_code, 200)

        self.assertTrue(
            Notification.objects.filter(
                recipient=self.admin,
                title__icontains='Task completed',
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.super_admin,
                title__icontains='Task completed',
            ).exists()
        )

    def test_task_crud_emits_notifications(self):
        create_resp = self.client.post(f'/api/v1/modules/{self.module.pk}/tasks/', {
            'title': 'Lifecycle Task',
            'status': 'todo',
            'priority': 'medium',
        }, format='json')
        self.assertEqual(create_resp.status_code, 201)
        task_id = create_resp.data['id']

        patch_resp = self.client.patch(f'/api/v1/modules/{self.module.pk}/tasks/{task_id}/', {
            'status': 'in_progress',
        }, format='json')
        self.assertEqual(patch_resp.status_code, 200)

        delete_resp = self.client.delete(f'/api/v1/modules/{self.module.pk}/tasks/{task_id}/')
        self.assertEqual(delete_resp.status_code, 200)

        self.assertTrue(Notification.objects.filter(title__icontains='Task created').exists())
        self.assertTrue(Notification.objects.filter(title__icontains='Task status changed').exists())
        self.assertTrue(Notification.objects.filter(title__icontains='Task deleted').exists())
