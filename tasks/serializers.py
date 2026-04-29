"""Serializers for the tasks app."""

from rest_framework import serializers
from .models import Task


class TaskSerializer(serializers.ModelSerializer):
    is_overdue = serializers.SerializerMethodField()
    assignee_email = serializers.SerializerMethodField()
    assignee_name = serializers.SerializerMethodField()
    module_name = serializers.SerializerMethodField()
    project_id = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            'id', 'module', 'module_name', 'project_id',
            'title', 'description',
            'assignee', 'assignee_email', 'assignee_name',
            'status', 'priority',
            'start_date', 'due_date', 'is_overdue',
            'created_by', 'updated_by',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'updated_by', 'created_at', 'updated_at']

    def get_is_overdue(self, obj):
        return obj.is_overdue

    def get_assignee_email(self, obj):
        if obj.assignee:
            return obj.assignee.email
        return None

    def get_assignee_name(self, obj):
        if not obj.assignee:
            return None
        try:
            return obj.assignee.employee_profile.full_name
        except Exception:
            return obj.assignee.email

    def get_module_name(self, obj):
        return obj.module.name

    def get_project_id(self, obj):
        return str(obj.module.project_id)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Task title cannot be blank.')
        return value

    def validate_assignee(self, value):
        """Validate that assignee is a project team member."""
        if not value:
            return value

        # Get the module from context or from the data being validated
        request = self.context.get('request')
        module = self.context.get('module')

        if module is None:
            # Try to get from data
            module_id = self.initial_data.get('module')
            if module_id:
                try:
                    from modules.models import Module
                    module = Module.objects.select_related('project').get(pk=module_id)
                except Exception:
                    pass

        if module is None and self.instance:
            module = self.instance.module

        if module:
            project = module.project
            # Collect valid user IDs: project owner + members
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
        start = data.get('start_date', getattr(self.instance, 'start_date', None))
        due = data.get('due_date', getattr(self.instance, 'due_date', None))
        if start and due and due < start:
            raise serializers.ValidationError({'due_date': ['Due date cannot be before start date.']})
        return data


class TaskMoveSerializer(serializers.Serializer):
    """For kanban drag-and-drop status moves."""
    status = serializers.ChoiceField(choices=Task.STATUS_CHOICES)
