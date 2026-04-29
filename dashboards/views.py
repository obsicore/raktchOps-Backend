"""
Dashboards views — aggregate data for each role.
GET /api/v1/dashboards/<role>/ returns role-specific summary data.
"""
import logging
from datetime import date, timedelta
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rbac.permissions import IsActiveUser
from rbac.models import get_user_role, Role

logger = logging.getLogger(__name__)


class AdminDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        if get_user_role(request.user) not in (Role.SUPER_ADMIN, Role.ADMIN, Role.PROJECT_MANAGER):
            raise PermissionDenied('Admin or PM access required.')
        from projects.models import Project
        from people.models import EmployeeProfile
        from workitems.models import WorkItem
        from deployments.models import Deployment

        total_projects = Project.objects.count()
        active_projects = Project.objects.filter(status='active').count()
        total_employees = EmployeeProfile.objects.filter(employment_status='active').count()
        open_items = WorkItem.objects.exclude(status__in=['done', 'cancelled']).count()
        overdue_items = sum(1 for i in WorkItem.objects.exclude(status__in=['done', 'cancelled']).only('due_date', 'status') if i.is_overdue)
        recent_deployments = Deployment.objects.select_related('release', 'environment').order_by('-started_at')[:5]

        from deployments.serializers import DeploymentSerializer
        return Response({
            'summary': {
                'total_projects': total_projects,
                'active_projects': active_projects,
                'total_employees': total_employees,
                'open_work_items': open_items,
                'overdue_work_items': overdue_items,
            },
            'recent_deployments': DeploymentSerializer(recent_deployments, many=True).data,
        })


class PMDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        from people.models import EmployeeProfile
        from projects.models import Project
        from workitems.models import WorkItem
        from planning.models import Sprint, SprintStatus

        try:
            profile = EmployeeProfile.objects.get(user=request.user)
        except EmployeeProfile.DoesNotExist:
            return Response({'summary': {}, 'my_projects': [], 'active_sprints': []})

        my_projects = Project.objects.filter(owner=profile)
        active_sprints = Sprint.objects.filter(project__in=my_projects, status=SprintStatus.ACTIVE).select_related('project')[:5]
        at_risk = my_projects.filter(health='at_risk').count()
        off_track = my_projects.filter(health='off_track').count()

        from projects.serializers import ProjectListSerializer
        from planning.serializers import SprintSerializer
        return Response({
            'summary': {
                'my_projects': my_projects.count(),
                'at_risk_projects': at_risk,
                'off_track_projects': off_track,
            },
            'my_projects': ProjectListSerializer(my_projects[:5], many=True).data,
            'active_sprints': SprintSerializer(active_sprints, many=True).data,
        })


class TeamLeadDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        from people.models import EmployeeProfile
        from workitems.models import WorkItem
        from planning.models import Sprint, SprintStatus

        try:
            profile = EmployeeProfile.objects.get(user=request.user)
        except EmployeeProfile.DoesNotExist:
            return Response({'summary': {}, 'my_items': [], 'team_items': []})

        my_items = WorkItem.objects.filter(assignee=profile).exclude(status__in=['done', 'cancelled'])
        active_sprints = Sprint.objects.filter(
            project__memberships__employee=profile, status=SprintStatus.ACTIVE
        ).distinct()[:3]

        from workitems.serializers import WorkItemListSerializer
        from planning.serializers import SprintSerializer
        return Response({
            'summary': {
                'my_open_items': my_items.count(),
                'blocked_items': my_items.filter(is_blocked=True).count(),
            },
            'my_items': WorkItemListSerializer(my_items[:10], many=True).data,
            'active_sprints': SprintSerializer(active_sprints, many=True).data,
        })


class StaffDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        from people.models import EmployeeProfile
        from workitems.models import WorkItem

        try:
            profile = EmployeeProfile.objects.get(user=request.user)
        except EmployeeProfile.DoesNotExist:
            return Response({'summary': {}, 'my_items': []})

        my_items = WorkItem.objects.filter(assignee=profile).exclude(status__in=['done', 'cancelled']).select_related('project', 'sprint')
        overdue = sum(1 for i in my_items if i.is_overdue)

        from workitems.serializers import WorkItemListSerializer
        return Response({
            'summary': {
                'my_open_items': my_items.count(),
                'overdue_items': overdue,
                'blocked_items': my_items.filter(is_blocked=True).count(),
            },
            'my_items': WorkItemListSerializer(my_items[:15], many=True).data,
        })
