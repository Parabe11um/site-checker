import textwrap
import requests
from requests.exceptions import RequestException
from django.utils import timezone
from monitor.models import Site, UserSite
from monitor.models_check import SiteCheck
import ssl
import socket
from datetime import datetime
import pytz
from sitechecker.telegram import send_telegram
import tldextract
import subprocess
import re


# -----------------------------
#  EXTRACT ROOT DOMAIN
# -----------------------------
def extract_domain(url: str) -> str:
    ext = tldextract.extract(url)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}"
    return ext.registered_domain or url


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

    except Exception as e:
        return {
            "expiration": None,
            "days_left": None,
            "status": f"ERROR: {e}",
        }


# -----------------------------
#  CHECK SSL
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
        return {
            "valid_from": None,
            "valid_to": None,
            "days_left": None,
            "status": f"ERROR: {e}",
        }


# -----------------------------
#  MAIN WEBSITE CHECK
# -----------------------------
def check_site(site: Site, timeout: float = 30.0) -> Site:
    status_code = None
    response_time = None
    snippet = ""
    error_text = ""

    try:
        response = requests.get(site.url, timeout=timeout)
        status_code = response.status_code
        response_time = response.elapsed.total_seconds()
        snippet = textwrap.shorten(response.text, width=2000, placeholder=" ...")

        if status_code >= 500:
            error_text = f"Server error {status_code}"

    except RequestException as e:
        status_code = 0
        error_text = str(e)

    prev = site.last_status_code
    curr = status_code

    if prev is None:
        prev = 200


    if prev != curr:
        subscriptions = UserSite.objects.filter(site=site, notify_enabled=True)

        for sub in subscriptions:
            user = sub.user
            name = sub.name or site.url

            if prev == 200 and curr >= 500:
                send_telegram(
                    user,
                    f"🚨 <b>Сайт упал</b>\n{name}\n{site.url}"
                )

            elif prev >= 500 and curr == 200:
                send_telegram(
                    user,
                    f"✅ <b>Сайт восстановлен</b>\n{name}"
                )

            elif curr == 0 and prev not in (0, None):
                send_telegram(
                    user,
                    f"⚠️ <b>Timeout</b>\n{name}\n{error_text}"
                )

            elif prev == 0 and curr == 200:
                send_telegram(
                    user,
                    f"✅ <b>Сайт восстановился</b>\n{name}"
                )



    # ------------ SSL CHECK ------------
    if curr == 0:
        ssl_info = {
            "valid_from": None, "valid_to": None,
            "days_left": None, "status": "NO_SSL_CHECK"
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

    # История
    SiteCheck.objects.create(
        site=site,
        status_code=curr,
        response_time=response_time,
        content_snippet=snippet,
        error=error_text,
    )

    return site
