from django.contrib import admin
from .models import UserSetting


@admin.register(UserSetting)
class UserSettingAdmin(admin.ModelAdmin):
    list_display = ("user", "key", "value")
    search_fields = ("key", "value", "user__username")

