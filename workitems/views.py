"""Views for the workitems and boards apps."""

import logging
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.models import NotificationType
from notifications.services import notify_project_related_users
from rbac.permissions import IsActiveUser
from rbac.models import get_user_role, Role
from people.models import EmployeeProfile

from .models import WorkItem, Comment, WorkItemDependency, MoveLog, VALID_TRANSITIONS
from .serializers import (
    WorkItemListSerializer, WorkItemDetailSerializer, KanbanMoveSerializer,
    CommentSerializer, WorkItemDependencySerializer, MoveLogSerializer,
)

logger = logging.getLogger(__name__)


class ItemPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100


def _get_profile(user):
    try:
        return EmployeeProfile.objects.get(user=user)
    except EmployeeProfile.DoesNotExist:
        return None


def _can_manage_item(user, item):
    """Admin/PM can manage any item. Assignee/reporter/project-owner can manage their own."""
    role = get_user_role(user)
    if role in (Role.SUPER_ADMIN, Role.ADMIN, Role.PROJECT_MANAGER):
        return True
    profile = _get_profile(user)
    if not profile:
        return False
    return (
        item.assignee == profile
        or item.reporter == profile
        or item.project.owner == profile
    )


def _check_project_access(user, project):
    """Staff/TL must be project member or owner to access work items."""
    role = get_user_role(user)
    if role in (Role.SUPER_ADMIN, Role.ADMIN, Role.PROJECT_MANAGER):
        return
    profile = _get_profile(user)
    if not profile:
        raise PermissionDenied('No employee profile found.')
    is_owner = project.owner == profile
    is_member = project.memberships.filter(employee=profile).exists()
    if not (is_owner or is_member):
        raise PermissionDenied('You are not a member of this project.')


def _work_item_user_ids(item):
    user_ids = []
    assignee_user_id = getattr(getattr(item, 'assignee', None), 'user_id', None)
    reporter_user_id = getattr(getattr(item, 'reporter', None), 'user_id', None)
    if assignee_user_id:
        user_ids.append(assignee_user_id)
    if reporter_user_id:
        user_ids.append(reporter_user_id)
    return user_ids


# ---------------------------------------------------------------------------
# Work Items
# ---------------------------------------------------------------------------

class WorkItemListCreateView(APIView):
    """GET/POST /api/v1/workitems/"""
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        qs = WorkItem.objects.select_related(
            'project', 'sprint', 'assignee', 'reporter', 'parent'
        )
        role = get_user_role(request.user)

        # Scope to accessible projects for staff/TL
        if role in (Role.STAFF, Role.TEAM_LEAD):
            profile = _get_profile(request.user)
            if not profile:
                return Response({'count': 0, 'results': []})
            from projects.models import Project
            accessible_projects = Project.objects.filter(
                memberships__employee=profile
            ) | Project.objects.filter(owner=profile)
            qs = qs.filter(project__in=accessible_projects)

        # Filters
        project_id = request.query_params.get('project')
        if project_id:
            qs = qs.filter(project_id=project_id)

        sprint_id = request.query_params.get('sprint')
        if sprint_id:
            qs = qs.filter(sprint_id=sprint_id)

        item_status = request.query_params.get('status')
        if item_status:
            qs = qs.filter(status=item_status)

        item_type = request.query_params.get('type')
        if item_type:
            qs = qs.filter(type=item_type)

        item_priority = request.query_params.get('priority')
        if item_priority:
            qs = qs.filter(priority=item_priority)

        assignee_id = request.query_params.get('assignee')
        if assignee_id:
            qs = qs.filter(assignee_id=assignee_id)

        is_blocked = request.query_params.get('is_blocked')
        if is_blocked in ('true', '1'):
            qs = qs.filter(is_blocked=True)

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(title__icontains=search)

        paginator = ItemPagination()
        page = paginator.paginate_queryset(qs.distinct(), request)
        serializer = WorkItemListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        # Check project access first so non-members get 403, not 400
        project_id = request.data.get('project')
        if project_id:
            from projects.models import Project as Proj
            try:
                pre_project = Proj.objects.get(pk=project_id)
                _check_project_access(request.user, pre_project)
            except Proj.DoesNotExist:
                pass  # serializer will handle the missing project error

        serializer = WorkItemDetailSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'detail': 'Validation failed.', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        item = serializer.save()
        try:
            notify_project_related_users(
                project=item.project,
                notification_type=NotificationType.GENERAL,
                title=f'Work item created: {item.title}',
                body=f"Work item '{item.title}' was created in project '{item.project.name}'.",
                link=f'/work-items/{item.pk}/',
                extra_user_ids=_work_item_user_ids(item),
                exclude_user_ids=[request.user.id],
            )
        except Exception:
            pass
        logger.info('%s created work item %s', request.user.email, item.title)
        return Response(WorkItemDetailSerializer(item).data, status=status.HTTP_201_CREATED)


class WorkItemDetailView(APIView):
    """GET/PATCH /api/v1/workitems/<pk>/"""
    permission_classes = [IsAuthenticated, IsActiveUser]

    def _get_item(self, pk):
        try:
            return WorkItem.objects.select_related(
                'project', 'sprint', 'assignee', 'reporter', 'parent'
            ).get(pk=pk)
        except WorkItem.DoesNotExist:
            raise NotFound('Work item not found.')

    def get(self, request, pk):
        item = self._get_item(pk)
        _check_project_access(request.user, item.project)
        return Response(WorkItemDetailSerializer(item).data)

    def patch(self, request, pk):
        item = self._get_item(pk)
        _check_project_access(request.user, item.project)
        if not _can_manage_item(request.user, item):
            raise PermissionDenied('You cannot edit this work item.')
        old_status = item.status

        serializer = WorkItemDetailSerializer(item, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({'detail': 'Validation failed.', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        item = serializer.save()
        try:
            if old_status != item.status:
                notify_project_related_users(
                    project=item.project,
                    notification_type=NotificationType.STATUS_CHANGED,
                    title=f'Work item status changed: {item.title}',
                    body=(
                        f"Work item '{item.title}' status changed from "
                        f"'{old_status}' to '{item.status}'."
                    ),
                    link=f'/work-items/{item.pk}/',
                    extra_user_ids=_work_item_user_ids(item),
                    exclude_user_ids=[request.user.id],
                )
            else:
                notify_project_related_users(
                    project=item.project,
                    notification_type=NotificationType.GENERAL,
                    title=f'Work item updated: {item.title}',
                    body=f"Work item '{item.title}' was updated in project '{item.project.name}'.",
                    link=f'/work-items/{item.pk}/',
                    extra_user_ids=_work_item_user_ids(item),
                    exclude_user_ids=[request.user.id],
                )
        except Exception:
            pass
        logger.info('%s updated work item %s', request.user.email, item.title)
        return Response(WorkItemDetailSerializer(item).data)

    def delete(self, request, pk):
        item = self._get_item(pk)
        _check_project_access(request.user, item.project)
        role = get_user_role(request.user)
        if role not in (Role.SUPER_ADMIN, Role.ADMIN, Role.PROJECT_MANAGER):
            raise PermissionDenied('Admin or PM required to delete work items.')
        item_title = item.title
        project = item.project
        related_user_ids = _work_item_user_ids(item)
        item.delete()
        try:
            notify_project_related_users(
                project=project,
                notification_type=NotificationType.GENERAL,
                title=f'Work item deleted: {item_title}',
                body=f"Work item '{item_title}' was deleted from project '{project.name}'.",
                link='/work-items/',
                extra_user_ids=related_user_ids,
                exclude_user_ids=[request.user.id],
            )
        except Exception:
            pass
        logger.info('%s deleted work item %s', request.user.email, item_title)
        return Response({'detail': f'Work item "{item_title}" deleted.'})


# ---------------------------------------------------------------------------
# Kanban Move
# ---------------------------------------------------------------------------

class KanbanMoveView(APIView):
    """PATCH /api/v1/workitems/<pk>/move/ — validates and persists status transition."""
    permission_classes = [IsAuthenticated, IsActiveUser]

    def patch(self, request, pk):
        try:
            item = WorkItem.objects.select_related('project').get(pk=pk)
        except WorkItem.DoesNotExist:
            raise NotFound('Work item not found.')

        _check_project_access(request.user, item.project)
        if not _can_manage_item(request.user, item):
            raise PermissionDenied('You cannot move this work item.')

        serializer = KanbanMoveSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'detail': 'Validation failed.', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        new_status = serializer.validated_data['status']
        old_status = item.status

        if new_status == old_status:
            return Response(WorkItemDetailSerializer(item).data)

        allowed = VALID_TRANSITIONS.get(old_status, [])
        if new_status not in allowed:
            return Response(
                {'detail': f'Invalid transition: {old_status} → {new_status}. Allowed: {", ".join(allowed)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        item.status = new_status
        item.save(update_fields=['status', 'updated_at'])

        MoveLog.objects.create(
            work_item=item,
            moved_by=request.user,
            from_status=old_status,
            to_status=new_status,
        )
        try:
            notify_project_related_users(
                project=item.project,
                notification_type=NotificationType.STATUS_CHANGED,
                title=f'Work item moved: {item.title}',
                body=f"Work item '{item.title}' moved from '{old_status}' to '{new_status}'.",
                link=f'/work-items/{item.pk}/',
                extra_user_ids=_work_item_user_ids(item),
                exclude_user_ids=[request.user.id],
            )
        except Exception:
            pass

        logger.info('%s moved work item %s: %s → %s', request.user.email, item.title, old_status, new_status)
        return Response(WorkItemDetailSerializer(item).data)


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

class CommentListCreateView(APIView):
    """GET/POST /api/v1/workitems/<pk>/comments/"""
    permission_classes = [IsAuthenticated, IsActiveUser]

    def _get_item(self, pk):
        try:
            return WorkItem.objects.select_related('project').get(pk=pk)
        except WorkItem.DoesNotExist:
            raise NotFound('Work item not found.')

    def get(self, request, pk):
        item = self._get_item(pk)
        _check_project_access(request.user, item.project)
        comments = item.comments.select_related('author').order_by('created_at')
        return Response({'count': comments.count(), 'results': CommentSerializer(comments, many=True).data})

    def post(self, request, pk):
        item = self._get_item(pk)
        _check_project_access(request.user, item.project)
        profile = _get_profile(request.user)

        data = dict(request.data)
        data['work_item'] = str(item.pk)
        data['author'] = str(profile.pk) if profile else None

        serializer = CommentSerializer(data=data)
        if not serializer.is_valid():
            return Response({'detail': 'Validation failed.', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        comment = serializer.save()
        try:
            notify_project_related_users(
                project=item.project,
                notification_type=NotificationType.COMMENT_ADDED,
                title=f'Comment added on: {item.title}',
                body='A new comment was added to this work item.',
                link=f'/work-items/{item.pk}/',
                extra_user_ids=_work_item_user_ids(item),
                exclude_user_ids=[request.user.id],
            )
        except Exception:
            pass
        return Response(CommentSerializer(comment).data, status=status.HTTP_201_CREATED)


class CommentDetailView(APIView):
    """PATCH/DELETE /api/v1/workitems/<pk>/comments/<comment_pk>/"""
    permission_classes = [IsAuthenticated, IsActiveUser]

    def _get_comment(self, pk, comment_pk):
        try:
            return Comment.objects.select_related('author', 'work_item__project').get(pk=comment_pk, work_item_id=pk)
        except Comment.DoesNotExist:
            raise NotFound('Comment not found.')

    def patch(self, request, pk, comment_pk):
        comment = self._get_comment(pk, comment_pk)
        _check_project_access(request.user, comment.work_item.project)
        profile = _get_profile(request.user)
        role = get_user_role(request.user)
        if comment.author != profile and role not in (Role.SUPER_ADMIN, Role.ADMIN, Role.PROJECT_MANAGER):
            raise PermissionDenied('You can only edit your own comments.')
        serializer = CommentSerializer(comment, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({'detail': 'Validation failed.', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        comment = serializer.save()
        try:
            notify_project_related_users(
                project=comment.work_item.project,
                notification_type=NotificationType.GENERAL,
                title=f'Comment updated on: {comment.work_item.title}',
                body='A comment was updated on this work item.',
                link=f'/work-items/{comment.work_item_id}/',
                extra_user_ids=_work_item_user_ids(comment.work_item),
                exclude_user_ids=[request.user.id],
            )
        except Exception:
            pass
        return Response(CommentSerializer(comment).data)

    def delete(self, request, pk, comment_pk):
        comment = self._get_comment(pk, comment_pk)
        _check_project_access(request.user, comment.work_item.project)
        profile = _get_profile(request.user)
        role = get_user_role(request.user)
        if comment.author != profile and role not in (Role.SUPER_ADMIN, Role.ADMIN, Role.PROJECT_MANAGER):
            raise PermissionDenied('You can only delete your own comments.')
        item = comment.work_item
        comment.delete()
        try:
            notify_project_related_users(
                project=item.project,
                notification_type=NotificationType.GENERAL,
                title=f'Comment deleted on: {item.title}',
                body='A comment was deleted from this work item.',
                link=f'/work-items/{item.pk}/',
                extra_user_ids=_work_item_user_ids(item),
                exclude_user_ids=[request.user.id],
            )
        except Exception:
            pass
        return Response({'detail': 'Comment deleted.'})


# ---------------------------------------------------------------------------
# Kanban board view
# ---------------------------------------------------------------------------

class KanbanBoardView(APIView):
    """GET /api/v1/workitems/board/?project=<uuid> — grouped by status."""
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        project_id = request.query_params.get('project')
        if not project_id:
            return Response({'detail': 'project query parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)

        from projects.models import Project
        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist:
            raise NotFound('Project not found.')

        _check_project_access(request.user, project)

        # Optional filters
        assignee_id = request.query_params.get('assignee')
        item_type = request.query_params.get('type')
        show_blocked_only = request.query_params.get('blocked') in ('true', '1')

        qs = WorkItem.objects.select_related('assignee', 'reporter', 'parent').filter(project=project)
        if assignee_id:
            qs = qs.filter(assignee_id=assignee_id)
        if item_type:
            qs = qs.filter(type=item_type)
        if show_blocked_only:
            qs = qs.filter(is_blocked=True)

        from .models import WorkItemStatus
        columns = {}
        for s in WorkItemStatus:
            items = qs.filter(status=s.value)
            columns[s.value] = {
                'label': s.label,
                'items': WorkItemListSerializer(items, many=True).data,
                'count': items.count(),
            }

        return Response({
            'project': project_id,
            'project_name': project.name,
            'columns': columns,
        })


# ---------------------------------------------------------------------------
# Move log
# ---------------------------------------------------------------------------

class MoveLogView(APIView):
    """GET /api/v1/workitems/<pk>/moves/"""
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request, pk):
        try:
            item = WorkItem.objects.select_related('project').get(pk=pk)
        except WorkItem.DoesNotExist:
            raise NotFound('Work item not found.')
        _check_project_access(request.user, item.project)
        logs = item.move_log.select_related('moved_by').order_by('-moved_at')[:50]
        return Response({'count': logs.count(), 'results': MoveLogSerializer(logs, many=True).data})
