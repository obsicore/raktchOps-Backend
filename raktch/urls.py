"""
Root URL configuration for the RAKTCH backend.
All application APIs are mounted under /api/v1/.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from tasks.views import TaskListCreateView, TaskDetailView, TaskMoveView, ProjectBoardView, OrgBoardView

api_v1_patterns = [
    # JWT auth endpoints
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # App routers
    path('auth/', include('accounts.urls')),
    path('rbac/', include('rbac.urls')),
    path('people/', include('people.urls')),
    path('org/', include('org.urls')),
    path('projects/', include('projects.urls')),

    # Modules (nested under projects for CRUD, separate endpoint for bulk import)
    path('projects/<uuid:project_id>/modules/', include('modules.urls')),

    # Tasks nested under modules
    path('modules/<int:module_id>/tasks/', TaskListCreateView.as_view(), name='task-list-create'),
    path('modules/<int:module_id>/tasks/<int:pk>/', TaskDetailView.as_view(), name='task-detail'),

    # Top-level task actions (kanban move)
    path('tasks/<int:pk>/move/', TaskMoveView.as_view(), name='task-move'),

    # Project kanban board
    path('projects/<uuid:project_id>/board/', ProjectBoardView.as_view(), name='project-board'),

    # Org-wide board
    path('board/', OrgBoardView.as_view(), name='org-board'),

    path('workitems/', include('workitems.urls')),
    path('boards/', include('boards.urls')),
    path('planning/', include('planning.urls')),
    path('deployments/', include('deployments.urls')),
    path('notifications/', include('notifications.urls')),
    path('search/', include('searchapp.urls')),
    path('dashboards/', include('dashboards.urls')),
]

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include(api_v1_patterns)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
