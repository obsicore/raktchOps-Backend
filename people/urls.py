"""URL configuration for the people app."""

from django.urls import path
from .views import EmployeeListCreateView, EmployeeDetailView, MyProfileView, EmployeeContributionsView

urlpatterns = [
    path('employees/', EmployeeListCreateView.as_view(), name='employee-list-create'),
    path('employees/<uuid:pk>/', EmployeeDetailView.as_view(), name='employee-detail'),
    path('employees/<uuid:pk>/contributions/', EmployeeContributionsView.as_view(), name='employee-contributions'),
    path('me/', MyProfileView.as_view(), name='my-profile'),
]
