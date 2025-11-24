from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Website
from .services import check_website


@receiver(post_save, sender=Website)
def website_post_save(sender, instance: Website, created: bool, **kwargs):
    """
    При первом создании сайта в админке — сразу делаем проверку.
    Можно по желанию убрать условие created, чтобы проверка была при каждом сохранении.
    """
    if created:
        check_website(instance)
