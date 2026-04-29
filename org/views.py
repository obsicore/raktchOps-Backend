"""
Views for the org app: departments, teams, and team memberships.
All endpoints under /api/v1/org/.
"""

import logging
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rbac.permissions import IsActiveUser, IsAdmin
from rbac.models import get_user_role, Role

from .models import Department, Team, TeamMembership
from .serializers import DepartmentSerializer, TeamSerializer, TeamMembershipSerializer

logger = logging.getLogger(__name__)


class OrgPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


def _require_admin(user):
    if get_user_role(user) not in (Role.SUPER_ADMIN, Role.ADMIN):
        raise PermissionDenied('Admin role required for this action.')


# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------

class DepartmentListCreateView(APIView):
    """
    GET  /api/v1/org/departments/   — all active users
    POST /api/v1/org/departments/   — admin only
    """
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        qs = Department.objects.select_related('head').prefetch_related('employees', 'teams')

        # By default exclude archived; pass ?include_archived=true to see all
        include_archived = request.query_params.get('include_archived', 'false').lower() == 'true'
        if not include_archived:
            qs = qs.filter(is_archived=False)

        # Search
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)

        qs = qs.order_by('name')
        paginator = OrgPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = DepartmentSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        _require_admin(request.user)
        serializer = DepartmentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'detail': 'Validation failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        dept = serializer.save()
        logger.info('Admin %s created department %s', request.user.email, dept.name)
        return Response(DepartmentSerializer(dept).data, status=status.HTTP_201_CREATED)


class DepartmentDetailView(APIView):
    """
    GET    /api/v1/org/departments/<pk>/
    PATCH  /api/v1/org/departments/<pk>/  — admin only
    DELETE /api/v1/org/departments/<pk>/  — admin only (archive, not delete)
    """
    permission_classes = [IsAuthenticated, IsActiveUser]

    def _get_dept(self, pk):
        try:
            return Department.objects.select_related('head').get(pk=pk)
        except Department.DoesNotExist:
            raise NotFound('Department not found.')

    def get(self, request, pk):
        dept = self._get_dept(pk)
        return Response(DepartmentSerializer(dept).data)

    def patch(self, request, pk):
        _require_admin(request.user)
        dept = self._get_dept(pk)
        serializer = DepartmentSerializer(dept, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(
                {'detail': 'Validation failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        dept = serializer.save()
        logger.info('Admin %s updated department %s', request.user.email, dept.name)
        return Response(DepartmentSerializer(dept).data)

    def delete(self, request, pk):
        """Archive instead of delete — preserves historical references."""
        _require_admin(request.user)
        dept = self._get_dept(pk)
        if dept.is_archived:
            return Response(
                {'detail': 'Department is already archived.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        dept.is_archived = True
        dept.save(update_fields=['is_archived'])
        logger.info('Admin %s archived department %s', request.user.email, dept.name)
        return Response({'detail': f'Department "{dept.name}" has been archived.'})


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------

class TeamListCreateView(APIView):
    """
    GET  /api/v1/org/teams/   — all active users
    POST /api/v1/org/teams/   — admin only
    """
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        qs = Team.objects.select_related('department', 'team_lead').prefetch_related('memberships')

        include_archived = request.query_params.get('include_archived', 'false').lower() == 'true'
        if not include_archived:
            qs = qs.filter(is_archived=False)

        dept = request.query_params.get('department')
        if dept:
            qs = qs.filter(department_id=dept)

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)

        qs = qs.order_by('name')
        paginator = OrgPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = TeamSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        _require_admin(request.user)
        serializer = TeamSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'detail': 'Validation failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        team = serializer.save()
        logger.info('Admin %s created team %s', request.user.email, team.name)
        return Response(TeamSerializer(team).data, status=status.HTTP_201_CREATED)


class TeamDetailView(APIView):
    """
    GET    /api/v1/org/teams/<pk>/
    PATCH  /api/v1/org/teams/<pk>/  — admin only
    DELETE /api/v1/org/teams/<pk>/  — admin only (archive)
    """
    permission_classes = [IsAuthenticated, IsActiveUser]

    def _get_team(self, pk):
        try:
            return Team.objects.select_related('department', 'team_lead').get(pk=pk)
        except Team.DoesNotExist:
            raise NotFound('Team not found.')

    def get(self, request, pk):
        team = self._get_team(pk)
        return Response(TeamSerializer(team).data)

    def patch(self, request, pk):
        _require_admin(request.user)
        team = self._get_team(pk)
        serializer = TeamSerializer(team, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(
                {'detail': 'Validation failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        team = serializer.save()
        logger.info('Admin %s updated team %s', request.user.email, team.name)
        return Response(TeamSerializer(team).data)

    def delete(self, request, pk):
        """Archive instead of delete."""
        _require_admin(request.user)
        team = self._get_team(pk)
        if team.is_archived:
            return Response(
                {'detail': 'Team is already archived.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        team.is_archived = True
        team.save(update_fields=['is_archived'])
        logger.info('Admin %s archived team %s', request.user.email, team.name)
        return Response({'detail': f'Team "{team.name}" has been archived.'})


# ---------------------------------------------------------------------------
# Team memberships
# ---------------------------------------------------------------------------

class TeamMembershipListView(APIView):
    """
    GET  /api/v1/org/teams/<pk>/members/   — list members
    POST /api/v1/org/teams/<pk>/members/   — admin only, add member
    """
    permission_classes = [IsAuthenticated, IsActiveUser]

    def _get_team(self, pk):
        try:
            return Team.objects.get(pk=pk)
        except Team.DoesNotExist:
            raise NotFound('Team not found.')

    def get(self, request, pk):
        team = self._get_team(pk)
        memberships = TeamMembership.objects.select_related(
            'employee', 'employee__user'
        ).filter(team=team).order_by('employee__full_name')
        serializer = TeamMembershipSerializer(memberships, many=True)
        return Response({'count': memberships.count(), 'results': serializer.data})

    def post(self, request, pk):
        _require_admin(request.user)
        team = self._get_team(pk)
        data = dict(request.data)
        data['team'] = str(team.pk)
        serializer = TeamMembershipSerializer(data=data)
        if not serializer.is_valid():
            return Response(
                {'detail': 'Validation failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        membership = serializer.save()
        logger.info(
            'Admin %s added %s to team %s',
            request.user.email,
            membership.employee.full_name,
            team.name,
        )
        return Response(TeamMembershipSerializer(membership).data, status=status.HTTP_201_CREATED)


class TeamMembershipDetailView(APIView):
    """DELETE /api/v1/org/teams/<pk>/members/<membership_pk>/ — admin only, remove member."""
    permission_classes = [IsAuthenticated, IsActiveUser]

    def delete(self, request, pk, membership_pk):
        _require_admin(request.user)
        try:
            membership = TeamMembership.objects.select_related('employee', 'team').get(
                pk=membership_pk, team_id=pk
            )
        except TeamMembership.DoesNotExist:
            raise NotFound('Membership not found.')

        name = membership.employee.full_name
        team_name = membership.team.name
        membership.delete()
        logger.info('Admin %s removed %s from team %s', request.user.email, name, team_name)
        return Response({'detail': f'{name} removed from {team_name}.'})
