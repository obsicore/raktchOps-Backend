from django.urls import path
from .views import KanbanBoardDetailView

urlpatterns = [
    path('<uuid:project_pk>/', KanbanBoardDetailView.as_view(), name='kanban-board-config'),
]
