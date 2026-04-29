from django.urls import path
from .views import (
    EnvironmentListCreateView, EnvironmentDetailView,
    ReleaseListCreateView, ReleaseDetailView,
    DeploymentListCreateView, DeploymentDetailView,
)

urlpatterns = [
    path('environments/', EnvironmentListCreateView.as_view(), name='environment-list-create'),
    path('environments/<uuid:pk>/', EnvironmentDetailView.as_view(), name='environment-detail'),
    path('releases/', ReleaseListCreateView.as_view(), name='release-list-create'),
    path('releases/<uuid:pk>/', ReleaseDetailView.as_view(), name='release-detail'),
    path('deployments/', DeploymentListCreateView.as_view(), name='deployment-list-create'),
    path('deployments/<uuid:pk>/', DeploymentDetailView.as_view(), name='deployment-detail'),
]
