"""Views for the planning app (Sprint, Milestone)."""
import logging
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rbac.permissions import IsActiveUser
from rbac.models import get_user_role, Role
from .models import Sprint, Milestone
from .serializers import SprintSerializer, MilestoneSerializer

logger = logging.getLogger(__name__)


class PlanningPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


def _require_pm_or_admin(user):
    if get_user_role(user) not in (Role.SUPER_ADMIN, Role.ADMIN, Role.PROJECT_MANAGER):
        raise PermissionDenied('Admin or PM role required.')


# ---------------------------------------------------------------------------
# Sprints
# ---------------------------------------------------------------------------

class SprintListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        qs = Sprint.objects.select_related('project')
        project_id = request.query_params.get('project')
        if project_id:
            qs = qs.filter(project_id=project_id)
        sprint_status = request.query_params.get('status')
        if sprint_status:
            qs = qs.filter(status=sprint_status)
        paginator = PlanningPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(SprintSerializer(page, many=True).data)

    def post(self, request):
        _require_pm_or_admin(request.user)
        serializer = SprintSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'detail': 'Validation failed.', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        sprint = serializer.save()
        logger.info('%s created sprint %s', request.user.email, sprint.name)
        return Response(SprintSerializer(sprint).data, status=status.HTTP_201_CREATED)


class SprintDetailView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser]

    def _get(self, pk):
        try:
            return Sprint.objects.select_related('project').get(pk=pk)
        except Sprint.DoesNotExist:
            raise NotFound('Sprint not found.')

    def get(self, request, pk):
        return Response(SprintSerializer(self._get(pk)).data)

    def patch(self, request, pk):
        _require_pm_or_admin(request.user)
        sprint = self._get(pk)
        serializer = SprintSerializer(sprint, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({'detail': 'Validation failed.', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        sprint = serializer.save()
        logger.info('%s updated sprint %s', request.user.email, sprint.name)
        return Response(SprintSerializer(sprint).data)

    def delete(self, request, pk):
        if get_user_role(request.user) not in (Role.SUPER_ADMIN, Role.ADMIN):
            raise PermissionDenied('Admin role required to delete sprints.')
        sprint = self._get(pk)
        name = sprint.name
        sprint.delete()
        logger.info('%s deleted sprint %s', request.user.email, name)
        return Response({'detail': f'Sprint "{name}" deleted.'})


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------

class MilestoneListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        qs = Milestone.objects.select_related('project')
        project_id = request.query_params.get('project')
        if project_id:
            qs = qs.filter(project_id=project_id)
        ms_status = request.query_params.get('status')
        if ms_status:
            qs = qs.filter(status=ms_status)
        paginator = PlanningPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(MilestoneSerializer(page, many=True).data)

    def post(self, request):
        _require_pm_or_admin(request.user)
        serializer = MilestoneSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'detail': 'Validation failed.', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        milestone = serializer.save()
        logger.info('%s created milestone %s', request.user.email, milestone.name)
        return Response(MilestoneSerializer(milestone).data, status=status.HTTP_201_CREATED)


class MilestoneDetailView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser]

    def _get(self, pk):
        try:
            return Milestone.objects.select_related('project').get(pk=pk)
        except Milestone.DoesNotExist:
            raise NotFound('Milestone not found.')

    def get(self, request, pk):
        return Response(MilestoneSerializer(self._get(pk)).data)

    def patch(self, request, pk):
        _require_pm_or_admin(request.user)
        ms = self._get(pk)
        serializer = MilestoneSerializer(ms, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({'detail': 'Validation failed.', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        ms = serializer.save()
        return Response(MilestoneSerializer(ms).data)

    def delete(self, request, pk):
        _require_pm_or_admin(request.user)
        ms = self._get(pk)
        name = ms.name
        ms.delete()
        return Response({'detail': f'Milestone "{name}" deleted.'})
