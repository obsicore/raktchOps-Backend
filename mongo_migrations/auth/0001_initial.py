import django.contrib.auth.models
import django.contrib.auth.validators
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models
import django_mongodb_backend.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Permission',
            fields=[
                ('id', django_mongodb_backend.fields.ObjectIdAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                )),
                ('name', models.CharField(max_length=255, verbose_name='name')),
                ('content_type', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to='contenttypes.contenttype',
                    verbose_name='content type',
                )),
                ('codename', models.CharField(max_length=100, verbose_name='codename')),
            ],
            options={
                'verbose_name': 'permission',
                'verbose_name_plural': 'permissions',
                'ordering': ['content_type__app_label', 'content_type__model', 'codename'],
                'unique_together': {('content_type', 'codename')},
            },
            managers=[('objects', django.contrib.auth.models.PermissionManager())],
        ),
        migrations.CreateModel(
            name='Group',
            fields=[
                ('id', django_mongodb_backend.fields.ObjectIdAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                )),
                ('name', models.CharField(max_length=150, unique=True, verbose_name='name')),
                ('permissions', models.ManyToManyField(
                    blank=True,
                    to='auth.permission',
                    verbose_name='permissions',
                )),
            ],
            options={
                'verbose_name': 'group',
                'verbose_name_plural': 'groups',
                'ordering': ['name'],
            },
            managers=[('objects', django.contrib.auth.models.GroupManager())],
        ),
    ]
