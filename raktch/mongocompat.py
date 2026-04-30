"""
Custom AppConfig subclasses that override default_auto_field for Django's built-in apps,
which hardcode AutoField and thus break the django-mongodb-backend compatibility check.
"""

from django.contrib.admin.apps import AdminConfig
from django.contrib.auth.apps import AuthConfig
from django.contrib.contenttypes.apps import ContentTypesConfig


class MongoAdminConfig(AdminConfig):
    name = "django.contrib.admin"
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"


class MongoAuthConfig(AuthConfig):
    name = "django.contrib.auth"
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"

    def ready(self):
        super().ready()
        # Disconnect create_permissions post_migrate signal — this project uses
        # custom RBAC and ObjectId PKs cause a hashing issue in this signal.
        from django.db.models.signals import post_migrate
        post_migrate.disconnect(
            dispatch_uid="django.contrib.auth.management.create_permissions",
        )


class MongoContentTypesConfig(ContentTypesConfig):
    name = "django.contrib.contenttypes"
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
