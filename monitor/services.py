import textwrap
import requests
from requests.exceptions import RequestException
from .models import Website
from .models_check import WebsiteCheck
import ssl
import socket
from datetime import datetime
import pytz
import subprocess
import re

from sitechecker.telegram import send_telegram


# ============================================================
# ===============  ГЛАВНАЯ ФУНКЦИЯ ПРОВЕРКИ  ==================
# ============================================================

def check_website(website: Website, timeout: float = 10.0) -> Website:
    """
    Основной мониторинг сайта:
    - HTTP статус
    - Скорость ответа
    - Ошибки
    - SSL сертификат
    - Дата окончания домена (WHOIS)
    """

    status_code = None
    response_time = None
    snippet = ""
    error_text = ""

    # ==========================
    #       1. HTTP проверка
    # ==========================
    try:
        response = requests.get(website.url, timeout=timeout)
        status_code = response.status_code
        response_time = response.elapsed.total_seconds()

        content = response.text
        snippet = textwrap.shorten(content, width=2000, placeholder=" ...")

        if status_code >= 500:
            error_text = f"Server error {status_code}"
        else:
            error_text = ""

    except RequestException as e:
        status_code = 0        # недоступен
        error_text = str(e)

    # ==========================
    #   2. TELEGRAM уведомления
    # ==========================

    prev_status = website.last_status_code
    current_status = status_code

    if prev_status is None:
        prev_status = 200

    # --- TIMEOUT / STATUS = 0 ---
    if current_status == 0:
        if prev_status != 0:
            send_telegram(
                f"⚠️ <b>Сайт притормаживает (timeout)</b>\n"
                f"{website.name}\n{website.url}\n\nОшибка: {error_text}"
            )
        else:
            send_telegram(
                f"🚨 <b>Сайт недоступен (двойной timeout)</b>\n"
                f"{website.name}\n{website.url}\n\nОшибка: {error_text}"
            )

    # --- КРИТИЧЕСКАЯ ОШИБКА 500 ---
    elif current_status == 500:
        send_telegram(
            f"🚨 <b>Критическая ошибка (500)</b>\n"
            f"{website.name}\n{website.url}"
        )

    # --- ЛЮБЫЕ ДРУГИЕ ИЗМЕНЕНИЯ ---
    elif prev_status != current_status:

        if current_status != 200:
            send_telegram(
                f"⚠️ <b>Проблема с сайтом</b>\n"
                f"{website.name}\n{website.url}\n\nHTTP: {current_status}"
            )
        else:
            send_telegram(
                f"✅ <b>Сайт восстановлен</b>\n"
                f"{website.name}\n{website.url}"
            )

    # ==========================
    #      3. Проверка SSL
    # ==========================

    if status_code == 0:
        ssl_info = {
            "valid_from": None,
            "valid_to": None,
            "days_left": None,
            "status": "NO_SSL_CHECK",
        }
    else:
        ssl_info = check_ssl_certificate(website.url)

    # ==========================
    #  4. Проверка домена WHOIS
    # ==========================

    domain_info = check_domain_expiration(website.url)

    # ==========================
    #   5. Обновление модели
    # ==========================

    from django.utils import timezone

    website.last_status_code = status_code
    website.last_response_time = response_time
    website.last_content_snippet = snippet
    website.last_error = error_text
    website.last_checked_at = timezone.now()

    # SSL
    website.ssl_valid_from = ssl_info["valid_from"]
    website.ssl_valid_to = ssl_info["valid_to"]
    website.ssl_days_left = ssl_info["days_left"]
    website.ssl_status = ssl_info["status"]

    # DOMAIN
    website.domain_expiration = domain_info["expiration"]
    website.domain_days_left = domain_info["days_left"]
    website.domain_status = domain_info["status"]

    website.save()

    # ==========================
    #      6. История
    # ==========================

    WebsiteCheck.objects.create(
        website=website,
        status_code=status_code,
        response_time=response_time,
        content_snippet=snippet,
        error=error_text,
    )

    return website


# ============================================================
# ===============        SSL проверка         =================
# ============================================================

def check_ssl_certificate(url: str) -> dict:
    hostname = url.replace("https://", "").replace("http://", "").split("/")[0]
    ctx = ssl.create_default_context()

    try:
        with socket.create_connection((hostname, 443), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()

        valid_from = datetime.strptime(cert["notBefore"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=pytz.UTC)
        valid_to = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=pytz.UTC)

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


# ============================================================
# ===============     WHOIS домен проверка     ===============
# ============================================================

def check_domain_expiration(url: str) -> dict:
    import subprocess
    from datetime import datetime
    import pytz
    import re

    # Получаем основной домен
    hostname = url.replace("https://", "").replace("http://", "").split("/")[0]
    parts = hostname.split(".")

    # Если домен вида xxx.yyy.zz — оставляем только два последних
    if len(parts) >= 2:
        domain = ".".join(parts[-2:])
    else:
        domain = hostname

    try:
        result = subprocess.run(
            ["whois", domain],
            capture_output=True,
            text=True,
            timeout=10
        )
        data = result.stdout

        # Поиск даты
        patterns = [
            r"Expiration Date: (.+)",      # .com, .net, .org
            r"paid-till: (.+)",            # .ru, .рф
            r"expiry date: (.+)",          # европейские домены
        ]

        expiration = None
        for p in patterns:
            match = re.search(p, data, re.IGNORECASE)
            if match:
                expiration_raw = match.group(1).strip()

                # Пытаемся распарсить разные форматы
                for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%d.%m.%Y"):
                    try:
                        expiration = datetime.strptime(expiration_raw, fmt)
                        expiration = expiration.replace(tzinfo=pytz.UTC)
                        break
                    except:
                        continue

                break

        if not expiration:
            return {
                "expiration": None,
                "days_left": None,
                "status": "WHOIS_PARSE_ERROR",
            }

        now = datetime.now(pytz.UTC)
        days_left = (expiration - now).days

        if days_left < 0:
            status = "EXPIRED"
        elif days_left < 7:
            status = "CRITICAL"
        elif days_left < 30:
            status = "EXPIRING_SOON"
        else:
            status = "OK"

        return {
            "expiration": expiration,
            "days_left": days_left,
            "status": status,
        }

    except Exception as e:
        return {
            "expiration": None,
            "days_left": None,
            "status": f"ERROR: {e}",
        }

