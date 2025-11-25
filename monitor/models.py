from django.db import models
from django.utils import timezone


class Website(models.Model):
    name = models.CharField("Название", max_length=255)
    url = models.URLField("URL", unique=True)

    last_status_code = models.IntegerField("Последний статус", null=True, blank=True)
    last_response_time = models.FloatField(
        "Последнее время ответа (сек.)", null=True, blank=True
    )
    last_checked_at = models.DateTimeField(
        "Последняя проверка", null=True, blank=True
    )
    last_error = models.TextField("Последняя ошибка", blank=True)
    last_content_snippet = models.TextField(
        "Фрагмент последнего ответа", blank=True
    )

    ssl_valid_from = models.DateTimeField(null=True, blank=True)
    ssl_valid_to = models.DateTimeField(null=True, blank=True)
    ssl_days_left = models.IntegerField(null=True, blank=True)
    ssl_status = models.CharField(max_length=50, null=True, blank=True)

    domain_expiration = models.DateTimeField(null=True, blank=True)
    domain_days_left = models.IntegerField(null=True, blank=True)
    domain_status = models.CharField(max_length=50, default="UNKNOWN")

    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Сайт"
        verbose_name_plural = "Сайты"

    def __str__(self):
        return f"{self.name} ({self.url})"

    def mark_checked(
            self,
            status_code: int | None,
            response_time: float | None,
            content_snippet: str = "",
            error: str = "",
            ssl_valid_from=None,
            ssl_valid_to=None,
            ssl_days_left=None,
            ssl_status=None,
    ):
        self.last_status_code = status_code
        self.last_response_time = response_time
        self.last_content_snippet = content_snippet
        self.last_error = error
        self.last_checked_at = timezone.now()

        # SSL
        if ssl_valid_from:
            self.ssl_valid_from = ssl_valid_from
        if ssl_valid_to:
            self.ssl_valid_to = ssl_valid_to
        if ssl_days_left is not None:
            self.ssl_days_left = ssl_days_left
        if ssl_status is not None:
            self.ssl_status = ssl_status

        self.save()


class TelegramSettings(models.Model):
    token = models.CharField("Telegram Bot Token", max_length=200)
    chat_id = models.CharField("Telegram Chat ID", max_length=50)

    def __str__(self):
        return "Telegram Integration Settings"

    class Meta:
        verbose_name = "Telegram настройки"
        verbose_name_plural = "Telegram настройки"