from django.contrib import admin

from .models import ProjectSetting


@admin.register(ProjectSetting)
class ProjectSettingAdmin(admin.ModelAdmin):
    list_display = ("service_name", "webhook_path", "created_at", "updated_at")
    readonly_fields = ("full_webhook_url",)

