import textwrap
import requests
from requests.exceptions import RequestException
from django.utils import timezone
from monitor.models import Site, UserSite, TelegramSettings
from monitor.models_check import SiteCheck
import ssl
import socket
from datetime import datetime, timedelta
import pytz
from sitechecker.telegram import send_telegram
import tldextract
import subprocess
import re
from django.core.mail import send_mail
from django.conf import settings
from urllib.parse import urlparse
from django.db.models import Avg
from statistics import median


# -----------------------------
#  HELPERS
# -----------------------------
def extract_domain(url: str) -> str:
    ext = tldextract.extract(url)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}"
    return ext.registered_domain or url


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

    if response_time:
        lines.append(f"Время отклика: {response_time:.2f} c")

    if error_text:
        lines.append(f"Ошибка: {error_text}")

    if snippet:
        lines.append("")
        lines.append("Фрагмент ответа:")
        lines.append(textwrap.shorten(snippet, 500))

    return "\n".join(lines)


# -----------------------------
#  DOMAIN EXPIRATION
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
                for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%d.%m.%Y"):
                    try:
                        expiration = datetime.strptime(raw, fmt).replace(tzinfo=pytz.UTC)
                        break
                    except ValueError:
                        continue
                break

        if not expiration:
            return {"expiration": None, "days_left": None, "status": "WHOIS_PARSE_ERROR"}

        days_left = (expiration - datetime.now(pytz.UTC)).days

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
        return {"expiration": None, "days_left": None, "status": f"ERROR: {e}"}


# -----------------------------
#  SSL CHECK
# -----------------------------
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
        return {"valid_from": None, "valid_to": None, "days_left": None, "status": f"ERROR: {e}"}


# -----------------------------
#  MAIN CHECK
# -----------------------------
def check_site(site: Site, timeout: float = 30.0) -> Site:
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
            pass

    old_ip = site.ip_address
    ip_changed = ip_address and ip_address != old_ip

    try:
        response = requests.get(site.url, timeout=timeout)
        status_code = response.status_code
        response_time = response.elapsed.total_seconds()
        snippet = response.text

        if status_code >= 500:
            error_text = response.reason

    except RequestException as e:
        status_code = 0
        error_text = str(e)

    prev = site.last_status_code or 200
    curr = status_code

    if prev != curr:
        subscriptions = UserSite.objects.filter(site=site, notify_enabled=True)

        for sub in subscriptions:
            user = sub.user
            name = sub.name or site.url
            tg = getattr(user, "telegram_settings", None)

            if not tg or not tg.is_active:
                continue

            # 🔴 DOWN
            if prev == 200 and curr >= 500 and tg.notify_down:
                msg = format_error_message(
                    title="🚨 Сайт недоступен",
                    site_name=name,
                    url=site.url,
                    status_code=curr,
                    response_time=response_time,
                    error_text=error_text,
                    snippet=snippet,
                )
                notify_user(user, "Сайт недоступен", msg)

            # ⚠️ TIMEOUT
            elif curr == 0 and prev != 0 and tg.notify_timeout:
                msg = format_error_message(
                    title="⚠️ Таймаут запроса",
                    site_name=name,
                    url=site.url,
                    error_text=error_text,
                )
                notify_user(user, "Таймаут запроса", msg)

            # 🟢 RECOVERED
            elif prev >= 500 and curr == 200 and tg.notify_up:
                notify_user(
                    user,
                    "Сайт восстановлен",
                    f"✅ Сайт восстановлен\n\n{name}\n{site.url}"
                )

    # ---- SSL / DOMAIN ----
    ssl_info = check_ssl_certificate(site.url) if curr != 0 else {}
    domain_info = check_domain_expiration(site.url)

    site.last_status_code = curr
    site.last_response_time = response_time
    site.last_content_snippet = textwrap.shorten(snippet, 2000)
    site.last_error = error_text
    site.last_checked_at = timezone.now()
    site.ip_address = ip_address

    site.ssl_valid_from = ssl_info.get("valid_from")
    site.ssl_valid_to = ssl_info.get("valid_to")
    site.ssl_days_left = ssl_info.get("days_left")
    site.ssl_status = ssl_info.get("status")

    site.domain_expiration = domain_info.get("expiration")
    site.domain_days_left = domain_info.get("days_left")
    site.domain_status = domain_info.get("status")

    site.save()

    if (ip_changed or not site.ipinfo_updated_at or
        site.ipinfo_updated_at < timezone.now() - timedelta(days=7)):
        enrich_ipinfo(site)

    SiteCheck.objects.create(
        site=site,
        status_code=curr,
        response_time=response_time,
        content_snippet=snippet,
        error=error_text,
    )

    qs = site.checks.filter(response_time__isnull=False)

    site.avg_response_time = qs.aggregate(avg=Avg("response_time"))["avg"]

    times = list(qs.order_by("-checked_at").values_list("response_time", flat=True)[:1000])
    times.sort()
    site.median_response_time = median(times) if times else None

    site.save(update_fields=["avg_response_time", "median_response_time"])

    return site


# -----------------------------
#  NOTIFY
# -----------------------------
def notify_user(user, subject: str, message: str):
    tg = getattr(user, "telegram_settings", None)

    if tg and tg.is_active:
        send_telegram(user, message)

    if getattr(user, "email", None):
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )


# -----------------------------
#  IP INFO
# -----------------------------
def get_ipinfo(ip: str) -> dict:
    try:
        r = requests.get(f"https://ipinfo.io/{ip}/json", timeout=5)
        return r.json()
    except Exception:
        return {}


def enrich_ipinfo(site: Site):
    if not site.ip_address:
        return

    data = get_ipinfo(site.ip_address)
    if not data:
        return

    site.ip_provider = data.get("org", "")
    site.ip_country = data.get("country", "")
    site.ipinfo_updated_at = timezone.now()
    site.save(update_fields=["ip_provider", "ip_country", "ipinfo_updated_at"])
