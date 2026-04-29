"""
Serializers for the org app — departments, teams, and team memberships.
"""

from rest_framework import serializers
from .models import Department, Team, TeamMembership


# ---------------------------------------------------------------------------
# Department
# ---------------------------------------------------------------------------

class DepartmentSerializer(serializers.ModelSerializer):
    head_name = serializers.CharField(
        source='head.full_name', read_only=True, default=None
    )
    employee_count = serializers.SerializerMethodField()
    team_count = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = [
            'id',
            'name',
            'description',
            'head',
            'head_name',
            'is_archived',
            'employee_count',
            'team_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_employee_count(self, obj):
        return obj.employees.filter(employment_status='active').count()

    def get_team_count(self, obj):
        return obj.teams.filter(is_archived=False).count()

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Department name cannot be blank.')
        qs = Department.objects.filter(name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('A department with this name already exists.')
        return value


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------

class TeamSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(
        source='department.name', read_only=True, default=None
    )
    team_lead_name = serializers.CharField(
        source='team_lead.full_name', read_only=True, default=None
    )
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = [
            'id',
            'name',
            'description',
            'department',
            'department_name',
            'team_lead',
            'team_lead_name',
            'is_archived',
            'member_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_member_count(self, obj):
        return obj.memberships.count()

    def validate_name(self, value):
        return value.strip() if value else value

    def validate(self, data):
        name = data.get('name', getattr(self.instance, 'name', None))
        department = data.get('department', getattr(self.instance, 'department', None))
        if name and department:
            qs = Team.objects.filter(name__iexact=name, department=department)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {'name': 'A team with this name already exists in this department.'}
                )
        return data


# ---------------------------------------------------------------------------
# Team membership
# ---------------------------------------------------------------------------

class TeamMembershipSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(
        source='employee.full_name', read_only=True
    )
    employee_email = serializers.CharField(
        source='employee.work_email', read_only=True
    )
    team_name = serializers.CharField(source='team.name', read_only=True)

    class Meta:
        model = TeamMembership
        fields = [
            'id',
            'team',
            'team_name',
            'employee',
            'employee_name',
            'employee_email',
            'joined_at',
        ]
        read_only_fields = ['id', 'joined_at']
        # Suppress auto-generated UniqueTogetherValidator so errors surface
        # under the named 'employee' key instead of non_field_errors.
        validators = []

    def validate(self, data):
        team = data.get('team', getattr(self.instance, 'team', None))
        employee = data.get('employee', getattr(self.instance, 'employee', None))

        if team and team.is_archived:
            raise serializers.ValidationError({'team': 'Cannot add members to an archived team.'})

        if team and employee:
            qs = TeamMembership.objects.filter(team=team, employee=employee)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {'employee': 'This employee is already a member of this team.'}
                )
        return data
