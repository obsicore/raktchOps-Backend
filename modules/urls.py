"""URL patterns for the modules app (nested under /api/v1/projects/<project_id>/modules/)."""

from django.urls import path
from .views import ModuleListCreateView, ModuleDetailView, ModuleBulkImportView

urlpatterns = [
    path('', ModuleListCreateView.as_view(), name='module-list-create'),
    path('bulk-import/', ModuleBulkImportView.as_view(), name='module-bulk-import'),
    path('bulk-import/template/', ModuleBulkImportView.as_view(), name='module-bulk-import-template'),
    path('<int:pk>/', ModuleDetailView.as_view(), name='module-detail'),
]
