from django.core.management.base import BaseCommand
from monitor.models import Website, Site, UserSite
from django.utils.text import slugify

class Command(BaseCommand):
    help = "Миграция Website → Site + UserSite"

    def handle(self, *args, **kwargs):
        for w in Website.objects.select_related("user"):
            site, created = Site.objects.get_or_create(
                url=w.url,
                defaults={
                    "normalized_url": w.url.lower().strip(),
                    "last_status_code": w.last_status_code,
                    "last_response_time": w.last_response_time,
                    "last_checked_at": w.last_checked_at,
                    "last_error": w.last_error,
                    "ssl_status": w.ssl_status,
                    "ssl_days_left": w.ssl_days_left,
                    "domain_days_left": w.domain_days_left,
                    "domain_status": w.domain_status,
                }
            )

            UserSite.objects.get_or_create(
                user=w.user,
                site=site,
                defaults={"name": w.name}
            )

        self.stdout.write(self.style.SUCCESS("Миграция завершена"))
