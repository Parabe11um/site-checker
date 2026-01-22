import textwrap
import requests
from requests.exceptions import RequestException
from django.utils import timezone
from monitor.models import Site, UserSite
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


def classify_status(code: int | None) -> str:
    if code is None:
        return "unknown"
    if code == 0:
        return "timeout"
    if 200 <= code < 300:
        return "ok"
    if 300 <= code < 400:
        return "redirect"
    if 400 <= code < 500:
        return "client_error"
    if 500 <= code < 600:
        return "server_error"
    return "unknown"


def format_error_message(
    *,
    title: str,
    site_name: str,
    url: str,
    status_code=None,
    response_time=None,
    error_text=None,
    snippet=None,
    redirect_to: str | None = None,
) -> str:
    lines = [
        title,
        "",
        site_name,
        url,
    ]

    if status_code is not None:
        lines.append(f"HTTP статус: {status_code}")

    if redirect_to:
        lines.append(f"Location: {redirect_to}")

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
    redirect_to = None

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
        # ВАЖНО: allow_redirects=False чтобы ловить 301/302/307/308
        response = requests.get(site.url, timeout=timeout, allow_redirects=False)
        status_code = response.status_code
        response_time = response.elapsed.total_seconds()

        # Текст/сниппет может быть большим — держим в переменной как есть,
        # но в БД будем сохранять короткую версию.
        snippet = response.text or ""

        # reason полезен для 3xx/4xx/5xx
        if status_code >= 300:
            error_text = response.reason or ""

        if 300 <= status_code < 400:
            redirect_to = response.headers.get("Location")

    except RequestException as e:
        status_code = 0
        error_text = str(e)

    prev = site.last_status_code or 200
    curr = status_code

    prev_type = classify_status(prev)
    curr_type = classify_status(curr)

    # Уведомляем, когда:
    # - статус-код изменился
    # - и текущий статус НЕ ok
    # - либо произошло восстановление (ok после не-ok)
    if prev != curr:
        subscriptions = UserSite.objects.filter(site=site, notify_enabled=True)

        for sub in subscriptions:
            user = sub.user
            name = sub.name or site.url
            tg = getattr(user, "telegram_settings", None)

            if not tg or not tg.is_active:
                continue

            # ✅ восстановление
            if curr_type == "ok" and prev_type != "ok" and tg.notify_up:
                notify_user(
                    user,
                    "Сайт восстановлен",
                    f"✅ Сайт восстановлен\n\n{name}\n{site.url}"
                )
                continue

            # если текущий не ok — шлём уведомление (в формате с кодом и текстом)
            if curr_type != "ok" and tg.notify_down:
                if curr_type in ("server_error", "timeout"):
                    title = "🚨 Ошибка сайта"
                    subj = "Ошибка сайта"
                else:
                    # redirect / client_error / unknown
                    title = "⚠️ Проблема с сайтом"
                    subj = "Проблема с сайтом"

                msg = format_error_message(
                    title=title,
                    site_name=name,
                    url=site.url,
                    status_code=curr,
                    response_time=response_time,
                    error_text=error_text,
                    snippet=snippet,
                    redirect_to=redirect_to,
                )
                notify_user(user, subj, msg)

    # ---- UPDATE SITE ----
    ssl_info = check_ssl_certificate(site.url) if curr != 0 else {}
    domain_info = check_domain_expiration(site.url)

    site.last_status_code = curr
    site.last_response_time = response_time
    site.last_content_snippet = textwrap.shorten(snippet, 2000, placeholder=" ...")
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

    if ip_changed or not site.ipinfo_updated_at or site.ipinfo_updated_at < timezone.now() - timedelta(days=7):
        enrich_ipinfo(site)

    # История — тоже кладём короткий сниппет, чтобы не раздувать таблицу
    SiteCheck.objects.create(
        site=site,
        status_code=curr,
        response_time=response_time,
        content_snippet=textwrap.shorten(snippet, 2000, placeholder=" ..."),
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
