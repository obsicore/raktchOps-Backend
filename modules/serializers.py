"""Serializers for the modules app."""

from rest_framework import serializers
from accounts.models import User
from .models import Module


class ModuleSerializer(serializers.ModelSerializer):
    progress = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()
    task_count = serializers.SerializerMethodField()
    done_task_count = serializers.SerializerMethodField()
    created_by_email = serializers.SerializerMethodField()
    assignee_name = serializers.SerializerMethodField()
    assignee_email = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = [
            'id', 'project', 'name', 'description', 'status', 'priority',
            'start_date', 'deadline', 'progress', 'is_overdue',
            'task_count', 'done_task_count',
            'assignee', 'assignee_name', 'assignee_email',
            'created_by', 'created_by_email', 'updated_by',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'updated_by', 'created_at', 'updated_at']
        validators = []

    def get_progress(self, obj):
        return obj.progress

    def get_is_overdue(self, obj):
        return obj.is_overdue

    def get_task_count(self, obj):
        return obj.tasks.count()

    def get_done_task_count(self, obj):
        return obj.tasks.filter(status='done').count()

    def get_created_by_email(self, obj):
        if obj.created_by:
            return obj.created_by.email
        return None

    def get_assignee_name(self, obj):
        if not obj.assignee:
            return None
        try:
            return obj.assignee.employee_profile.full_name
        except Exception:
            return obj.assignee.email

    def get_assignee_email(self, obj):
        if obj.assignee:
            return obj.assignee.email
        return None

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Module name cannot be blank.')
        return value

    def validate_assignee(self, value):
        """Validate that assignee is a project team member (if set)."""
        if not value:
            return value

        project = self.context.get('project')
        if project is None and self.instance:
            project = self.instance.project

        if project:
            valid_user_ids = set()
            try:
                valid_user_ids.add(project.owner.user_id)
            except Exception:
                pass
            for membership in project.memberships.select_related('employee__user').all():
                try:
                    valid_user_ids.add(membership.employee.user_id)
                except Exception:
                    pass

            if value.id not in valid_user_ids:
                raise serializers.ValidationError(
                    f"User '{value.email}' is not a member of this project's team."
                )

        return value

    def validate(self, data):
        project = data.get('project', getattr(self.instance, 'project', None))
        name = data.get('name', getattr(self.instance, 'name', None))

        if project and name:
            qs = Module.objects.filter(project=project, name=name)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {'name': [f"A module named '{name}' already exists in this project."]}
                )

        start = data.get('start_date', getattr(self.instance, 'start_date', None))
        deadline = data.get('deadline', getattr(self.instance, 'deadline', None))
        if start and deadline and deadline < start:
            raise serializers.ValidationError(
                {'deadline': ['Deadline cannot be before the start date.']}
            )

        return data
