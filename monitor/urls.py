from django.urls import path
from django.views.generic import RedirectView
from . import views
from .views import (
    SiteListView,
    WebsiteDetailView,
    website_check_now,
    response_time_api,
    dashboard_status_api,
    site_create,
    site_edit,
    site_delete,
    telegram_settings_view,
)

urlpatterns = [
    path("", SiteListView.as_view(), name="home"),

    path("site/<int:pk>/", WebsiteDetailView.as_view(), name="site_detail"),
    path("site/<int:pk>/check/", website_check_now, name="site_check_now"),
    path("site/<int:pk>/response-data/", response_time_api, name="response_time_api"),

    path("dashboard/status/", dashboard_status_api, name="dashboard_status_api"),

    path("my-sites/add/", site_create, name="site_create"),
    path("my-sites/<int:pk>/edit/", site_edit, name="site_edit"),
    path("my-sites/<int:pk>/delete/", site_delete, name="site_delete"),

    # Старый адрес Telegram — временный редирект
    path(
        "telegram/",
        RedirectView.as_view(pattern_name="telegram_settings", permanent=False),
    ),

    # Уведомления
    path("notifications/", views.notifications_index_view, name="notifications_index"),
    path("notifications/telegram/", views.telegram_settings_view, name="telegram_settings"),
    path("notifications/email/", views.email_settings_view, name="email_settings"),
]