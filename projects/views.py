"""
Views for the projects app.
All endpoints under /api/v1/projects/.
"""

import logging
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rbac.permissions import IsActiveUser
from rbac.models import get_user_role, Role
from notifications.models import NotificationType
from notifications.services import (
    notify_project_related_users,
    notify_users_with_super_admins,
)

from .models import Project, ProjectMember
from .serializers import (
    ProjectListSerializer,
    ProjectDetailSerializer,
    ProjectMemberSerializer,
)

logger = logging.getLogger(__name__)


class ProjectPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


def _can_manage_project(user, project):
    """Super admin or admin can manage any project. PM and project leader can manage their own."""
    role = get_user_role(user)
    if role in (Role.SUPER_ADMIN, Role.ADMIN, Role.PROJECT_MANAGER):
        return True
    try:
        return project.owner.user == user
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Project list + create
# ---------------------------------------------------------------------------

class ProjectListCreateView(APIView):
    """
    GET  /api/v1/projects/   — any active user (org-wide visibility)
    POST /api/v1/projects/   — admin/PM/super-admin (staff cannot create)
    """
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        qs = Project.objects.select_related('owner').prefetch_related('memberships')

        # Status filter
        filter_status = request.query_params.get('status')
        if filter_status:
            qs = qs.filter(status=filter_status)

        # Health filter
        filter_health = request.query_params.get('health')
        if filter_health:
            qs = qs.filter(health=filter_health)

        # Type filter
        filter_type = request.query_params.get('type')
        if filter_type:
            qs = qs.filter(type=filter_type)

        # Search
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search) | qs.filter(code__icontains=search)
            qs = qs.distinct()

        # Ordering
        ordering = request.query_params.get('ordering', '-created_at')
        allowed = ['-created_at', 'created_at', 'name', '-name', 'due_date', '-due_date']
        if ordering in allowed:
            qs = qs.order_by(ordering)

        paginator = ProjectPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = ProjectListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        # Staff can view projects but cannot create them.
        if get_user_role(request.user) == Role.STAFF:
            raise PermissionDenied('Staff users can view projects but cannot create them.')

        serializer = ProjectDetailSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'detail': 'Validation failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        project = serializer.save()
        try:
            notify_project_related_users(
                project=project,
                notification_type=NotificationType.GENERAL,
                title=f'Project created: {project.name}',
                body=f"Project '{project.name}' was created.",
                link=f'/projects/{project.pk}/',
                exclude_user_ids=[request.user.id],
            )
        except Exception:
            pass
        logger.info('%s created project %s', request.user.email, project.name)
        return Response(
            ProjectDetailSerializer(project).data,
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Project detail
# ---------------------------------------------------------------------------

class ProjectDetailView(APIView):
    """
    GET    /api/v1/projects/<pk>/
    PATCH  /api/v1/projects/<pk>/  — admin, PM, or project owner
    DELETE /api/v1/projects/<pk>/  — admin only (archive)
    """
    permission_classes = [IsAuthenticated, IsActiveUser]

    def _get_project(self, pk):
        try:
            return Project.objects.select_related('owner').prefetch_related('memberships').get(pk=pk)
        except Project.DoesNotExist:
            raise NotFound('Project not found.')

    def _check_visibility(self, user, project):
        """All active authenticated users can view all projects."""
        return True

    def get(self, request, pk):
        project = self._get_project(pk)
        self._check_visibility(request.user, project)
        return Response(ProjectDetailSerializer(project).data)

    def patch(self, request, pk):
        project = self._get_project(pk)
        if not _can_manage_project(request.user, project):
            raise PermissionDenied('You do not have permission to edit this project.')

        previous_status = project.status

        serializer = ProjectDetailSerializer(project, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(
                {'detail': 'Validation failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        project = serializer.save()

        try:
            if previous_status != project.status:
                if project.status == 'completed':
                    title = f'Project completed: {project.name}'
                    body = f"Project '{project.name}' has been marked as completed."
                else:
                    title = f'Project status changed: {project.name}'
                    body = (
                        f"Project '{project.name}' status changed from "
                        f"'{previous_status}' to '{project.status}'."
                    )
                notify_project_related_users(
                    project=project,
                    notification_type=NotificationType.STATUS_CHANGED,
                    title=title,
                    body=body,
                    link=f'/projects/{project.pk}/',
                )
            else:
                notify_project_related_users(
                    project=project,
                    notification_type=NotificationType.GENERAL,
                    title=f'Project updated: {project.name}',
                    body=f"Project '{project.name}' details were updated.",
                    link=f'/projects/{project.pk}/',
                )
        except Exception:
            pass

        logger.info('%s updated project %s', request.user.email, project.name)
        return Response(ProjectDetailSerializer(project).data)

    def delete(self, request, pk):
        """Archive project (admin only)."""
        if get_user_role(request.user) not in (Role.SUPER_ADMIN, Role.ADMIN):
            raise PermissionDenied('Admin role required to archive projects.')
        project = self._get_project(pk)
        if project.status == 'archived':
            return Response(
                {'detail': 'Project is already archived.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        project.status = 'archived'
        project.save(update_fields=['status'])
        try:
            notify_project_related_users(
                project=project,
                notification_type=NotificationType.STATUS_CHANGED,
                title=f'Project archived: {project.name}',
                body=f"Project '{project.name}' has been archived.",
                link=f'/projects/{project.pk}/',
                exclude_user_ids=[request.user.id],
            )
        except Exception:
            pass
        logger.info('%s archived project %s', request.user.email, project.name)
        return Response({'detail': f'Project "{project.name}" has been archived.'})


# ---------------------------------------------------------------------------
# Project memberships
# ---------------------------------------------------------------------------

class ProjectMemberListView(APIView):
    """
    GET  /api/v1/projects/<pk>/members/   — project members or admin/PM
    POST /api/v1/projects/<pk>/members/   — admin, PM, or project owner
    """
    permission_classes = [IsAuthenticated, IsActiveUser]

    def _get_project(self, pk):
        try:
            return Project.objects.select_related('owner').get(pk=pk)
        except Project.DoesNotExist:
            raise NotFound('Project not found.')

    def get(self, request, pk):
        from modules.models import Module
        from tasks.models import Task

        project = self._get_project(pk)
        memberships = list(
            ProjectMember.objects.select_related(
                'employee', 'employee__user'
            ).filter(project=project).order_by('employee__full_name')
        )

        results = []
        for m in memberships:
            data = ProjectMemberSerializer(m).data
            user = m.employee.user
            data['modules_assigned'] = Module.objects.filter(
                project=project, assignee=user
            ).count()
            data['modules_done'] = Module.objects.filter(
                project=project, assignee=user, status='done'
            ).count()
            data['tasks_assigned'] = Task.objects.filter(
                module__project=project, assignee=user
            ).count()
            data['tasks_done'] = Task.objects.filter(
                module__project=project, assignee=user, status='done'
            ).count()
            results.append(data)

        return Response({'count': len(results), 'results': results})

    def post(self, request, pk):
        project = self._get_project(pk)
        if not _can_manage_project(request.user, project):
            raise PermissionDenied('Only the project owner, admin, or PM can add members.')

        data = dict(request.data)
        data['project'] = str(project.pk)
        serializer = ProjectMemberSerializer(data=data)
        if not serializer.is_valid():
            return Response(
                {'detail': 'Validation failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        membership = serializer.save()

        try:
            notify_users_with_super_admins(
                recipient_ids=[membership.employee.user_id],
                notification_type=NotificationType.PROJECT_ADDED,
                title=f'Added to project: {project.name}',
                body=(
                    f"You were added as a contributor to project '{project.name}'."
                ),
                link=f'/projects/{project.pk}/',
            )
        except Exception:
            pass

        logger.info(
            '%s added %s to project %s',
            request.user.email,
            membership.employee.full_name,
            project.name,
        )
        return Response(ProjectMemberSerializer(membership).data, status=status.HTTP_201_CREATED)


class ProjectMemberDetailView(APIView):
    """DELETE /api/v1/projects/<pk>/members/<membership_pk>/ — remove member."""
    permission_classes = [IsAuthenticated, IsActiveUser]

    def delete(self, request, pk, membership_pk):
        try:
            project = Project.objects.get(pk=pk)
        except Project.DoesNotExist:
            raise NotFound('Project not found.')

        if not _can_manage_project(request.user, project):
            raise PermissionDenied('Only the project owner, admin, or PM can remove members.')

        try:
            membership = ProjectMember.objects.select_related('employee').get(
                pk=membership_pk, project_id=pk
            )
        except ProjectMember.DoesNotExist:
            raise NotFound('Membership not found.')

        name = membership.employee.full_name
        removed_user_id = membership.employee.user_id
        membership.delete()
        try:
            notify_users_with_super_admins(
                recipient_ids=[removed_user_id],
                notification_type=NotificationType.PROJECT_ADDED,
                title=f'Removed from project: {project.name}',
                body=f"You were removed from project '{project.name}'.",
                link='/projects/',
            )
        except Exception:
            pass
        logger.info('%s removed %s from project %s', request.user.email, name, project.name)
        return Response({'detail': f'{name} removed from {project.name}.'})
