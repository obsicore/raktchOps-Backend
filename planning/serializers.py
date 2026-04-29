"""Serializers for the planning app (Sprint, Milestone)."""
from rest_framework import serializers
from .models import Sprint, Milestone, SprintStatus


class SprintSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    progress_summary = serializers.SerializerMethodField()

    class Meta:
        model = Sprint
        fields = [
            'id', 'project', 'project_name', 'name', 'status',
            'start_date', 'end_date', 'capacity', 'goal',
            'progress_summary', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_progress_summary(self, obj):
        return obj.progress_summary

    def validate(self, data):
        start = data.get('start_date', getattr(self.instance, 'start_date', None))
        end = data.get('end_date', getattr(self.instance, 'end_date', None))
        if start and end and end < start:
            raise serializers.ValidationError({'end_date': 'End date cannot be before start date.'})

        # Only one sprint can be active per project
        new_status = data.get('status', getattr(self.instance, 'status', None))
        project = data.get('project', getattr(self.instance, 'project', None))
        if new_status == SprintStatus.ACTIVE and project:
            qs = Sprint.objects.filter(project=project, status=SprintStatus.ACTIVE)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({'status': 'Another sprint is already active for this project.'})
        return data


class MilestoneSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)

    class Meta:
        model = Milestone
        fields = [
            'id', 'project', 'project_name', 'name', 'description',
            'target_date', 'status', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError('Milestone name cannot be blank.')
        return value.strip()
