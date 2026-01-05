from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from accounts.views import (
    RegisterView, ActivateView, LoginView, LogoutView, dashboard
)

urlpatterns = []

# ------- Админка (только если включена) -------
if settings.ADMIN_ENABLED:
    urlpatterns += [
        path("admin/", admin.site.urls),
    ]


# ------- Аутентификация -------
urlpatterns += [
    path("register/", RegisterView.as_view(), name="register"),
    path("activate/<uidb64>/<token>/", ActivateView.as_view(), name="activate"),

    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),

    path("dashboard/", dashboard, name="dashboard"),
]


# ------- Основной интерфейс мониторинга -------
urlpatterns += [
    # Теперь главный экран — SiteListView из monitor.views
    path("", include("monitor.urls")),
]


# ------- Статика и медиа -------
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static("/screenshots/", document_root="/app/screenshots/")
