# monitor/models_check.py
from django.db import models
from django.utils import timezone
from .models import Site


class SiteCheck(models.Model):
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="checks")
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
        return f"Check {self.site} @ {self.checked_at}"
