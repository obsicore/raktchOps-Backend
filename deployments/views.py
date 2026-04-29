"""Views for the deployments app."""
import logging
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rbac.permissions import IsActiveUser
from rbac.models import get_user_role, Role
from .models import Environment, Release, Deployment, ReleaseStatus
from .serializers import EnvironmentSerializer, ReleaseSerializer, DeploymentSerializer

logger = logging.getLogger(__name__)


class DeployPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


def _require_pm_or_admin(user):
    if get_user_role(user) not in (Role.SUPER_ADMIN, Role.ADMIN, Role.PROJECT_MANAGER):
        raise PermissionDenied('Admin or PM role required.')


# ---------------------------------------------------------------------------
# Environments
# ---------------------------------------------------------------------------

class EnvironmentListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        qs = Environment.objects.select_related('project')
        project_id = request.query_params.get('project')
        if project_id:
            qs = qs.filter(project_id=project_id)
        paginator = DeployPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(EnvironmentSerializer(page, many=True).data)

    def post(self, request):
        _require_pm_or_admin(request.user)
        serializer = EnvironmentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'detail': 'Validation failed.', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        env = serializer.save()
        logger.info('%s created environment %s', request.user.email, env.name)
        return Response(EnvironmentSerializer(env).data, status=status.HTTP_201_CREATED)


class EnvironmentDetailView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser]

    def _get(self, pk):
        try:
            return Environment.objects.select_related('project').get(pk=pk)
        except Environment.DoesNotExist:
            raise NotFound('Environment not found.')

    def get(self, request, pk):
        return Response(EnvironmentSerializer(self._get(pk)).data)

    def patch(self, request, pk):
        _require_pm_or_admin(request.user)
        env = self._get(pk)
        serializer = EnvironmentSerializer(env, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({'detail': 'Validation failed.', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        return Response(EnvironmentSerializer(serializer.save()).data)

    def delete(self, request, pk):
        if get_user_role(request.user) not in (Role.SUPER_ADMIN, Role.ADMIN):
            raise PermissionDenied('Admin role required to delete environments.')
        env = self._get(pk)
        name = env.name
        env.delete()
        return Response({'detail': f'Environment "{name}" deleted.'})


# ---------------------------------------------------------------------------
# Releases
# ---------------------------------------------------------------------------

class ReleaseListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        qs = Release.objects.select_related('project', 'created_by')
        project_id = request.query_params.get('project')
        if project_id:
            qs = qs.filter(project_id=project_id)
        rel_status = request.query_params.get('status')
        if rel_status:
            qs = qs.filter(status=rel_status)
        paginator = DeployPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(ReleaseSerializer(page, many=True).data)

    def post(self, request):
        _require_pm_or_admin(request.user)
        serializer = ReleaseSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'detail': 'Validation failed.', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        release = serializer.save()
        logger.info('%s created release %s', request.user.email, release.version)
        return Response(ReleaseSerializer(release).data, status=status.HTTP_201_CREATED)


class ReleaseDetailView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser]

    def _get(self, pk):
        try:
            return Release.objects.select_related('project', 'created_by').get(pk=pk)
        except Release.DoesNotExist:
            raise NotFound('Release not found.')

    def get(self, request, pk):
        return Response(ReleaseSerializer(self._get(pk)).data)

    def patch(self, request, pk):
        _require_pm_or_admin(request.user)
        release = self._get(pk)
        if release.status == ReleaseStatus.RELEASED:
            return Response({'detail': 'Released versions cannot be modified.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = ReleaseSerializer(release, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({'detail': 'Validation failed.', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ReleaseSerializer(serializer.save()).data)


# ---------------------------------------------------------------------------
# Deployments
# ---------------------------------------------------------------------------

class DeploymentListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        qs = Deployment.objects.select_related('release', 'environment', 'deployed_by')
        project_id = request.query_params.get('project')
        if project_id:
            qs = qs.filter(release__project_id=project_id)
        env_id = request.query_params.get('environment')
        if env_id:
            qs = qs.filter(environment_id=env_id)
        dep_status = request.query_params.get('status')
        if dep_status:
            qs = qs.filter(status=dep_status)
        paginator = DeployPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(DeploymentSerializer(page, many=True).data)

    def post(self, request):
        _require_pm_or_admin(request.user)
        serializer = DeploymentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'detail': 'Validation failed.', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        deployment = serializer.save()
        logger.info('%s created deployment for release %s to %s', request.user.email, deployment.release.version, deployment.environment.name)
        return Response(DeploymentSerializer(deployment).data, status=status.HTTP_201_CREATED)


class DeploymentDetailView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser]

    def _get(self, pk):
        try:
            return Deployment.objects.select_related('release', 'environment', 'deployed_by').get(pk=pk)
        except Deployment.DoesNotExist:
            raise NotFound('Deployment not found.')

    def get(self, request, pk):
        return Response(DeploymentSerializer(self._get(pk)).data)

    def patch(self, request, pk):
        _require_pm_or_admin(request.user)
        deployment = self._get(pk)
        serializer = DeploymentSerializer(deployment, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({'detail': 'Validation failed.', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DeploymentSerializer(serializer.save()).data)
