import textwrap
import requests
from requests.exceptions import RequestException
from .models import Website
from .models_check import WebsiteCheck
import ssl
import socket
from datetime import datetime
import pytz


def check_website(website: Website, timeout: float = 10.0) -> Website:
    """
    Основной мониторинг сайта + SSL.
    """

    status_code = None
    response_time = None
    snippet = ""
    error_text = ""

    # 1. HTTP проверка
    try:
        response = requests.get(website.url, timeout=timeout)
        status_code = response.status_code
        response_time = response.elapsed.total_seconds()

        content = response.text
        snippet = textwrap.shorten(content, width=2000, placeholder=" ...")

        if 500 <= status_code <= 599:
            error_text = f"Server error {status_code}"
        else:
            error_text = ""

    except RequestException as e:
        error_text = str(e)
        status_code = 0  # Сайт недоступен

    # ---- Telegram уведомления ----
    from sitechecker.telegram import send_telegram

    prev_status = website.last_status_code
    current_status = status_code

    if prev_status is None:
        prev_status = 200

    # --- Агрессивный режим ---
    # Если сайт вернул 500 → отправляем ВСЕГДА
    if current_status == 500:
        send_telegram(
            f"🚨 <b>Критическая ошибка (500)</b>\n"
            f"{website.name}\n"
            f"{website.url}"
        )

    # --- Уведомление при изменении статуса ---
    elif prev_status != current_status:

        # Упал
        if current_status != 200:
            send_telegram(
                f"⚠️ <b>Проблема с сайтом</b>\n"
                f"{website.name}\n"
                f"{website.url}\n\n"
                f"HTTP статус: {current_status}"
            )

        # Восстановился
        else:
            send_telegram(
                f"✅ <b>Сайт восстановлен</b>\n"
                f"{website.name}\n"
                f"{website.url}"
            )

    # 2. SSL проверка
    ssl_info = check_ssl_certificate(website.url)

    website.ssl_valid_from = ssl_info["valid_from"]
    website.ssl_valid_to = ssl_info["valid_to"]
    website.ssl_days_left = ssl_info["days_left"]
    website.ssl_status = ssl_info["status"]

    # 3. Обновляем последние поля
    from django.utils import timezone
    website.last_status_code = status_code
    website.last_response_time = response_time
    website.last_content_snippet = snippet
    website.last_error = error_text
    website.last_checked_at = timezone.now()
    website.save()

    # 4. Пишем в историю
    WebsiteCheck.objects.create(
        website=website,
        status_code=status_code,
        response_time=response_time,
        content_snippet=snippet,
        error=error_text,
    )

    return website


def check_ssl_certificate(url: str) -> dict:
    """Проверяет SSL сертификат сайта."""
    hostname = url.replace("https://", "").replace("http://", "").split("/")[0]
    ctx = ssl.create_default_context()

    try:
        with socket.create_connection((hostname, 443), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()

        valid_from = datetime.strptime(
            cert["notBefore"], "%b %d %H:%M:%S %Y %Z"
        ).replace(tzinfo=pytz.UTC)

        valid_to = datetime.strptime(
            cert["notAfter"], "%b %d %H:%M:%S %Y %Z"
        ).replace(tzinfo=pytz.UTC)

        days_left = (valid_to - datetime.now(pytz.UTC)).days

        return {
            "valid_from": valid_from,
            "valid_to": valid_to,
            "days_left": days_left,
            "status": "OK" if days_left > 0 else "EXPIRED",
        }

    except Exception as e:
        return {
            "valid_from": None,
            "valid_to": None,
            "days_left": None,
            "status": f"ERROR: {e}",
        }
