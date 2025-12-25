from django.contrib import admin
from .models import Site, UserSite, TelegramSettings
from .models_check import SiteCheck


# -------------------------------
# Site (единый сайт)
# -------------------------------
@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = (
        "url",
        "last_status_code",
        "last_response_time",
        "last_checked_at",
    )
    search_fields = ("url",)
    readonly_fields = (
        "last_status_code",
        "last_response_time",
        "last_checked_at",
        "last_error",
    )


# -------------------------------
# Связь пользователь ↔ сайт
# -------------------------------
@admin.register(UserSite)
class UserSiteAdmin(admin.ModelAdmin):
    list_display = ("user", "site", "name", "notify_enabled")
    list_filter = ("notify_enabled",)
    search_fields = ("user__username", "site__url", "name")


# -------------------------------
# История проверок
# -------------------------------
@admin.register(SiteCheck)
class WebsiteCheckAdmin(admin.ModelAdmin):
    list_display = (
        "site",
        "status_code",
        "response_time",
        "checked_at",
    )
    list_filter = ("status_code",)
    readonly_fields = (
        "site",
        "status_code",
        "response_time",
        "content_snippet",
        "error",
        "checked_at",
    )


# -------------------------------
# Telegram настройки
# -------------------------------
admin.site.register(TelegramSettings)
