import textwrap
import requests
from requests.exceptions import RequestException
from .models import Website
from .models_check import WebsiteCheck
import ssl
import socket
from datetime import datetime
import pytz
from sitechecker.telegram import send_telegram
import tldextract
import subprocess
import re


def extract_domain(url: str) -> str:
    """
    Возвращает корневой домен:
    https://bar.chaochay.ru → chaochay.ru
    https://www.site.co.uk → site.co.uk
    """
    ext = tldextract.extract(url)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}"
    return ext.registered_domain or url


def check_domain_expiration(url: str) -> dict:
    """
    Проверяет дату окончания регистрации домена.
    """

    root_domain = extract_domain(url)

    try:
        result = subprocess.run(
            ["whois", root_domain],
            capture_output=True,
            text=True,
            timeout=10
        )
        data = result.stdout

        # Популярные шаблоны дат
        patterns = [
            r"Expiration Date: (.+)",
            r"expiry date: (.+)",
            r"paid-till: (.+)",
        ]

        expiration = None
        for p in patterns:
            match = re.search(p, data, re.IGNORECASE)
            if match:
                expiration_raw = match.group(1).strip()

                # Попытка распарсить несколько форматов даты
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
                "raw": data,
            }

        now = datetime.now(pytz.UTC)
        days_left = (expiration - now).days

        # Статус
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
            "raw": data,
        }

    except Exception as e:
        return {
            "expiration": None,
            "days_left": None,
            "status": f"ERROR: {e}",
        }


def check_website(website: Website, timeout: float = 10.0) -> Website:
    """
    Основной мониторинг сайта + SSL + домен.
    """

    status_code = None
    response_time = None
    snippet = ""
    error_text = ""

    # --- HTTP ---
    try:
        response = requests.get(website.url, timeout=timeout)
        status_code = response.status_code
        response_time = response.elapsed.total_seconds()
        snippet = textwrap.shorten(response.text, width=2000, placeholder=" ...")

        if 500 <= status_code <= 599:
            error_text = f"Server error {status_code}"

    except RequestException as e:
        status_code = 0
        error_text = str(e)

    # --- TELEGRAM уведомления ---
    prev_status = website.last_status_code
    current_status = status_code

    if prev_status is None:
        prev_status = 200

    if current_status == 0:
        if prev_status != 0:
            send_telegram(f"⚠️ Timeout: {website.name}\n{website.url}\n{error_text}")
        else:
            send_telegram(f"🚨 Двойной timeout: {website.name}\n{website.url}\n{error_text}")

    elif current_status == 500:
        send_telegram(f"🚨 500 ошибка: {website.name}\n{website.url}")

    elif prev_status != current_status:
        if current_status != 200:
            send_telegram(f"⚠️ Ошибка {current_status}: {website.name}\n{website.url}")
        else:
            send_telegram(f"✅ Восстановлен: {website.name}")

    # --- SSL ---
    if status_code == 0:
        ssl_info = {"valid_from": None, "valid_to": None, "days_left": None, "status": "NO_SSL_CHECK"}
    else:
        ssl_info = check_ssl_certificate(website.url)

    # --- DOMAIN ---
    domain_info = check_domain_expiration(website.url)

    # --- UPDATE DB ---
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

    # Domain
    website.domain_expiration = domain_info["expiration"]
    website.domain_days_left = domain_info["days_left"]
    website.domain_status = domain_info["status"]

    website.save()

    # История
    WebsiteCheck.objects.create(
        website=website,
        status_code=status_code,
        response_time=response_time,
        content_snippet=snippet,
        error=error_text,
    )

    return website