# sitechecker/settings/local.py
from .base import *

DEBUG = True
SECRET_KEY = "replace-me-dev"

ALLOWED_HOSTS = ["*"]


INSTALLED_APPS += [
    "django_apscheduler",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "sitechecker",
        "USER": "checker",
        "PASSWORD": "checker123",
        "HOST": "db",
        "PORT": "3306",
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}

# -----------------------------
# EMAIL SETTINGS (для разработки)
# -----------------------------
EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
EMAIL_FILE_PATH = "/app/sent_emails"