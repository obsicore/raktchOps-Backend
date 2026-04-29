"""Serializers for the workitems app."""

from datetime import date
from rest_framework import serializers
from .models import WorkItem, Comment, WorkItemDependency, MoveLog, VALID_TRANSITIONS, WorkItemStatus


class WorkItemListSerializer(serializers.ModelSerializer):
    assignee_name = serializers.CharField(source='assignee.full_name', read_only=True, default=None)
    reporter_name = serializers.CharField(source='reporter.full_name', read_only=True, default=None)
    project_name = serializers.CharField(source='project.name', read_only=True)
    sprint_name = serializers.CharField(source='sprint.name', read_only=True, default=None)
    is_overdue = serializers.BooleanField(read_only=True)
    comment_count = serializers.SerializerMethodField()

    class Meta:
        model = WorkItem
        fields = [
            'id', 'title', 'type', 'status', 'priority',
            'project', 'project_name', 'sprint', 'sprint_name',
            'assignee', 'assignee_name', 'reporter', 'reporter_name',
            'parent', 'due_date', 'progress', 'is_blocked', 'is_overdue',
            'comment_count', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_comment_count(self, obj):
        return obj.comments.count()


class WorkItemDetailSerializer(serializers.ModelSerializer):
    assignee_name = serializers.CharField(source='assignee.full_name', read_only=True, default=None)
    reporter_name = serializers.CharField(source='reporter.full_name', read_only=True, default=None)
    project_name = serializers.CharField(source='project.name', read_only=True)
    sprint_name = serializers.CharField(source='sprint.name', read_only=True, default=None)
    parent_title = serializers.CharField(source='parent.title', read_only=True, default=None)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = WorkItem
        fields = [
            'id', 'title', 'type', 'description', 'status', 'priority',
            'project', 'project_name', 'sprint', 'sprint_name',
            'parent', 'parent_title',
            'assignee', 'assignee_name', 'reporter', 'reporter_name',
            'due_date', 'progress', 'is_blocked', 'is_overdue',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError('Title cannot be blank.')
        return value.strip()

    def validate_progress(self, value):
        if not (0 <= value <= 100):
            raise serializers.ValidationError('Progress must be between 0 and 100.')
        return value

    def validate_due_date(self, value):
        return value  # date validated by model field; business rule: warn but don't block

    def validate(self, data):
        parent = data.get('parent', getattr(self.instance, 'parent', None))
        item_id = self.instance.pk if self.instance else None
        if parent and item_id and parent.pk == item_id:
            raise serializers.ValidationError({'parent': 'A work item cannot be its own parent.'})
        return data


class KanbanMoveSerializer(serializers.Serializer):
    """Validates a Kanban status transition."""
    status = serializers.ChoiceField(choices=WorkItemStatus.choices)

    def validate_status(self, value):
        # Cross-field check happens in view (needs current status)
        return value


class CommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.full_name', read_only=True, default=None)

    class Meta:
        model = Comment
        fields = ['id', 'work_item', 'author', 'author_name', 'body', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_body(self, value):
        if not value.strip():
            raise serializers.ValidationError('Comment body cannot be blank.')
        return value.strip()


class WorkItemDependencySerializer(serializers.ModelSerializer):
    from_title = serializers.CharField(source='from_item.title', read_only=True)
    to_title = serializers.CharField(source='to_item.title', read_only=True)

    class Meta:
        model = WorkItemDependency
        fields = ['id', 'from_item', 'from_title', 'to_item', 'to_title', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate(self, data):
        from_item = data.get('from_item')
        to_item = data.get('to_item')
        if from_item and to_item:
            if from_item.pk == to_item.pk:
                raise serializers.ValidationError({'to_item': 'A work item cannot depend on itself.'})
            if WorkItemDependency.objects.filter(from_item=from_item, to_item=to_item).exists():
                raise serializers.ValidationError({'to_item': 'This dependency already exists.'})
            # Simple cycle check (1-level)
            if WorkItemDependency.objects.filter(from_item=to_item, to_item=from_item).exists():
                raise serializers.ValidationError({'to_item': 'This would create a circular dependency.'})
        return data


class MoveLogSerializer(serializers.ModelSerializer):
    moved_by_email = serializers.CharField(source='moved_by.email', read_only=True, default=None)

    class Meta:
        model = MoveLog
        fields = ['id', 'from_status', 'to_status', 'moved_by', 'moved_by_email', 'moved_at']
        read_only_fields = ['id', 'moved_at']
