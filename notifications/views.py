"""Views for the notifications app."""
import logging
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rbac.permissions import IsActiveUser
from rbac.models import Role, get_user_role

from .models import Notification
from .serializers import NotificationSerializer, NotificationCreateSerializer
from .services import create_notification_fanout, project_related_user_ids

logger = logging.getLogger(__name__)


class NotifPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class NotificationListView(APIView):
    """
    GET /api/v1/notifications/ — own notifications, unread-first
    """
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        qs = Notification.objects.filter(recipient=request.user)
        unread_only = request.query_params.get('unread')
        if unread_only in ('true', '1'):
            qs = qs.filter(is_read=False)
        notif_type = request.query_params.get('type')
        if notif_type:
            qs = qs.filter(type=notif_type)
        qs = qs.order_by('is_read', '-created_at')
        paginator = NotifPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(NotificationSerializer(page, many=True).data)

    def post(self, request):
        """
        POST /api/v1/notifications/
        Manual notification fanout for elevated roles.
        """
        role = get_user_role(request.user)
        if role not in (Role.SUPER_ADMIN, Role.ADMIN, Role.PROJECT_MANAGER, Role.TEAM_LEAD):
            raise PermissionDenied('You do not have permission to create notifications.')

        serializer = NotificationCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'detail': 'Validation failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        project = data.get('project')
        explicit_recipients = set(data.get('recipient_ids') or [])
        recipients = set()

        if project:
            # Team leads can send project-scoped notices only for projects they own.
            if role == Role.TEAM_LEAD and getattr(project.owner, 'user_id', None) != request.user.id:
                raise PermissionDenied('Team leads can only notify for projects they own.')

            allowed_recipients = project_related_user_ids(project=project, include_admins=True)
            if explicit_recipients:
                recipients = allowed_recipients.intersection(explicit_recipients)
            else:
                recipients = allowed_recipients
        elif explicit_recipients:
            # Non-admin elevated roles must use project scoping to resolve recipients safely.
            if role not in (Role.SUPER_ADMIN, Role.ADMIN):
                raise PermissionDenied('Project managers and team leads must provide project_id for manual notifications.')
            recipients = explicit_recipients
        else:
            recipients = {request.user.id}

        created_count = create_notification_fanout(
            recipient_ids=recipients,
            notification_type=data['type'],
            title=data['title'],
            body=data.get('body', ''),
            link=data.get('link', ''),
        )
        return Response({'created': created_count}, status=status.HTTP_201_CREATED)


class UnreadCountView(APIView):
    """GET /api/v1/notifications/unread-count/ — quick badge count."""
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return Response({'unread_count': count})


class MarkAllReadView(APIView):
    """POST /api/v1/notifications/mark-all-read/ — bulk mark as read."""
    permission_classes = [IsAuthenticated, IsActiveUser]

    def post(self, request):
        from django.utils import timezone
        updated = Notification.objects.filter(recipient=request.user, is_read=False).update(
            is_read=True, read_at=timezone.now()
        )
        return Response({'detail': f'{updated} notification(s) marked as read.'})


class NotificationDetailView(APIView):
    """PATCH /api/v1/notifications/<pk>/ — mark single notification read/unread."""
    permission_classes = [IsAuthenticated, IsActiveUser]

    def _get(self, request, pk):
        try:
            return Notification.objects.get(pk=pk, recipient=request.user)
        except Notification.DoesNotExist:
            raise NotFound('Notification not found.')

    def patch(self, request, pk):
        notif = self._get(request, pk)
        is_read = request.data.get('is_read')
        if is_read is True:
            notif.mark_read()
        elif is_read is False:
            from django.utils import timezone
            notif.is_read = False
            notif.read_at = None
            notif.save(update_fields=['is_read', 'read_at'])
        return Response(NotificationSerializer(notif).data)

    def delete(self, request, pk):
        notif = self._get(request, pk)
        notif.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
