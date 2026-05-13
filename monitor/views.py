from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, ListView
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.contrib.auth import logout
from django.utils import timezone
from datetime import timedelta
import datetime
import pytz
from .models import Site, UserSite, TelegramSettings, EmailSettings
from .forms import AddSiteForm
from monitor.services import check_site
from .forms import TelegramSettingsForm, EmailSettingsForm
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from sitechecker.telegram import send_telegram
from urllib.parse import urlparse
from django.db.models import Avg
from statistics import median
from django.urls import reverse


# ======================================================
#        СПИСОК САЙТОВ (замена HomeView)
# ======================================================
class SiteListView(LoginRequiredMixin, ListView):
    template_name = "monitor/home.html"
    context_object_name = "sites"
    login_url = "/login/"

    def get_queryset(self):
        return UserSite.objects.select_related("site").filter(
            user=self.request.user
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        user_sites = context["sites"]
        sites = []

        for us in user_sites:
            site = us.site
            site.display_name = us.name or site.url
            site._usersite = us
            sites.append(site)

        context["sites"] = sites

        context["stats"] = {
            "ok": sum(1 for s in sites if s.last_status_code and s.last_status_code < 300),
            "warn": sum(1 for s in sites if s.last_status_code and 300 <= s.last_status_code < 500),
            "err": sum(1 for s in sites if s.last_status_code and s.last_status_code >= 500),
            "total": len(sites),
        }

        return context

# ======================================================
#          ДЕТАЛИ САЙТА
# ======================================================
@method_decorator(login_required, name="dispatch")
class WebsiteDetailView(LoginRequiredMixin, DetailView):
    login_url = "/login/"
    template_name = "monitor/site_detail.html"
    context_object_name = "site"

    def get_object(self):
        site = get_object_or_404(Site, pk=self.kwargs["pk"])

        # Проверка доступа
        if not self.request.user.is_superuser:
            UserSite.objects.get(site=site, user=self.request.user)

        return site

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        site = self.object

        # ================================
        #  Среднее и медиана отклика
        # ================================
        response_times_qs = site.checks.filter(
            response_time__isnull=False
        ).values_list("response_time", flat=True)

        # Среднее (через SQL)
        context["avg_response_time"] = (
            response_times_qs.aggregate(avg=Avg("response_time"))["avg"]
        )

        # Медиана (через Python)
        response_times = list(response_times_qs)
        context["median_response_time"] = (
            median(response_times) if response_times else None
        )

        # ================================
        # История проверок
        # ================================
        context["history"] = site.checks.all()[:20]

        now = timezone.now()

        def calc_uptime(hours):
            since = now - timedelta(hours=hours)
            qs = site.checks.filter(checked_at__gte=since)

            total = qs.count()
            if total == 0:
                return None

            ok = qs.filter(status_code=200).count()
            return round((ok / total) * 100, 1)

        # Аптайм
        context["uptime_24h"] = calc_uptime(24)
        context["uptime_7d"] = calc_uptime(24 * 7)
        context["uptime_30d"] = calc_uptime(24 * 30)

        # Данные для графиков
        context["chart_history"] = site.checks.order_by("-checked_at")[:50]
        context["errors"] = site.checks.exclude(error="").order_by("-checked_at")[:10]

        return context


# ======================================================
#          ПРОВЕРКА САЙТА
# ======================================================
@login_required
@csrf_exempt
def website_check_now(request, pk):
    site = get_object_or_404(Site, pk=pk)

    if not request.user.is_superuser:
        UserSite.objects.get(site=site, user=request.user)

    check_site(site)

    return JsonResponse({
        "ok": True,
        "status": site.last_status_code,
        "response_time": site.last_response_time,
        "checked_at": site.last_checked_at.strftime("%H:%M:%S %d.%m.%Y"),
    })


@login_required
def response_time_api(request, pk):
    site = get_object_or_404(Site, pk=pk)

    if not request.user.is_superuser:
        UserSite.objects.get(site=site, user=request.user)

    checks = list(site.checks.order_by("-checked_at")[:50])
    checks.reverse()

    return JsonResponse({
        "labels": [c.checked_at.strftime("%H:%M") for c in checks],
        "values": [c.response_time or 0 for c in checks],
    })



# ======================================================
#          ДАШБОРД API
# ======================================================
scheduler_instance = None

def get_scheduler_instance():
    global scheduler_instance
    return scheduler_instance

def set_scheduler_instance(s):
    global scheduler_instance
    scheduler_instance = s

@login_required
def dashboard_status_api(request):
    now = datetime.datetime.now(pytz.utc)

    sites = Site.objects.filter(
        subscribers__user=request.user
    ).distinct()

    return JsonResponse({
        "counts": {
            "ok": sites.filter(last_status_code__lt=300).count(),
            "warn": sites.filter(last_status_code__gte=300, last_status_code__lt=500).count(),
            "err": sites.filter(last_status_code__gte=500).count(),
            "total": sites.count()
        },
        "now": now.isoformat(),
    })


@login_required
def dashboard_sites_api(request):
    user_sites = (
        UserSite.objects
        .select_related("site")
        .filter(user=request.user)
        .order_by("site__id")
    )

    rows = []

    ok_count = 0
    warn_count = 0
    error_count = 0

    for us in user_sites:
        site = us.site

        status_code = site.last_status_code

        if status_code is not None and 200 <= int(status_code) < 300:
            ok_count += 1
        elif status_code is not None and 300 <= int(status_code) < 500:
            warn_count += 1
        else:
            error_count += 1

        last_checked = ""
        if site.last_checked_at:
            last_checked = timezone.localtime(site.last_checked_at).strftime("%d.%m.%Y %H:%M")

        response_time = ""
        if site.last_response_time is not None:
            response_time = f"{site.last_response_time:.2f} с"

        median_response_time = ""
        if site.median_response_time is not None:
            median_response_time = f"med {site.median_response_time:.2f}"

        ssl_text = site.ssl_status or "Нет данных"

        if site.ssl_status == "OK" and site.ssl_days_left is not None:
            ssl_text = f"OK ({site.ssl_days_left} д.)"

        domain_text = ""
        if site.domain_days_left is not None:
            domain_text = str(site.domain_days_left)

        rows.append({
            "id": site.id,
            "name": us.name or site.url,
            "url": site.url,
            "status_code": status_code,
            "response_time": response_time,
            "median_response_time": median_response_time,
            "ssl": ssl_text,
            "domain": domain_text,
            "last_checked_at": last_checked,
            "check_url": reverse("site_check_now", args=[site.id]),
            "detail_url": reverse("site_detail", args=[site.id]),
            "delete_url": reverse("site_delete", args=[site.id]),
        })

    return JsonResponse({
        "stats": {
            "ok": ok_count,
            "warn": warn_count,
            "error": error_count,
            "total": user_sites.count(),
        },
        "rows": rows,
    })


# ======================================================
#                CRUD САЙТОВ
# ======================================================
@login_required
def site_list(request):
    return redirect("/")  # заменяем на SiteListView

@login_required
def site_create(request):
    if request.method == "POST":
        form = AddSiteForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data["name"]
            url = form.cleaned_data["url"]

            parsed = urlparse(url)
            host = parsed.netloc.lower()

            if host.startswith("www."):
                host = host[4:]

            host = host.split(":")[0]
            site = Site.objects.filter(normalized_url=host).first()

            if site:
                if UserSite.objects.filter(user=request.user, site=site).exists():
                    form.add_error(
                        "url",
                        "Этот сайт уже добавлен в ваш список"
                    )
                    return render(request, "monitor/site_create.html", {
                        "form": form
                    })

            site = site or Site.objects.create(url=url)

            UserSite.objects.get_or_create(
                user=request.user,
                site=site,
                defaults={"name": name}
            )

            check_site(site)

            return redirect("home")
    else:
        form = AddSiteForm()

    return render(request, "monitor/site_create.html", {
        "form": form
    })






@login_required
def site_edit(request, pk):
    usersite = get_object_or_404(UserSite, site_id=pk, user=request.user)

    if request.method == "POST":
        usersite.name = request.POST.get("name")
        usersite.save()
        return redirect("home")

    return render(request, "monitor/site_edit.html", {"usersite": usersite})


@login_required
def site_delete(request, pk):
    site = get_object_or_404(Site, pk=pk)
    UserSite.objects.filter(site=site, user=request.user).delete()
    return redirect("home")

# ======================================================
#                TELEGRAM SETTINGS
# ======================================================
@login_required
def telegram_settings_view(request):
    settings_obj = TelegramSettings.objects.filter(user=request.user).first()

    if request.method == "POST":

        # 🔴 Отключить Telegram
        if "disconnect_telegram" in request.POST:
            if settings_obj:
                settings_obj.is_active = False
                settings_obj.save(update_fields=["is_active"])

            messages.success(request, "Telegram-уведомления отключены")
            return redirect("telegram_settings")

        # 🧪 Тест
        if "send_test" in request.POST and settings_obj:
            send_telegram(
                request.user,
                "✅ Тестовое сообщение от Site-Checker"
            )
            messages.success(request, "Тестовое сообщение отправлено")
            return redirect("telegram_settings")

        form = TelegramSettingsForm(
            request.POST,
            instance=settings_obj
        )

        if form.is_valid():
            telegram = form.save(commit=False)
            telegram.user = request.user
            telegram.save()

            messages.success(request, "Telegram-настройки сохранены")
            return redirect("telegram_settings")

    else:
        form = TelegramSettingsForm(instance=settings_obj)

    return render(
        request,
        "monitor/telegram_settings.html",
        {
            "form": form,
            "settings": settings_obj,
        }
    )

# ======================================================
#                ЛОГАУТ
# ======================================================
def custom_logout(request):
    logout(request)
    response = redirect("/login/")
    response.delete_cookie("sessionid")
    response.delete_cookie("csrftoken")
    return response

# ======================================================
#                УВЕДОМЛЕНИЯ
# ======================================================
@login_required
def notifications_index_view(request):
    tg = TelegramSettings.objects.filter(user=request.user).first()
    email_settings = EmailSettings.objects.filter(user=request.user).first()

    return render(request, "monitor/notifications/index.html", {
        "tg": tg,
        "email_settings": email_settings,
    })

@login_required
def email_settings_view(request):
    settings_obj = EmailSettings.objects.filter(user=request.user).first()

    if request.method == "POST":

        # Отключить email-уведомления
        if "disconnect_email" in request.POST and settings_obj:
            settings_obj.is_active = False
            settings_obj.save(update_fields=["is_active"])
            messages.success(request, "Email-уведомления отключены")
            return redirect("email_settings")

        form = EmailSettingsForm(request.POST, instance=settings_obj)

        if form.is_valid():
            email_settings = form.save(commit=False)
            email_settings.user = request.user
            email_settings.save()

            messages.success(request, "Email-настройки сохранены")
            return redirect("email_settings")
    else:
        form = EmailSettingsForm(instance=settings_obj)

    return render(
        request,
        "monitor/notifications/email.html",
        {
            "form": form,
            "settings": settings_obj,
        }
    )