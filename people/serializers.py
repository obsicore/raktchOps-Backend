"""
Serializers for the people app — employee directory and profile management.
"""

from rest_framework import serializers
from .models import EmployeeProfile, EmploymentStatus
from accounts.models import AccountStatus


class EmployeeListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for directory listings."""

    role = serializers.SerializerMethodField()
    department_name = serializers.CharField(
        source='department.name', read_only=True, default=None
    )
    team_name = serializers.CharField(source='team.name', read_only=True, default=None)
    manager_name = serializers.CharField(
        source='manager.full_name', read_only=True, default=None
    )
    user_email = serializers.EmailField(source='user.email', read_only=True)
    account_status = serializers.CharField(
        source='user.account_status', read_only=True
    )

    class Meta:
        model = EmployeeProfile
        fields = [
            'id',
            'user',
            'user_email',
            'full_name',
            'work_email',
            'job_title',
            'department',
            'department_name',
            'team',
            'team_name',
            'manager',
            'manager_name',
            'role',
            'employment_status',
            'account_status',
            'avatar',
            'created_at',
        ]
        read_only_fields = ['id', 'user', 'user_email', 'role', 'account_status', 'created_at']

    def get_role(self, obj):
        return obj.role


class EmployeeDetailSerializer(serializers.ModelSerializer):
    """Full serializer for profile detail and update operations."""

    role = serializers.SerializerMethodField()
    department_name = serializers.CharField(
        source='department.name', read_only=True, default=None
    )
    team_name = serializers.CharField(source='team.name', read_only=True, default=None)
    manager_name = serializers.CharField(
        source='manager.full_name', read_only=True, default=None
    )
    user_email = serializers.EmailField(source='user.email', read_only=True)
    account_status = serializers.CharField(
        source='user.account_status', read_only=True
    )

    class Meta:
        model = EmployeeProfile
        fields = [
            'id',
            'user',
            'user_email',
            'full_name',
            'work_email',
            'job_title',
            'phone',
            'department',
            'department_name',
            'team',
            'team_name',
            'manager',
            'manager_name',
            'role',
            'employment_status',
            'account_status',
            'avatar',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'user', 'user_email', 'role', 'account_status', 'created_at', 'updated_at']

    def get_role(self, obj):
        return obj.role

    def validate_work_email(self, value):
        value = value.lower().strip()
        qs = EmployeeProfile.objects.filter(work_email=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('This work email is already in use.')
        return value

    def validate_manager(self, value):
        if self.instance and value and value.pk == self.instance.pk:
            raise serializers.ValidationError('An employee cannot be their own manager.')
        return value

    def validate_employment_status(self, value):
        if value not in [s[0] for s in EmploymentStatus.choices]:
            raise serializers.ValidationError(f'Invalid employment status: {value}')
        return value


class EmployeeCreateSerializer(serializers.ModelSerializer):
    """
    Admin-only: create an employee profile for an existing active user.
    The user must exist and must not already have a profile.
    """

    class Meta:
        model = EmployeeProfile
        fields = [
            'user',
            'full_name',
            'work_email',
            'job_title',
            'phone',
            'department',
            'team',
            'manager',
            'employment_status',
        ]

    def validate_user(self, value):
        if value.account_status != AccountStatus.ACTIVE:
            raise serializers.ValidationError(
                'Only active users can have an employee profile.'
            )
        if hasattr(value, 'employee_profile'):
            raise serializers.ValidationError(
                'This user already has an employee profile.'
            )
        return value

    def validate_work_email(self, value):
        value = value.lower().strip()
        if EmployeeProfile.objects.filter(work_email=value).exists():
            raise serializers.ValidationError('This work email is already in use.')
        return value

    def validate(self, data):
        manager = data.get('manager')
        user = data.get('user')
        # Cannot self-manage — unlikely at create time but guard it
        if manager and user and hasattr(user, 'employee_profile'):
            if manager.user == user:
                raise serializers.ValidationError({'manager': 'An employee cannot be their own manager.'})
        return data
