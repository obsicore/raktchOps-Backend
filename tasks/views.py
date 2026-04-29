"""
Views for the tasks app.
Endpoints nested under /api/v1/modules/<module_id>/tasks/
and a top-level move endpoint at /api/v1/tasks/<id>/move/.
"""

import logging
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.models import NotificationType
from notifications.services import notify_project_related_users
from rbac.permissions import IsActiveUser
from rbac.models import get_user_role, Role
from modules.models import Module

from .models import Task
from .serializers import TaskSerializer, TaskMoveSerializer
from .permissions import can_manage_task, can_manage_task_in_project

logger = logging.getLogger(__name__)


def _get_module(pk):
    try:
        return Module.objects.select_related('project__owner__user').get(pk=pk)
    except Module.DoesNotExist:
        raise NotFound('Module not found.')


def _check_project_visibility(user, project):
    # Project visibility is org-wide for active authenticated users.
    return True


class TaskListCreateView(APIView):
    """
    GET  /api/v1/modules/<module_id>/tasks/
    POST /api/v1/modules/<module_id>/tasks/
    """
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request, module_id):
        module = _get_module(module_id)
        _check_project_visibility(request.user, module.project)

        qs = Task.objects.filter(module=module).select_related('assignee', 'module__project')

        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        assignee_filter = request.query_params.get('assignee')
        if assignee_filter:
            qs = qs.filter(assignee_id=assignee_filter)

        paginator = PageNumberPagination()
        paginator.page_size = 50
        page = paginator.paginate_queryset(qs, request)
        serializer = TaskSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, module_id):
        module = _get_module(module_id)
        if not can_manage_task_in_project(request.user, module.project):
            raise PermissionDenied('Only the project owner or admin can create tasks.')

        data = dict(request.data)
        data['module'] = module_id

        serializer = TaskSerializer(data=data, context={'request': request, 'module': module})
        if not serializer.is_valid():
            return Response(
                {'detail': 'Validation failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        task = serializer.save(created_by=request.user, updated_by=request.user)
        try:
            notify_project_related_users(
                project=module.project,
                notification_type=NotificationType.GENERAL,
                title=f'Task created: {task.title}',
                body=(
                    f"Task '{task.title}' was created in module '{module.name}' "
                    f"for project '{module.project.name}'."
                ),
                link=f'/projects/{module.project_id}/board/',
                extra_user_ids=[task.assignee_id] if task.assignee_id else None,
                exclude_user_ids=[request.user.id],
            )
        except Exception:
            pass
        logger.info('%s created task %s in module %s', request.user.email, task.title, module.name)
        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)


class TaskDetailView(APIView):
    """
    GET    /api/v1/modules/<module_id>/tasks/<id>/
    PUT    /api/v1/modules/<module_id>/tasks/<id>/
    PATCH  /api/v1/modules/<module_id>/tasks/<id>/
    DELETE /api/v1/modules/<module_id>/tasks/<id>/
    """
    permission_classes = [IsAuthenticated, IsActiveUser]

    def _get_task(self, module_id, pk):
        module = _get_module(module_id)
        try:
            task = Task.objects.select_related('module__project__owner__user', 'assignee').get(
                pk=pk, module=module
            )
        except Task.DoesNotExist:
            raise NotFound('Task not found.')
        return module, task

    def get(self, request, module_id, pk):
        module, task = self._get_task(module_id, pk)
        _check_project_visibility(request.user, module.project)
        return Response(TaskSerializer(task).data)

    def _update(self, request, module_id, pk, partial):
        module, task = self._get_task(module_id, pk)
        if not can_manage_task(request.user, task):
            raise PermissionDenied('You do not have permission to edit this task.')
        previous_status = task.status

        data = dict(request.data)
        data['module'] = module_id

        serializer = TaskSerializer(task, data=data, partial=partial, context={'request': request, 'module': module})
        if not serializer.is_valid():
            return Response(
                {'detail': 'Validation failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        task = serializer.save(updated_by=request.user)
        try:
            if previous_status != task.status:
                notify_project_related_users(
                    project=module.project,
                    notification_type=NotificationType.STATUS_CHANGED,
                    title=f'Task status changed: {task.title}',
                    body=(
                        f"Task '{task.title}' status changed from "
                        f"'{previous_status}' to '{task.status}'."
                    ),
                    link=f'/projects/{module.project_id}/board/',
                    extra_user_ids=[task.assignee_id] if task.assignee_id else None,
                    exclude_user_ids=[request.user.id],
                )
            else:
                notify_project_related_users(
                    project=module.project,
                    notification_type=NotificationType.GENERAL,
                    title=f'Task updated: {task.title}',
                    body=f"Task '{task.title}' in module '{module.name}' was updated.",
                    link=f'/projects/{module.project_id}/board/',
                    extra_user_ids=[task.assignee_id] if task.assignee_id else None,
                    exclude_user_ids=[request.user.id],
                )
        except Exception:
            pass
        logger.info('%s updated task %s', request.user.email, task.title)
        return Response(TaskSerializer(task).data)

    def put(self, request, module_id, pk):
        return self._update(request, module_id, pk, partial=False)

    def patch(self, request, module_id, pk):
        return self._update(request, module_id, pk, partial=True)

    def delete(self, request, module_id, pk):
        module, task = self._get_task(module_id, pk)
        if not can_manage_task_in_project(request.user, module.project):
            raise PermissionDenied('Only the project owner or admin can delete tasks.')
        title = task.title
        project = module.project
        assignee_id = task.assignee_id
        task.delete()
        try:
            notify_project_related_users(
                project=project,
                notification_type=NotificationType.GENERAL,
                title=f'Task deleted: {title}',
                body=f"Task '{title}' was deleted from module '{module.name}'.",
                link=f'/projects/{project.pk}/board/',
                extra_user_ids=[assignee_id] if assignee_id else None,
                exclude_user_ids=[request.user.id],
            )
        except Exception:
            pass
        logger.info('%s deleted task %s', request.user.email, title)
        return Response({'detail': f"Task '{title}' deleted."})


class TaskMoveView(APIView):
    """PATCH /api/v1/tasks/<id>/move/ — update task status (kanban drag)."""
    permission_classes = [IsAuthenticated, IsActiveUser]

    def patch(self, request, pk):
        try:
            task = Task.objects.select_related('module__project__owner__user', 'assignee').get(pk=pk)
        except Task.DoesNotExist:
            raise NotFound('Task not found.')

        # Check project visibility
        _check_project_visibility(request.user, task.module.project)

        # Check permission: assignee can move their own task, project leader/admin can move any
        if not can_manage_task(request.user, task):
            raise PermissionDenied('You do not have permission to move this task.')

        serializer = TaskMoveSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'detail': 'Validation failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_status = task.status
        task.status = serializer.validated_data['status']
        task.updated_by = request.user
        task.save(update_fields=['status', 'updated_by', 'updated_at'])

        try:
            notify_project_related_users(
                project=task.module.project,
                notification_type=NotificationType.STATUS_CHANGED,
                title=f'Task moved: {task.title}',
                body=f"Task '{task.title}' moved from '{old_status}' to '{task.status}'.",
                link=f'/projects/{task.module.project_id}/board/',
                extra_user_ids=[task.assignee_id] if task.assignee_id else None,
                exclude_user_ids=[request.user.id],
            )
        except Exception:
            pass

        logger.info('%s moved task %s from %s to %s', request.user.email, task.title, old_status, task.status)
        return Response(TaskSerializer(task).data)


class OrgBoardView(APIView):
    """
    GET /api/v1/board/
    Returns all accessible tasks grouped by status, plus project progress summaries.
    Optional ?project=<uuid> filter.
    """
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        from projects.models import Project
        from modules.models import Module

        role = get_user_role(request.user)
        project_id_filter = request.query_params.get('project')

        if role in (Role.SUPER_ADMIN, Role.ADMIN, Role.PROJECT_MANAGER):
            projects_qs = Project.objects.all()
        else:
            try:
                from people.models import EmployeeProfile
                profile = EmployeeProfile.objects.get(user=request.user)
                from django.db.models import Q
                projects_qs = Project.objects.filter(
                    Q(owner=profile) | Q(memberships__employee=profile)
                ).distinct()
            except Exception:
                projects_qs = Project.objects.none()

        if project_id_filter:
            projects_qs = projects_qs.filter(pk=project_id_filter)

        project_ids = list(projects_qs.values_list('pk', flat=True))

        tasks = Task.objects.filter(
            module__project_id__in=project_ids
        ).select_related('assignee', 'module__project').order_by('module__project__name', 'created_at')

        board = {'todo': [], 'in_progress': [], 'blocked': [], 'done': []}
        serializer = TaskSerializer(tasks, many=True)
        for task_data in serializer.data:
            s = task_data.get('status', 'todo')
            if s in board:
                board[s].append(task_data)
            else:
                board['todo'].append(task_data)

        from projects.serializers import ProjectListSerializer
        projects_data = ProjectListSerializer(
            projects_qs.select_related('owner').prefetch_related('memberships'),
            many=True
        ).data

        return Response({'projects': projects_data, 'board': board})


class ProjectBoardView(APIView):
    """
    GET /api/v1/projects/<project_id>/board/
    Returns tasks grouped by status for kanban.
    """
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request, project_id):
        from projects.models import Project
        try:
            project = Project.objects.select_related('owner').get(pk=project_id)
        except Project.DoesNotExist:
            raise NotFound('Project not found.')

        _check_project_visibility(request.user, project)

        tasks = Task.objects.filter(
            module__project=project
        ).select_related('assignee', 'module').order_by('created_at')

        board = {
            'todo': [],
            'in_progress': [],
            'blocked': [],
            'done': [],
        }

        serializer = TaskSerializer(tasks, many=True)
        for task_data in serializer.data:
            s = task_data.get('status', 'todo')
            if s in board:
                board[s].append(task_data)
            else:
                board['todo'].append(task_data)

        return Response(board)
