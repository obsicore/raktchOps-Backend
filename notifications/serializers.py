"""Serializers for the notifications app."""

from rest_framework import serializers

from projects.models import Project

from .models import Notification, NotificationType


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'type', 'title', 'body', 'link', 'is_read', 'created_at', 'read_at']
        read_only_fields = ['id', 'type', 'title', 'body', 'link', 'created_at', 'read_at']


class NotificationCreateSerializer(serializers.Serializer):
    """
    Manual notification create payload.
    Elevated roles can fan out notices to related recipients.
    """

    type = serializers.ChoiceField(choices=NotificationType.choices, default=NotificationType.GENERAL)
    title = serializers.CharField(max_length=200)
    body = serializers.CharField(required=False, allow_blank=True, default='')
    link = serializers.CharField(required=False, allow_blank=True, max_length=300, default='')
    recipient_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
    )
    project_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        project_id = attrs.get('project_id')
        if project_id:
            try:
                attrs['project'] = Project.objects.select_related('owner').get(pk=project_id)
            except Project.DoesNotExist:
                raise serializers.ValidationError({'project_id': ['Project not found.']})
        return attrs
