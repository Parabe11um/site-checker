from django.db import models
from django.utils import timezone
from django.conf import settings
from urllib.parse import urlparse

class Website(models.Model):
    name = models.CharField("Название", max_length=255)
    url = models.URLField("URL")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="websites",
        verbose_name="Владелец",
        null=True,
        blank=True
    )

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
    domain_status = models.CharField(max_length=100, default="UNKNOWN")

    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Сайт"
        verbose_name_plural = "Сайты"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "url"],
                name="unique_site_per_user"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.url})"

    def mark_checked(
            self,
            status_code,
            response_time,
            content_snippet="",
            error="",
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

        if ssl_valid_from:
            self.ssl_valid_from = ssl_valid_from
        if ssl_valid_to:
            self.ssl_valid_to = ssl_valid_to
        if ssl_days_left is not None:
            self.ssl_days_left = ssl_days_left
        if ssl_status is not None:
            self.ssl_status = ssl_status

        self.save()


class Site(models.Model):
    url = models.URLField(unique=True)
    normalized_url = models.CharField(max_length=255, unique=True, editable=False)

    ip_address = models.GenericIPAddressField(
        "IP адрес сайта",
        null=True,
        blank=True
    )

    ip_provider = models.CharField(
        "Провайдер / организация",
        max_length=255,
        blank=True
    )

    ip_asn = models.CharField(
        "ASN",
        max_length=50,
        blank=True
    )

    ip_country = models.CharField(
        "Страна",
        max_length=2,
        blank=True
    )

    ipinfo_updated_at = models.DateTimeField(
        null=True,
        blank=True
    )

    # Последнее состояние
    last_status_code = models.IntegerField(null=True, blank=True)
    last_response_time = models.FloatField(null=True, blank=True)

    avg_response_time = models.FloatField(
        "Среднее время отклика (сек.)",
        null=True,
        blank=True
    )

    median_response_time = models.FloatField(
        "Медианное время отклика (сек.)",
        null=True,
        blank=True
    )


    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    ssl_valid_from = models.DateTimeField(null=True, blank=True)
    ssl_valid_to = models.DateTimeField(null=True, blank=True)
    ssl_days_left = models.IntegerField(null=True, blank=True)
    ssl_status = models.CharField(max_length=50, null=True, blank=True)

    domain_expiration = models.DateTimeField(null=True, blank=True)
    domain_days_left = models.IntegerField(null=True, blank=True)
    domain_status = models.CharField(max_length=100, default="UNKNOWN")

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.normalized_url:
            parsed = urlparse(self.url)

            if not parsed.netloc:
                raise ValueError(f"Invalid URL for normalization: {self.url}")

            self.normalized_url = parsed.netloc.lower()

        super().save(*args, **kwargs)


class UserSite(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_sites"
    )
    site = models.ForeignKey(
        Site,
        on_delete=models.CASCADE,
        related_name="subscribers"
    )

    name = models.CharField("Название у пользователя", max_length=255)
    notify_enabled = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "site")

    def __str__(self):
        return f"{self.user} → {self.site.url}"


class TelegramSettings(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="telegram_settings"
    )

    token = models.CharField(max_length=200, blank=True)
    chat_id = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)

    notify_down = models.BooleanField(default=True)
    notify_up = models.BooleanField(default=True)
    notify_timeout = models.BooleanField(default=True)

    # 🆕 Email
    email_enabled = models.BooleanField(
        default=False,
        verbose_name="Отправлять уведомления на email"
    )

    created_at = models.DateTimeField(auto_now_add=True)


    @property
    def is_configured(self):
        """
        Есть ли минимальная конфигурация
        """
        return bool(self.token and self.chat_id)

    @property
    def is_connected(self):
        """
        Telegram реально подключён и работает
        """
        return self.is_active and self.is_configured