"""Views for the boards app."""
import logging
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rbac.permissions import IsActiveUser
from rbac.models import get_user_role, Role
from projects.models import Project
from .models import KanbanBoard
from .serializers import KanbanBoardSerializer

logger = logging.getLogger(__name__)


def _get_project(pk):
    try:
        return Project.objects.get(pk=pk)
    except Project.DoesNotExist:
        raise NotFound('Project not found.')


class KanbanBoardDetailView(APIView):
    """
    GET  /api/v1/boards/<project_pk>/   — get or auto-create board for project
    PATCH /api/v1/boards/<project_pk>/  — update board config (admin/PM)
    """
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request, project_pk):
        project = _get_project(project_pk)
        board, _ = KanbanBoard.objects.get_or_create(project=project, defaults={'name': f'{project.name} Board'})
        return Response(KanbanBoardSerializer(board).data)

    def patch(self, request, project_pk):
        role = get_user_role(request.user)
        if role not in (Role.SUPER_ADMIN, Role.ADMIN, Role.PROJECT_MANAGER):
            raise PermissionDenied('Admin or PM required to configure boards.')
        project = _get_project(project_pk)
        board, _ = KanbanBoard.objects.get_or_create(project=project, defaults={'name': f'{project.name} Board'})
        serializer = KanbanBoardSerializer(board, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({'detail': 'Validation failed.', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        board = serializer.save()
        logger.info('%s updated board config for project %s', request.user.email, project.name)
        return Response(KanbanBoardSerializer(board).data)
