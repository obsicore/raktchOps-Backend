"""URL configuration for the org app."""

from django.urls import path
from .views import (
    DepartmentListCreateView,
    DepartmentDetailView,
    TeamListCreateView,
    TeamDetailView,
    TeamMembershipListView,
    TeamMembershipDetailView,
)

urlpatterns = [
    # Departments
    path('departments/', DepartmentListCreateView.as_view(), name='department-list-create'),
    path('departments/<uuid:pk>/', DepartmentDetailView.as_view(), name='department-detail'),

    # Teams
    path('teams/', TeamListCreateView.as_view(), name='team-list-create'),
    path('teams/<uuid:pk>/', TeamDetailView.as_view(), name='team-detail'),

    # Team memberships
    path('teams/<uuid:pk>/members/', TeamMembershipListView.as_view(), name='team-membership-list'),
    path('teams/<uuid:pk>/members/<uuid:membership_pk>/', TeamMembershipDetailView.as_view(), name='team-membership-detail'),
]
