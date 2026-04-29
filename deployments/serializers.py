"""Serializers for the deployments app."""
from rest_framework import serializers
from .models import Environment, Release, Deployment, ReleaseStatus, DeploymentStatus


class EnvironmentSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)

    class Meta:
        model = Environment
        fields = ['id', 'project', 'project_name', 'name', 'type', 'url', 'is_protected', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError('Environment name cannot be blank.')
        return value.strip()


class ReleaseSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)
    deployment_count = serializers.SerializerMethodField()

    class Meta:
        model = Release
        fields = [
            'id', 'project', 'project_name', 'version', 'notes', 'status',
            'created_by', 'created_by_name', 'released_at', 'deployment_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_deployment_count(self, obj):
        return obj.deployments.count()

    def validate_version(self, value):
        if not value.strip():
            raise serializers.ValidationError('Version cannot be blank.')
        return value.strip()


class DeploymentSerializer(serializers.ModelSerializer):
    release_version = serializers.CharField(source='release.version', read_only=True)
    environment_name = serializers.CharField(source='environment.name', read_only=True)
    deployed_by_name = serializers.CharField(source='deployed_by.full_name', read_only=True)

    class Meta:
        model = Deployment
        fields = [
            'id', 'release', 'release_version', 'environment', 'environment_name',
            'status', 'deployed_by', 'deployed_by_name',
            'started_at', 'finished_at', 'notes', 'rolled_back_by',
        ]
        read_only_fields = ['id', 'started_at']

    def validate(self, data):
        release = data.get('release', getattr(self.instance, 'release', None))
        environment = data.get('environment', getattr(self.instance, 'environment', None))
        if release and environment:
            if release.project_id != environment.project_id:
                raise serializers.ValidationError(
                    {'environment': 'Environment and release must belong to the same project.'}
                )
            if environment.is_protected and release.status != ReleaseStatus.APPROVED:
                raise serializers.ValidationError(
                    {'environment': 'This environment requires an approved release before deploying.'}
                )
        return data
