"""
Serializers for the projects app.
Repository URL validation enforces GitHub-only per REPOSITORY_ALLOWED_HOSTS setting.
"""

from urllib.parse import urlparse

from django.conf import settings
from rest_framework import serializers

from people.models import EmployeeProfile
from .models import Project, ProjectMember, ProjectStatus, ProjectHealth, ProjectType


def _validate_repository_url(url: str) -> str:
    """
    Validate that the URL:
    1. Uses HTTPS (if REPOSITORY_REQUIRE_HTTPS is True)
    2. Is from one of the REPOSITORY_ALLOWED_HOSTS (default: github.com)
    """
    if not url:
        return url

    parsed = urlparse(url)

    require_https = getattr(settings, 'REPOSITORY_REQUIRE_HTTPS', True)
    if require_https and parsed.scheme != 'https':
        raise serializers.ValidationError(
            'Repository URL must use HTTPS.'
        )

    allowed_hosts = getattr(settings, 'REPOSITORY_ALLOWED_HOSTS', ['github.com'])
    if parsed.netloc not in allowed_hosts:
        raise serializers.ValidationError(
            f'Repository URL must be from one of: {", ".join(allowed_hosts)}.'
        )

    return url


# ---------------------------------------------------------------------------
# Project serializers
# ---------------------------------------------------------------------------

class ProjectListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for project list views."""

    leader = serializers.PrimaryKeyRelatedField(
        source='owner',
        queryset=EmployeeProfile.objects.all(),
    )
    leader_name = serializers.CharField(source='owner.full_name', read_only=True)
    leader_user_id = serializers.UUIDField(source='owner.user_id', read_only=True)
    member_count = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            'id',
            'name',
            'code',
            'type',
            'leader',
            'leader_name',
            'leader_user_id',
            'status',
            'health',
            'start_date',
            'due_date',
            'repository_url',
            'member_count',
            'progress',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_member_count(self, obj):
        return obj.memberships.count()

    def get_progress(self, obj):
        try:
            from tasks.models import Task
            total = Task.objects.filter(module__project=obj).count()
            if total == 0:
                return 0
            done = Task.objects.filter(module__project=obj, status='done').count()
            return round((done / total) * 100)
        except Exception:
            return 0


class ProjectDetailSerializer(serializers.ModelSerializer):
    """Full project serializer for detail and create/update."""

    leader = serializers.PrimaryKeyRelatedField(
        source='owner',
        queryset=EmployeeProfile.objects.all(),
    )
    leader_name = serializers.CharField(source='owner.full_name', read_only=True)
    leader_user_id = serializers.UUIDField(source='owner.user_id', read_only=True)
    member_count = serializers.SerializerMethodField()
    members = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    module_count = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            'id',
            'name',
            'code',
            'description',
            'type',
            'leader',
            'leader_name',
            'leader_user_id',
            'status',
            'health',
            'start_date',
            'due_date',
            'repository_url',
            'member_count',
            'members',
            'progress',
            'module_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_member_count(self, obj):
        return obj.memberships.count()

    def get_members(self, obj):
        return list(
            obj.memberships.select_related('employee').values_list('employee_id', flat=True)
        )

    def get_progress(self, obj):
        try:
            from tasks.models import Task
            total = Task.objects.filter(module__project=obj).count()
            if total == 0:
                return 0
            done = Task.objects.filter(module__project=obj, status='done').count()
            return round((done / total) * 100)
        except Exception:
            return 0

    def get_module_count(self, obj):
        try:
            return obj.modules.count()
        except Exception:
            return 0

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError('Project name cannot be blank.')
        return value.strip()

    def validate_repository_url(self, value):
        return _validate_repository_url(value)

    def validate_due_date(self, value):
        start_date = self.initial_data.get('start_date') or (
            self.instance.start_date if self.instance else None
        )
        if value and start_date:
            from datetime import date
            if isinstance(start_date, str):
                from datetime import datetime
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            if value < start_date:
                raise serializers.ValidationError(
                    'Due date cannot be before the start date.'
                )
        return value

    def validate_status(self, value):
        valid = [s[0] for s in ProjectStatus.choices]
        if value not in valid:
            raise serializers.ValidationError(f'Invalid status. Choose from: {", ".join(valid)}')
        return value

    def validate_health(self, value):
        valid = [h[0] for h in ProjectHealth.choices]
        if value not in valid:
            raise serializers.ValidationError(f'Invalid health. Choose from: {", ".join(valid)}')
        return value


# ---------------------------------------------------------------------------
# Project member serializers
# ---------------------------------------------------------------------------

class ProjectMemberSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    employee_email = serializers.CharField(source='employee.work_email', read_only=True)
    employee_user_id = serializers.UUIDField(source='employee.user_id', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)

    class Meta:
        model = ProjectMember
        fields = [
            'id',
            'project',
            'project_name',
            'employee',
            'employee_name',
            'employee_email',
            'employee_user_id',
            'joined_at',
        ]
        read_only_fields = ['id', 'joined_at']
        # Suppress auto-generated UniqueTogetherValidator so errors surface
        # under the named 'employee' key instead of non_field_errors.
        validators = []

    def validate(self, data):
        project = data.get('project', getattr(self.instance, 'project', None))
        employee = data.get('employee', getattr(self.instance, 'employee', None))

        if project and project.status == 'archived':
            raise serializers.ValidationError({'project': 'Cannot add members to an archived project.'})

        if project and employee:
            qs = ProjectMember.objects.filter(project=project, employee=employee)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {'employee': 'This employee is already a member of this project.'}
                )
        return data
