"""URL configuration for the workitems app."""
from django.urls import path
from .views import (
    WorkItemListCreateView, WorkItemDetailView, KanbanMoveView,
    CommentListCreateView, CommentDetailView, KanbanBoardView, MoveLogView,
)

urlpatterns = [
    path('', WorkItemListCreateView.as_view(), name='workitem-list-create'),
    path('board/', KanbanBoardView.as_view(), name='kanban-board'),
    path('<uuid:pk>/', WorkItemDetailView.as_view(), name='workitem-detail'),
    path('<uuid:pk>/move/', KanbanMoveView.as_view(), name='workitem-move'),
    path('<uuid:pk>/comments/', CommentListCreateView.as_view(), name='comment-list-create'),
    path('<uuid:pk>/comments/<uuid:comment_pk>/', CommentDetailView.as_view(), name='comment-detail'),
    path('<uuid:pk>/moves/', MoveLogView.as_view(), name='move-log'),
]
