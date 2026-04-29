"""URL configuration for the projects app."""

from django.urls import path
from .views import (
    ProjectListCreateView,
    ProjectDetailView,
    ProjectMemberListView,
    ProjectMemberDetailView,
)

urlpatterns = [
    path('', ProjectListCreateView.as_view(), name='project-list-create'),
    path('<uuid:pk>/', ProjectDetailView.as_view(), name='project-detail'),
    path('<uuid:pk>/members/', ProjectMemberListView.as_view(), name='project-member-list'),
    path('<uuid:pk>/members/<uuid:membership_pk>/', ProjectMemberDetailView.as_view(), name='project-member-detail'),
]
