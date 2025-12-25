from django.urls import path
from .views import (
    SiteListView,
    WebsiteDetailView,
    website_check_now,
    response_time_api,
    dashboard_status_api,
    site_create,
    site_edit,
    site_delete,
    telegram_settings_view
)

urlpatterns = [
    # Главный экран — список сайтов
    path("", SiteListView.as_view(), name="home"),

    # Детальная страница
    path("site/<int:pk>/", WebsiteDetailView.as_view(), name="site_detail"),

    # Принудительная проверка
    path("site/<int:pk>/check/", website_check_now, name="site_check_now"),

    # API для графиков
    path("site/<int:pk>/response-data/", response_time_api, name="response_time_api"),

    # Дашборд API
    path("dashboard/status/", dashboard_status_api, name="dashboard_status_api"),

    # CRUD сайтов
    path("my-sites/add/", site_create, name="site_create"),
    path("my-sites/<int:pk>/edit/", site_edit, name="site_edit"),
    path("my-sites/<int:pk>/delete/", site_delete, name="site_delete"),

    # Настройки Telegram
    path("telegram/", telegram_settings_view, name="telegram_settings"),
]
