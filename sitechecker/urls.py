from django.contrib.auth import views as auth_views
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from monitor.views import HomeView, custom_logout

urlpatterns = [
      path("admin/", admin.site.urls),

      # Авторизация
      path("login/", auth_views.LoginView.as_view(
          template_name="monitor/login.html",
          redirect_authenticated_user=True
      ), name="login"),

      # logout
      path("logout/", custom_logout, name="logout"),

      path("", HomeView.as_view(), name="home"),
      path("", include("monitor.urls")),
    ] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Раздача статических файлов (только DEBUG)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

    # Раздача скриншотов
    urlpatterns += static("/screenshots/", document_root="/app/screenshots/")
