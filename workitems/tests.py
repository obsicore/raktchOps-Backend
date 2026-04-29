"""Tests for workitems app: CRUD, Kanban moves, comments, visibility."""
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from accounts.models import User, AccountStatus
from rbac.models import UserRole, Role
from people.models import EmployeeProfile
from projects.models import Project, ProjectMember
from notifications.models import Notification
from .models import WorkItem, Comment, MoveLog, VALID_TRANSITIONS


def make_user(email, role=Role.STAFF):
    user = User.objects.create_user(email=email, password='Pass123!', account_status=AccountStatus.ACTIVE)
    UserRole.objects.create(user=user, role=role, is_primary=True)
    return user

def make_profile(user):
    profile, _ = EmployeeProfile.objects.get_or_create(
        user=user,
        defaults={'full_name': user.email.split('@')[0], 'work_email': user.email},
    )
    return profile
def auth_client(user):
    c = APIClient(); refresh = RefreshToken.for_user(user)
    c.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}'); return c

def make_project(owner): return Project.objects.create(name='Test Project', owner=owner)
def make_item(project, reporter, title='Fix bug', item_status='backlog'):
    return WorkItem.objects.create(title=title, project=project, reporter=reporter, status=item_status)


class WorkItemCreateTests(TestCase):
    def setUp(self):
        self.pm_user = make_user('pm@t.com', Role.PROJECT_MANAGER)
        self.pm = make_profile(self.pm_user)
        self.staff_user = make_user('staff@t.com')
        self.staff = make_profile(self.staff_user)
        self.project = make_project(self.pm)
        ProjectMember.objects.create(project=self.project, employee=self.staff)

    def test_member_can_create_item(self):
        client = auth_client(self.staff_user)
        resp = client.post('/api/v1/workitems/', {'title': 'Task', 'project': str(self.project.id), 'reporter': str(self.staff.id)}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_non_member_blocked(self):
        outsider_user = make_user('out@t.com')
        make_profile(outsider_user)
        client = auth_client(outsider_user)
        resp = client.post('/api/v1/workitems/', {'title': 'Steal', 'project': str(self.project.id), 'reporter': str(outsider_user.id)}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_blank_title_rejected(self):
        client = auth_client(self.pm_user)
        resp = client.post('/api/v1/workitems/', {'title': '  ', 'project': str(self.project.id), 'reporter': str(self.pm.id)}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_work_item_crud_emits_notifications(self):
        client = auth_client(self.pm_user)
        create_resp = client.post('/api/v1/workitems/', {
            'title': 'Lifecycle item',
            'project': str(self.project.id),
            'reporter': str(self.pm.id),
            'status': 'todo',
        }, format='json')
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        item_id = create_resp.data['id']

        patch_resp = client.patch(f'/api/v1/workitems/{item_id}/', {
            'status': 'in_progress',
        }, format='json')
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)

        delete_resp = client.delete(f'/api/v1/workitems/{item_id}/')
        self.assertEqual(delete_resp.status_code, status.HTTP_200_OK)

        self.assertTrue(Notification.objects.filter(title__icontains='Work item created').exists())
        self.assertTrue(Notification.objects.filter(title__icontains='Work item status changed').exists())
        self.assertTrue(Notification.objects.filter(title__icontains='Work item deleted').exists())


class KanbanMoveTests(TestCase):
    def setUp(self):
        self.pm_user = make_user('pm@t.com', Role.PROJECT_MANAGER)
        self.pm = make_profile(self.pm_user)
        self.project = make_project(self.pm)
        self.item = make_item(self.project, self.pm, item_status='backlog')

    def test_valid_move_persisted(self):
        client = auth_client(self.pm_user)
        resp = client.patch(f'/api/v1/workitems/{self.item.id}/move/', {'status': 'todo'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, 'todo')
        self.assertTrue(MoveLog.objects.filter(work_item=self.item, from_status='backlog', to_status='todo').exists())

    def test_invalid_transition_rejected(self):
        client = auth_client(self.pm_user)
        resp = client.patch(f'/api/v1/workitems/{self.item.id}/move/', {'status': 'done'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_all_valid_transitions_work(self):
        """Verify VALID_TRANSITIONS dict is self-consistent."""
        all_statuses = set(VALID_TRANSITIONS.keys())
        for from_s, targets in VALID_TRANSITIONS.items():
            for target in targets:
                self.assertIn(target, all_statuses, f'{target} not a valid status')


class CommentTests(TestCase):
    def setUp(self):
        self.pm_user = make_user('pm@t.com', Role.PROJECT_MANAGER)
        self.pm = make_profile(self.pm_user)
        self.staff_user = make_user('staff@t.com')
        self.staff = make_profile(self.staff_user)
        self.project = make_project(self.pm)
        ProjectMember.objects.create(project=self.project, employee=self.staff)
        self.item = make_item(self.project, self.pm)

    def test_member_can_comment(self):
        client = auth_client(self.staff_user)
        resp = client.post(f'/api/v1/workitems/{self.item.id}/comments/', {'body': 'LGTM'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_blank_comment_rejected(self):
        client = auth_client(self.pm_user)
        resp = client.post(f'/api/v1/workitems/{self.item.id}/comments/', {'body': '  '}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_comment_crud_emits_notifications(self):
        client = auth_client(self.staff_user)
        create_resp = client.post(f'/api/v1/workitems/{self.item.id}/comments/', {'body': 'First'}, format='json')
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        comment_id = create_resp.data['id']

        patch_resp = client.patch(
            f'/api/v1/workitems/{self.item.id}/comments/{comment_id}/',
            {'body': 'Updated'},
            format='json',
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)

        delete_resp = client.delete(f'/api/v1/workitems/{self.item.id}/comments/{comment_id}/')
        self.assertEqual(delete_resp.status_code, status.HTTP_200_OK)

        self.assertTrue(Notification.objects.filter(title__icontains='Comment added').exists())
        self.assertTrue(Notification.objects.filter(title__icontains='Comment updated').exists())
        self.assertTrue(Notification.objects.filter(title__icontains='Comment deleted').exists())


class KanbanBoardViewTests(TestCase):
    def setUp(self):
        self.pm_user = make_user('pm@t.com', Role.PROJECT_MANAGER)
        self.pm = make_profile(self.pm_user)
        self.project = make_project(self.pm)
        make_item(self.project, self.pm, 'Task 1', 'todo')
        make_item(self.project, self.pm, 'Task 2', 'in_progress')

    def test_board_returns_columns(self):
        client = auth_client(self.pm_user)
        resp = client.get(f'/api/v1/workitems/board/?project={self.project.id}')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('columns', resp.data)
        self.assertEqual(resp.data['columns']['todo']['count'], 1)
        self.assertEqual(resp.data['columns']['in_progress']['count'], 1)

    def test_board_requires_project_param(self):
        client = auth_client(self.pm_user)
        resp = client.get('/api/v1/workitems/board/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
