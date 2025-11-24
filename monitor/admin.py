from django.contrib import admin
from .models import Website, TelegramSettings
from .services import check_website


@admin.register(Website)
class WebsiteAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "url",
        "last_status_code",
        "last_response_time",
        "last_checked_at",
    )
    search_fields = ("name", "url")
    readonly_fields = (
        "last_status_code",
        "last_response_time",
        "last_checked_at",
        "last_error",
        "last_content_snippet",
        "created_at",
    )

    fieldsets = (
        (None, {"fields": ("name", "url")}),
        ("Последний результат проверки", {
            "fields": (
                "last_status_code",
                "last_response_time",
                "last_checked_at",
                "last_error",
                "last_content_snippet",
            )
        }),
        ("Служебное", {"fields": ("created_at",)}),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change:
            check_website(obj)


# -------------------------------
# Регистрация Telegram-настроек
# -------------------------------

admin.site.register(TelegramSettings)
