"""Tests for notifications app."""
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from accounts.models import User, AccountStatus
from rbac.models import UserRole, Role
from .models import Notification


def make_user(email, role=Role.STAFF):
    user = User.objects.create_user(email=email, password='Pass123!', account_status=AccountStatus.ACTIVE)
    UserRole.objects.create(user=user, role=role, is_primary=True)
    return user

def auth_client(user):
    c = APIClient(); refresh = RefreshToken.for_user(user)
    c.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}'); return c

def make_notif(user, title='Test', is_read=False):
    return Notification.objects.create(recipient=user, title=title, is_read=is_read)


class NotificationTests(TestCase):
    def setUp(self):
        self.user = make_user('user@t.com')
        self.other = make_user('other@t.com')
        self.admin = make_user('admin@t.com', role=Role.ADMIN)
        self.n1 = make_notif(self.user, 'Notification 1')
        self.n2 = make_notif(self.user, 'Notification 2', is_read=True)
        make_notif(self.other, 'Other User Notif')

    def test_user_sees_only_own_notifications(self):
        client = auth_client(self.user)
        resp = client.get('/api/v1/notifications/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 2)

    def test_unread_filter(self):
        client = auth_client(self.user)
        resp = client.get('/api/v1/notifications/?unread=true')
        self.assertEqual(resp.data['count'], 1)
        self.assertFalse(resp.data['results'][0]['is_read'])

    def test_unread_count(self):
        client = auth_client(self.user)
        resp = client.get('/api/v1/notifications/unread-count/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['unread_count'], 1)

    def test_mark_single_read(self):
        client = auth_client(self.user)
        resp = client.patch(f'/api/v1/notifications/{self.n1.id}/', {'is_read': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.n1.refresh_from_db()
        self.assertTrue(self.n1.is_read)

    def test_mark_all_read(self):
        client = auth_client(self.user)
        resp = client.post('/api/v1/notifications/mark-all-read/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Notification.objects.filter(recipient=self.user, is_read=False).count(), 0)

    def test_other_user_notification_not_accessible(self):
        other_notif = Notification.objects.get(recipient=self.other)
        client = auth_client(self.user)
        resp = client.patch(f'/api/v1/notifications/{other_notif.id}/', {'is_read': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_own_notification(self):
        client = auth_client(self.user)
        resp = client.delete(f'/api/v1/notifications/{self.n1.id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Notification.objects.filter(pk=self.n1.id).exists())

    def test_non_admin_cannot_manual_create(self):
        client = auth_client(self.user)
        resp = client.post(
            '/api/v1/notifications/',
            {'title': 'Manual', 'body': 'Hello', 'recipient_ids': [str(self.other.id)]},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_manual_create(self):
        client = auth_client(self.admin)
        resp = client.post(
            '/api/v1/notifications/',
            {'title': 'Manual', 'body': 'Hello', 'recipient_ids': [str(self.user.id)]},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['created'], 1)
        self.assertTrue(Notification.objects.filter(recipient=self.user, title='Manual').exists())
