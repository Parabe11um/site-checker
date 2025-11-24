from django.urls import path
from .views import (
    HomeView,
    WebsiteDetailView,
    website_check_now,
    response_time_api,
    dashboard_status_api,
)

urlpatterns = [
    path("", HomeView.as_view(), name="home"),

    # Детальная страница сайта
    path("site/<int:pk>/", WebsiteDetailView.as_view(), name="site_detail"),

    # Принудительная проверка
    path("site/<int:pk>/check/", website_check_now, name="site_check_now"),

    # API графика
    path("site/<int:pk>/response-data/", response_time_api, name="response_time_api"),

    # API дашборда
    path("dashboard/status/", dashboard_status_api, name="dashboard_status_api"),
]