from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings
from .views import set_scheduler_instance, get_scheduler_instance
from .services import check_site
from .models import Website
from apscheduler.triggers.interval import IntervalTrigger

def run_checks():
    for site in Website.objects.all():
        check_site(site)

def start_scheduler():
    # Если scheduler уже запущен — НЕ запускать повторно
    existing = get_scheduler_instance()
    if existing:
        print("Scheduler already running, skipping second start")
        return

    scheduler = BackgroundScheduler()

    scheduler.add_job(
        run_checks,
        IntervalTrigger(minutes=5),
        id='website_check_job',
        replace_existing=True,
    )

    scheduler.start()
    set_scheduler_instance(scheduler)
    print("Scheduler started")
