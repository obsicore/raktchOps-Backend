"""Serializers for the boards app."""
from rest_framework import serializers
from .models import KanbanBoard


class KanbanBoardSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)

    class Meta:
        model = KanbanBoard
        fields = ['id', 'project', 'project_name', 'name', 'wip_limits', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_wip_limits(self, value):
        allowed_statuses = {'backlog', 'todo', 'in_progress', 'in_review', 'done', 'cancelled'}
        for key, val in value.items():
            if key not in allowed_statuses:
                raise serializers.ValidationError(f'Invalid status column: {key}')
            if not isinstance(val, int) or val < 1:
                raise serializers.ValidationError(f'WIP limit for {key} must be a positive integer.')
        return value
