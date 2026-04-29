"""
Views for the people app: employee directory and profile management.
All endpoints under /api/v1/people/.
"""

import logging
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, filters
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rbac.permissions import IsActiveUser, IsAdmin, IsAdminOrProjectManager
from rbac.models import get_user_role, Role

from .models import EmployeeProfile, EmploymentStatus
from .serializers import (
    EmployeeListSerializer,
    EmployeeDetailSerializer,
    EmployeeCreateSerializer,
)

logger = logging.getLogger(__name__)


class EmployeePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# ---------------------------------------------------------------------------
# Employee directory (list + create)
# ---------------------------------------------------------------------------

class EmployeeListCreateView(APIView):
    """
    GET  /api/v1/people/employees/   — paginated directory, searchable/filterable
    POST /api/v1/people/employees/   — admin only, create profile for active user
    """
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        qs = EmployeeProfile.objects.select_related(
            'user', 'department', 'team', 'manager'
        )

        # Filter by employment status (default: active only unless specified)
        emp_status = request.query_params.get('employment_status')
        if emp_status:
            qs = qs.filter(employment_status=emp_status)
        else:
            qs = qs.filter(employment_status=EmploymentStatus.ACTIVE)

        # Filter by department
        dept = request.query_params.get('department')
        if dept:
            qs = qs.filter(department_id=dept)

        # Filter by team
        team = request.query_params.get('team')
        if team:
            qs = qs.filter(team_id=team)

        # Search by name or email
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                full_name__icontains=search
            ) | qs.filter(
                work_email__icontains=search
            ) | qs.filter(
                job_title__icontains=search
            )
            # Re-apply queryset filters — union can widen results, re-filter
            qs = EmployeeProfile.objects.select_related(
                'user', 'department', 'team', 'manager'
            ).filter(
                full_name__icontains=search
            ) | EmployeeProfile.objects.select_related(
                'user', 'department', 'team', 'manager'
            ).filter(
                work_email__icontains=search
            ) | EmployeeProfile.objects.select_related(
                'user', 'department', 'team', 'manager'
            ).filter(
                job_title__icontains=search
            )
            # Limit to active by default when no explicit status filter
            if not emp_status:
                qs = qs.filter(employment_status=EmploymentStatus.ACTIVE)

        # Ordering
        ordering = request.query_params.get('ordering', 'full_name')
        allowed_orderings = ['full_name', '-full_name', 'created_at', '-created_at', 'job_title']
        if ordering in allowed_orderings:
            qs = qs.order_by(ordering)

        paginator = EmployeePagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = EmployeeListSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        # Only admins can create employee profiles
        if get_user_role(request.user) not in (Role.SUPER_ADMIN, Role.ADMIN):
            raise PermissionDenied('Admin role required to create employee profiles.')

        serializer = EmployeeCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'detail': 'Validation failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        profile = serializer.save()
        logger.info('Admin %s created employee profile for user %s', request.user.email, profile.user.email)
        return Response(
            EmployeeDetailSerializer(profile, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Employee detail (get / update)
# ---------------------------------------------------------------------------

class EmployeeDetailView(APIView):
    """
    GET   /api/v1/people/employees/<pk>/   — any active user
    PATCH /api/v1/people/employees/<pk>/   — self (limited fields) or admin/PM (all fields)
    """
    permission_classes = [IsAuthenticated, IsActiveUser]

    def _get_profile(self, pk):
        try:
            return EmployeeProfile.objects.select_related(
                'user', 'department', 'team', 'manager'
            ).get(pk=pk)
        except EmployeeProfile.DoesNotExist:
            raise NotFound('Employee profile not found.')

    def get(self, request, pk):
        profile = self._get_profile(pk)
        serializer = EmployeeDetailSerializer(profile, context={'request': request})
        return Response(serializer.data)

    def patch(self, request, pk):
        profile = self._get_profile(pk)
        user_role = get_user_role(request.user)
        is_self = profile.user == request.user

        if not is_self and user_role not in (Role.SUPER_ADMIN, Role.ADMIN, Role.PROJECT_MANAGER):
            raise PermissionDenied('You can only edit your own profile unless you are an admin or project manager.')

        # Staff editing their own profile: restrict to safe personal fields
        if is_self and user_role == Role.STAFF:
            allowed_fields = {'full_name', 'job_title', 'phone'}
            disallowed = set(request.data.keys()) - allowed_fields
            if disallowed:
                raise PermissionDenied(
                    f'You cannot edit these fields: {", ".join(sorted(disallowed))}'
                )

        serializer = EmployeeDetailSerializer(
            profile, data=request.data, partial=True, context={'request': request}
        )
        if not serializer.is_valid():
            return Response(
                {'detail': 'Validation failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer.save()
        logger.info(
            '%s updated employee profile %s',
            request.user.email,
            profile.work_email,
        )
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# My profile shortcut
# ---------------------------------------------------------------------------

class MyProfileView(APIView):
    """GET /api/v1/people/me/ — returns own employee profile."""
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        try:
            profile = EmployeeProfile.objects.select_related(
                'user', 'department', 'team', 'manager'
            ).get(user=request.user)
        except EmployeeProfile.DoesNotExist:
            raise NotFound('No employee profile found for your account. Contact an administrator.')
        serializer = EmployeeDetailSerializer(profile, context={'request': request})
        return Response(serializer.data)


class EmployeeContributionsView(APIView):
    """
    GET /api/v1/people/employees/<uuid:pk>/contributions/
    Returns project memberships, assigned tasks, assigned modules, and summary
    stats for a given employee. Visible to all logged-in active users.
    """
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request, pk):
        try:
            profile = EmployeeProfile.objects.select_related('user').get(pk=pk)
        except EmployeeProfile.DoesNotExist:
            raise NotFound('Employee profile not found.')

        from projects.models import Project, ProjectMember
        from modules.models import Module
        from tasks.models import Task

        user = profile.user

        # Projects where employee is a member
        member_pids = set(
            ProjectMember.objects.filter(employee=profile).values_list('project_id', flat=True)
        )
        # Projects where employee is the owner / leader
        owned_pids = set(
            Project.objects.filter(owner=profile).values_list('id', flat=True)
        )
        all_pids = member_pids | owned_pids

        projects_qs = Project.objects.filter(id__in=all_pids).select_related('owner')

        projects_data = []
        for p in projects_qs:
            total = Task.objects.filter(module__project=p).count()
            done = Task.objects.filter(module__project=p, status='done').count()
            progress = round((done / total) * 100) if total > 0 else 0
            projects_data.append({
                'id': str(p.id),
                'name': p.name,
                'status': p.status,
                'progress': progress,
                'is_leader': p.owner == profile,
                'leader_name': p.owner.full_name if p.owner else None,
                'due_date': p.due_date.isoformat() if p.due_date else None,
            })

        # Tasks assigned to this user
        tasks_qs = Task.objects.filter(
            assignee=user
        ).select_related('module__project').order_by('-created_at')[:50]

        tasks_data = []
        for t in tasks_qs:
            tasks_data.append({
                'id': t.id,
                'title': t.title,
                'status': t.status,
                'priority': t.priority,
                'due_date': t.due_date.isoformat() if t.due_date else None,
                'module_name': t.module.name,
                'project_name': t.module.project.name,
                'project_id': str(t.module.project_id),
                'is_overdue': t.is_overdue,
            })

        # Modules assigned to this user
        modules_qs = Module.objects.filter(
            assignee=user
        ).select_related('project').prefetch_related('tasks').order_by('-created_at')[:30]

        modules_data = []
        for m in modules_qs:
            task_count = m.tasks.count()
            done_count = m.tasks.filter(status='done').count()
            modules_data.append({
                'id': m.id,
                'name': m.name,
                'status': m.status,
                'project_name': m.project.name,
                'project_id': str(m.project_id),
                'task_count': task_count,
                'done_task_count': done_count,
                'deadline': m.deadline.isoformat() if m.deadline else None,
            })

        stats = {
            'total_projects': len(all_pids),
            'led_projects': len(owned_pids),
            'total_tasks_assigned': Task.objects.filter(assignee=user).count(),
            'completed_tasks': Task.objects.filter(assignee=user, status='done').count(),
            'assigned_modules': Module.objects.filter(assignee=user).count(),
        }

        return Response({
            'stats': stats,
            'projects': projects_data,
            'tasks': tasks_data,
            'modules': modules_data,
        })
