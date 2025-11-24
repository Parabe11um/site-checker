# monitor/models_check.py
from django.db import models
from django.utils import timezone
from .models import Website


class WebsiteCheck(models.Model):
    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name="checks")
    status_code = models.IntegerField(null=True, blank=True)
    response_time = models.FloatField(null=True, blank=True)
    error = models.TextField(blank=True)
    content_snippet = models.TextField(blank=True)
    checked_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-checked_at"]
        verbose_name = "Проверка сайта"
        verbose_name_plural = "История проверок"

    def __str__(self):
        return f"Check {self.website.name} @ {self.checked_at}"
