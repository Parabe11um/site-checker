import textwrap
import requests
from requests.exceptions import RequestException
from .models import Website
from .models_check import WebsiteCheck
import ssl
import socket
from datetime import datetime
import pytz
from playwright.sync_api import sync_playwright
from sitechecker.telegram import send_photo


def check_website(website: Website, timeout: float = 10.0) -> Website:
    """
    Основной мониторинг сайта + SSL + скриншот.
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


    # ---- Telegram уведомления ----
    from sitechecker.telegram import send_telegram  # путь зависит от структуры проекта

    prev_status = website.last_status_code
    current_status = status_code

    # Сайт упал (был 200 -> стал не 200)
    if prev_status == 200 and current_status != 200:
        send_telegram(
            f"⚠️ <b>Проблема с сайтом</b>\n"
            f"{website.name}\n"
            f"{website.url}\n\n"
            f"HTTP статус: {current_status}\n"
            f"Скриншот: /screenshots/{website.id}.png"
        )

    # Сайт восстановился (был не 200 -> стал 200)
    if prev_status != 200 and current_status == 200:
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

    # 5. Скриншот только при ошибках
    # Считаем ошибками всё, что НЕ 200:
    # - 0 (нет ответа)
    # - 3xx (редиректы)
    # - 4xx (клиентские)
    # - 5xx (серверные)
    # 5. Скриншот + отправка в Telegram (только при ошибках)
    if status_code != 200:
        screenshot_path = None

        # --- попытка сделать скриншот ---
        try:
            screenshot_path = take_screenshot(website)
        except Exception as e:
            print(f"[Screenshot ERROR] {website.url}: {e}")
            screenshot_path = None  # чтобы не отправлять несуществующий файл

        # --- попытка отправить скриншот ---
        if screenshot_path:
            try:
                send_photo(
                    screenshot_path,
                    caption=f"⚠️ Проблема с сайтом\n{website.name}\n{website.url}"
                )
            except Exception as e:
                print(f"[Telegram Photo ERROR] {website.url}: {e}")

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


def take_screenshot(website):
    path = f"/app/screenshots/{website.id}.png"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--ignore-certificate-errors"]
            )
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()

            page.goto(website.url, timeout=15000)
            page.screenshot(path=path, full_page=True)

            browser.close()
    except Exception as e:
        print(f"[SCREENSHOT ERROR] {website.url}: {e}")

    return path

