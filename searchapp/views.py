"""
Search app: global search across projects, work items, employees, and departments.
GET /api/v1/search/?q=<term>&type=<entity_type>
"""
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rbac.permissions import IsActiveUser
from rbac.models import get_user_role, Role


class GlobalSearchView(APIView):
    """
    GET /api/v1/search/?q=<query>&type=<projects|workitems|employees|departments>
    Returns mixed results grouped by entity type, max 10 per type.
    Respects project visibility rules for work items.
    """
    permission_classes = [IsAuthenticated, IsActiveUser]

    def get(self, request):
        q = request.query_params.get('q', '').strip()
        if not q or len(q) < 2:
            return Response({'detail': 'Query must be at least 2 characters.', 'results': {}})

        entity_type = request.query_params.get('type', '')
        role = get_user_role(request.user)
        results = {}

        # Determine accessible project IDs for scoping work items
        from projects.models import Project
        if role in (Role.SUPER_ADMIN, Role.ADMIN, Role.PROJECT_MANAGER):
            accessible_project_ids = None  # all
        else:
            from people.models import EmployeeProfile
            try:
                profile = EmployeeProfile.objects.get(user=request.user)
                accessible_project_ids = list(
                    Project.objects.filter(memberships__employee=profile).values_list('id', flat=True)
                ) + list(Project.objects.filter(owner=profile).values_list('id', flat=True))
            except EmployeeProfile.DoesNotExist:
                accessible_project_ids = []

        if not entity_type or entity_type == 'projects':
            qs = Project.objects.filter(name__icontains=q) | Project.objects.filter(code__icontains=q)
            if accessible_project_ids is not None:
                qs = qs.filter(id__in=accessible_project_ids)
            results['projects'] = [
                {'id': str(p.id), 'name': p.name, 'code': p.code, 'status': p.status, 'type': 'project'}
                for p in qs.distinct()[:10]
            ]

        if not entity_type or entity_type == 'workitems':
            from workitems.models import WorkItem
            qs = WorkItem.objects.filter(title__icontains=q).select_related('project')
            if accessible_project_ids is not None:
                qs = qs.filter(project_id__in=accessible_project_ids)
            results['workitems'] = [
                {'id': str(i.id), 'title': i.title, 'type': i.type, 'status': i.status, 'project': i.project.name, 'entity': 'workitem'}
                for i in qs[:10]
            ]

        if not entity_type or entity_type == 'employees':
            from people.models import EmployeeProfile
            qs = (
                EmployeeProfile.objects.filter(full_name__icontains=q) |
                EmployeeProfile.objects.filter(work_email__icontains=q) |
                EmployeeProfile.objects.filter(job_title__icontains=q)
            ).filter(employment_status='active')
            results['employees'] = [
                {'id': str(e.id), 'full_name': e.full_name, 'job_title': e.job_title, 'work_email': e.work_email, 'entity': 'employee'}
                for e in qs.distinct()[:10]
            ]

        if not entity_type or entity_type == 'departments':
            from org.models import Department
            qs = Department.objects.filter(name__icontains=q, is_archived=False)
            results['departments'] = [
                {'id': str(d.id), 'name': d.name, 'entity': 'department'}
                for d in qs[:10]
            ]

        total = sum(len(v) for v in results.values())
        return Response({'query': q, 'total': total, 'results': results})
