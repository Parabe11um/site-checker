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

from .models import Site, UserSite, TelegramSettings
from .forms import AddSiteForm
from .services import check_site
from .forms import TelegramSettingsForm
from django.views.decorators.csrf import csrf_exempt




# ======================================================
#        СПИСОК САЙТОВ (замена HomeView)
# ======================================================
class SiteListView(LoginRequiredMixin, ListView):
    template_name = "monitor/home.html"
    context_object_name = "sites"
    login_url = "/login/"

    def get_queryset(self):
        if self.request.user.is_superuser or self.request.user.role == "admin":
            return UserSite.objects.select_related("site").all()
        return UserSite.objects.select_related("site").filter(user=self.request.user)

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

        # История проверок
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

            site, _ = Site.objects.get_or_create(url=url)

            UserSite.objects.get_or_create(
                user=request.user,
                site=site,
                defaults={"name": name}
            )

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
    settings_obj, _ = TelegramSettings.objects.get_or_create(id=1)

    if request.method == "POST":
        form = TelegramSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            return redirect("telegram_settings")

    else:
        form = TelegramSettingsForm(instance=settings_obj)

    return render(request, "monitor/telegram_settings.html", {"form": form})


# ======================================================
#                ЛОГАУТ
# ======================================================
def custom_logout(request):
    logout(request)
    response = redirect("/login/")
    response.delete_cookie("sessionid")
    response.delete_cookie("csrftoken")
    return response
