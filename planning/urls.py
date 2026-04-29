from django.urls import path
from .views import SprintListCreateView, SprintDetailView, MilestoneListCreateView, MilestoneDetailView

urlpatterns = [
    path('sprints/', SprintListCreateView.as_view(), name='sprint-list-create'),
    path('sprints/<uuid:pk>/', SprintDetailView.as_view(), name='sprint-detail'),
    path('milestones/', MilestoneListCreateView.as_view(), name='milestone-list-create'),
    path('milestones/<uuid:pk>/', MilestoneDetailView.as_view(), name='milestone-detail'),
]
