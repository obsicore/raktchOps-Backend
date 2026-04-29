from django.urls import path
from .views import AdminDashboardView, PMDashboardView, TeamLeadDashboardView, StaffDashboardView

urlpatterns = [
    path('admin/', AdminDashboardView.as_view(), name='dashboard-admin'),
    path('pm/', PMDashboardView.as_view(), name='dashboard-pm'),
    path('team-lead/', TeamLeadDashboardView.as_view(), name='dashboard-team-lead'),
    path('staff/', StaffDashboardView.as_view(), name='dashboard-staff'),
]
