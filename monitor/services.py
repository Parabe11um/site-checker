import textwrap
import ssl
import socket
import subprocess
import re

from datetime import datetime, timedelta
from statistics import median
from urllib.parse import urlparse

import pytz
import tldextract
import urllib3.util.connection as urllib3_connection


def force_ipv4():
    return socket.AF_INET


urllib3_connection.allowed_gai_family = force_ipv4
urllib3_connection.HAS_IPV6 = False

import requests
from requests.exceptions import RequestException

from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Avg

from monitor.models import Site, UserSite, TelegramSettings, EmailSettings
from monitor.models_check import SiteCheck
from sitechecker.telegram import send_telegram

# -----------------------------
#  EXTRACT ROOT DOMAIN
# -----------------------------
def extract_domain(url: str) -> str:
    ext = tldextract.extract(url)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}"
    return ext.registered_domain or url


# -----------------------------
#  ALERT RULES
# -----------------------------
ALERT_AFTER_FAILED_CHECKS = 2


def is_success_status(code) -> bool:
    """
    Успешным считаем только 2xx.
    3xx / 4xx / 5xx / 0 считаем проблемой.
    """
    return code is not None and 200 <= int(code) < 300


def is_problem_status(code) -> bool:
    return not is_success_status(code)


def count_previous_problem_checks(site: Site, limit: int = 10) -> int:
    """
    Считает, сколько последних проверок подряд были проблемными.
    Важно: текущая проверка еще не записана в SiteCheck,
    поэтому считаем только историю ДО текущей проверки.
    """
    count = 0

    for check in site.checks.order_by("-checked_at")[:limit]:
        if is_problem_status(check.status_code):
            count += 1
        else:
            break

    return count


def get_problem_title_and_subject(status_code) -> tuple[str, str]:
    if status_code == 0:
        return "⚠️ Таймаут запроса", "Таймаут запроса"

    if 300 <= status_code < 400:
        return "⚠️ Редирект сайта", "Редирект сайта"

    if 400 <= status_code < 500:
        return "⚠️ Ошибка сайта 4xx", "Ошибка сайта 4xx"

    if 500 <= status_code < 600:
        return "🚨 Ошибка сайта 5xx", "Ошибка сайта 5xx"

    return "⚠️ Проблема с сайтом", "Проблема с сайтом"


def format_error_message(
    *,
    title: str,
    site_name: str,
    url: str,
    status_code=None,
    response_time=None,
    error_text=None,
    snippet=None,
) -> str:
    lines = [
        title,
        "",
        site_name,
        url,
    ]

    if status_code is not None:
        lines.append(f"HTTP статус: {status_code}")

    if response_time is not None:
        lines.append(f"Время отклика: {response_time:.2f} c")

    if error_text:
        lines.append(f"Ошибка: {error_text}")

    if snippet:
        lines.append("")
        lines.append("Фрагмент ответа:")
        lines.append(textwrap.shorten(snippet, width=500, placeholder=" ..."))

    return "\n".join(lines)

# -----------------------------
#  CHECK DOMAIN EXPIRATION
# -----------------------------
def check_domain_expiration(url: str) -> dict:
    root_domain = extract_domain(url)

    try:
        result = subprocess.run(
            ["whois", root_domain],
            capture_output=True,
            text=True,
            timeout=10
        )
        data = result.stdout

        patterns = [
            r"Expiration Date: (.+)",
            r"expiry date: (.+)",
            r"paid-till: (.+)",
        ]

        expiration = None
        for p in patterns:
            match = re.search(p, data, re.IGNORECASE)
            if match:
                raw = match.group(1).strip()

                # ----- TRY MULTIPLE FORMATS -----
                for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%d.%m.%Y"):
                    try:
                        expiration = datetime.strptime(raw, fmt)
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

    except Exception:
        return {
            "expiration": None,
            "days_left": None,
            "status": "ERROR",
            "raw": "",
        }

# -----------------------------
#  CHECK SSL
# -----------------------------
def check_ssl_certificate(url: str) -> dict:
    parsed = urlparse(url)
    hostname = parsed.hostname

    if not hostname:
        return {
            "valid_from": None,
            "valid_to": None,
            "days_left": None,
            "status": "ERROR",
        }

    try:
        hostname_idna = hostname.encode("idna").decode("ascii")
    except Exception:
        hostname_idna = hostname

    ctx = ssl.create_default_context()

    try:
        # Принудительно получаем IPv4
        ip_address = socket.gethostbyname(hostname_idna)

        # Подключаемся к IPv4, но SNI оставляем по домену
        with socket.create_connection((ip_address, 443), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname_idna) as ssock:
                cert = ssock.getpeercert()

        valid_from = datetime.strptime(
            cert["notBefore"],
            "%b %d %H:%M:%S %Y %Z"
        ).replace(tzinfo=pytz.UTC)

        valid_to = datetime.strptime(
            cert["notAfter"],
            "%b %d %H:%M:%S %Y %Z"
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
            "status": "ERROR",
        }

# -----------------------------
#  MAIN WEBSITE CHECK
# -----------------------------
def check_site(site: Site, timeout: float = 25.0) -> Site:
    status_code = None
    response_time = None
    snippet = ""
    error_text = ""

    parsed = urlparse(site.url)
    hostname = parsed.hostname

    ip_address = None
    if hostname:
        try:
            ip_address = socket.gethostbyname(hostname)
        except Exception:
            ip_address = None

    old_ip = site.ip_address
    ip_changed = ip_address is not None and ip_address != old_ip

    try:
        response = requests.get(
            site.url,
            timeout=(7, timeout),
            allow_redirects=False,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; CheckyWebMonitor/1.0)"
            }
        )

        status_code = response.status_code
        response_time = response.elapsed.total_seconds()
        snippet = textwrap.shorten(response.text, width=2000, placeholder=" ...")

        if status_code >= 300:
            error_text = response.reason or f"HTTP {status_code}"

            if 300 <= status_code < 400:
                location = response.headers.get("Location")
                if location:
                    error_text = f"{error_text}. Location: {location}"

    except RequestException as e:
        status_code = 0
        error_text = str(e)

    prev = site.last_status_code
    curr = status_code

    if prev is None:
        prev = 200

    # Сколько проблемных проверок подряд было ДО текущей проверки
    previous_problem_count = count_previous_problem_checks(site)

    # Сколько проблемных проверок подряд будет С УЧЕТОМ текущей
    current_problem_count = (
        previous_problem_count + 1
        if is_problem_status(curr)
        else 0
    )

    # Ошибку отправляем только на 2-й подряд проблемной проверке
    should_send_problem_alert = (
        is_problem_status(curr)
        and current_problem_count == ALERT_AFTER_FAILED_CHECKS
    )

    # Восстановление отправляем только после подтвержденной проблемы,
    # то есть когда до текущей успешной проверки было 2+ ошибок подряд
    should_send_recovery_alert = (
        is_success_status(curr)
        and previous_problem_count >= ALERT_AFTER_FAILED_CHECKS
    )

    if should_send_problem_alert or should_send_recovery_alert:
        subscriptions = UserSite.objects.filter(
            site=site,
            notify_enabled=True
        ).select_related("user")

        sent_user_ids = set()

        for sub in subscriptions:
            user = sub.user

            # Защита от дублей, если у одного пользователя вдруг несколько связей с сайтом
            if user.id in sent_user_ids:
                continue

            sent_user_ids.add(user.id)

            name = sub.name or site.url

            if should_send_problem_alert:
                title, subject = get_problem_title_and_subject(curr)

                event_type = "timeout" if curr == 0 else "down"

                notify_user(
                    user=user,
                    subject=subject,
                    message=format_error_message(
                        title=title,
                        site_name=name,
                        url=site.url,
                        status_code=curr,
                        response_time=response_time,
                        error_text=error_text,
                        snippet=snippet,
                    ),
                    event_type=event_type,
                )

            elif should_send_recovery_alert:
                notify_user(
                    user=user,
                    subject="✅ Сайт восстановлен",
                    message=(
                        "✅ Сайт восстановлен\n\n"
                        f"{name}\n"
                        f"{site.url}\n"
                        f"HTTP статус: {curr}"
                    ),
                    event_type="up",
                )

    # ------------ SSL CHECK ------------
    if curr == 0:
        ssl_info = {
            "valid_from": None,
            "valid_to": None,
            "days_left": None,
            "status": "Нет данных",
        }
    elif not site.url.startswith("https://"):
        ssl_info = {
            "valid_from": None,
            "valid_to": None,
            "days_left": None,
            "status": "NOT_HTTPS",
        }
    else:
        ssl_info = check_ssl_certificate(site.url)

    # ------------ DOMAIN CHECK ------------
    domain_info = check_domain_expiration(site.url)

    # ------------ UPDATE DB ------------
    from django.utils import timezone

    site.last_status_code = curr
    site.last_response_time = response_time
    site.last_content_snippet = snippet
    site.last_error = error_text
    site.last_checked_at = timezone.now()
    site.ip_address = ip_address


    # SSL
    site.ssl_valid_from = ssl_info["valid_from"]
    site.ssl_valid_to = ssl_info["valid_to"]
    site.ssl_days_left = ssl_info["days_left"]
    site.ssl_status = ssl_info["status"]

    # Domain
    site.domain_expiration = domain_info["expiration"]
    site.domain_days_left = domain_info["days_left"]
    site.domain_status = domain_info["status"]

    site.save()

    needs_refresh = (
            not site.ipinfo_updated_at or
            site.ipinfo_updated_at < timezone.now() - timedelta(days=7)
    )

    if (ip_changed or needs_refresh) and site.ip_address:
        enrich_ipinfo(site)

    # История
    SiteCheck.objects.create(
        site=site,
        status_code=curr,
        response_time=response_time,
        content_snippet=snippet,
        error=error_text,
    )

    qs = site.checks.filter(response_time__isnull=False)

    # Среднее (SQL)
    site.avg_response_time = qs.aggregate(
        avg=Avg("response_time")
    )["avg"]

    # Медиана (Python, с ограничением)
    MEDIAN_LIMIT = 1000

    times = list(
        qs.order_by("-checked_at")
        .values_list("response_time", flat=True)[:MEDIAN_LIMIT]
    )
    times.sort()

    site.median_response_time = median(times) if times else None

    site.save(update_fields=[
        "avg_response_time",
        "median_response_time",
    ])

    return site

def notify_user(user, subject: str, message: str, event_type: str = "down"):
    """
    Унифицированная отправка уведомлений:
    - Telegram, если канал включён и разрешён тип уведомления
    - Email, если канал включён и разрешён тип уведомления
    """

    flag_map = {
        "down": "notify_down",
        "timeout": "notify_timeout",
        "up": "notify_up",
    }

    flag_name = flag_map.get(event_type, "notify_down")

    # --- TELEGRAM ---
    tg = getattr(user, "telegram_settings", None)

    if (
        tg
        and tg.is_active
        and getattr(tg, flag_name, False)
    ):
        send_telegram(user, message)

    # --- EMAIL ---
    email_settings = EmailSettings.objects.filter(user=user).first()

    if (
        email_settings
        and email_settings.is_active
        and getattr(email_settings, flag_name, False)
        and getattr(user, "email", None)
    ):
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )


def get_ipinfo(ip: str) -> dict:
    try:
        r = requests.get(
            f"https://ipinfo.io/{ip}/json",
            timeout=5
        )
        data = r.json()

        return {
            "provider": data.get("org"),
            "country": data.get("country"),
        }
    except Exception:
        return {}


def enrich_ipinfo(site: Site):
    if not site.ip_address:
        return

    data = get_ipinfo(site.ip_address)
    if not data:
        return

    site.ip_provider = data.get("provider", "")
    site.ip_country = data.get("country", "")
    site.ipinfo_updated_at = timezone.now()

    site.save(update_fields=[
        "ip_provider",
        "ip_country",
        "ipinfo_updated_at"
    ])