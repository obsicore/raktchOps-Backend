"""URL patterns for the tasks app."""

from django.urls import path
from .views import TaskListCreateView, TaskDetailView, TaskMoveView

# Module-nested patterns (included under /api/v1/modules/<module_id>/tasks/)
module_urlpatterns = [
    path('', TaskListCreateView.as_view(), name='task-list-create'),
    path('<int:pk>/', TaskDetailView.as_view(), name='task-detail'),
]

# Top-level task action patterns (included under /api/v1/tasks/)
task_urlpatterns = [
    path('<int:pk>/move/', TaskMoveView.as_view(), name='task-move'),
]
