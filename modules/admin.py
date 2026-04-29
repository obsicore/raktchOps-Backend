from django.contrib import admin
from .models import Module

@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'project', 'status', 'priority', 'deadline']
    list_filter = ['status', 'priority']
    search_fields = ['name', 'project__name']
