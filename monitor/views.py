from django.shortcuts import get_object_or_404, redirect
from django.views.generic import DetailView, ListView, TemplateView
from django.http import JsonResponse
from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import pytz
from .models import Website
from .services import check_website
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.utils.decorators import method_decorator
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from datetime import timedelta

@method_decorator(login_required, name="dispatch")
class WebsiteDetailView(LoginRequiredMixin, DetailView):
    login_url = "/login/"
    template_name = "monitor/site_detail.html"
    model = Website
    context_object_name = "site"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        site = self.object

        # ░░░ История (как и было — НЕ трогаем) ░░░
        context["history"] = site.checks.all()[:20]

        # ░░░ Новый функционал: расчёт аптайма ░░░
        now = timezone.now()

        def calc_uptime(hours):
            since = now - timedelta(hours=hours)
            qs = site.checks.filter(checked_at__gte=since)

            total = qs.count()
            if total == 0:
                return None

            ok = qs.filter(status_code=200).count()
            return round((ok / total) * 100, 1)

        context["uptime_24h"] = calc_uptime(24)
        context["uptime_7d"] = calc_uptime(24 * 7)
        context["uptime_30d"] = calc_uptime(24 * 30)

        # ░░░ История для графика (последние 50 проверок) ░░░
        context["chart_history"] = (
            site.checks.order_by("-checked_at")[:50]
        )

        # ░░░ Последние ошибки (10 шт) ░░░
        context["errors"] = (
            site.checks.exclude(error="").order_by("-checked_at")[:10]
        )

        return context



@login_required(login_url="/login/")
@csrf_exempt
def website_check_now(request, pk):
    site = get_object_or_404(Website, pk=pk)
    result = check_website(site)

    return JsonResponse({
        "ok": True,
        "status": site.last_status_code,
        "response_time": site.last_response_time,
        "checked_at": site.last_checked_at.strftime("%H:%M:%S %d.%m.%Y"),
    })

@login_required(login_url="/login/")
def response_time_api(request, pk):
    website = Website.objects.get(pk=pk)
    checks = list(website.checks.order_by("-checked_at")[:50])
    checks.reverse()

    return JsonResponse({
        "labels": [c.checked_at.strftime("%H:%M") for c in checks],
        "values": [c.response_time or 0 for c in checks],
    })


@method_decorator(login_required, name="dispatch")
class HomeView(LoginRequiredMixin, TemplateView):
    login_url = "/login/"
    template_name = "monitor/home.html"

    def get_context_data(self, **kwargs):
        from .views import dashboard_status_api
        context = super().get_context_data(**kwargs)

        sites = Website.objects.all().order_by('name')

        ok = sites.filter(last_status_code__lt=300).count()
        warn = sites.filter(last_status_code__gte=300, last_status_code__lt=500).count()
        err = sites.filter(last_status_code__gte=500).count()

        context.update({
            "sites": sites,
            "stats": {
                "ok": ok,
                "warn": warn,
                "err": err,
                "total": sites.count(),
            }
        })
        return context

# ---- Scheduler linkage ----

scheduler_instance = None


def get_scheduler_instance():
    global scheduler_instance
    return scheduler_instance


def set_scheduler_instance(s):
    global scheduler_instance
    scheduler_instance = s

@login_required(login_url="/login/")
def dashboard_status_api(request):
    now = datetime.datetime.now(pytz.utc)
    sched = get_scheduler_instance()

    next_run = None
    if sched:
        jobs = sched.get_jobs()
        if jobs:
            next_run = jobs[0].next_run_time

    sites = Website.objects.all()

    ok = sites.filter(last_status_code__lt=300).count()
    warn = sites.filter(last_status_code__gte=300, last_status_code__lt=500).count()
    err = sites.filter(last_status_code__gte=500).count()

    return JsonResponse({
        "next_run": next_run.isoformat() if next_run else None,
        "counts": {
            "ok": ok,
            "warn": warn,
            "err": err,
            "total": sites.count()
        },
        "now": now.isoformat(),
    })

def custom_logout(request):
    logout(request)
    response = redirect("/login/")
    response.delete_cookie("sessionid")     # очистить куки ЛК
    response.delete_cookie("csrftoken")
    return response