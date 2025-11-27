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
def check_website(website: Website, timeout: float = 30.0) -> Website:

    status_code = None
    response_time = None
    snippet = ""
    error_text = ""

    # ------------ HTTP CHECK ------------
    try:
        response = requests.get(website.url, timeout=timeout)
        status_code = response.status_code
        response_time = response.elapsed.total_seconds()
        snippet = textwrap.shorten(response.text, width=2000, placeholder=" ...")

        if status_code >= 500:
            error_text = f"Server error {status_code}"

    except RequestException as e:
        status_code = 0
        error_text = str(e)

    # ------------ TELEGRAM ANTI-SPAM LOGIC ------------
    prev = website.last_status_code
    curr = status_code

    if prev is None:
        prev = 200  # считаем первый запуск "в норме"

    # === Упал: 200 → 500 ===
    if prev == 200 and curr == 500:
        send_telegram(
            f"🚨 <b>Сайт упал (500)</b>\n"
            f"{website.name}\n{website.url}"
        )

    # === Восстановился: 500 → 200 ===
    elif prev == 500 and curr == 200:
        send_telegram(
            f"✅ <b>Сайт восстановлен</b>\n"
            f"{website.name}\n{website.url}"
        )

    # === Первый timeout ===
    elif curr == 0 and prev != 0:
        send_telegram(
            f"⚠️ <b>Timeout</b>\n{website.name}\n{website.url}\n{error_text}"
        )

    # === Восстановился после timeout ===
    elif prev == 0 and curr == 200:
        send_telegram(
            f"✅ <b>Сайт восстановился после timeout</b>\n{website.name}"
        )

    # 500→500 или 0→0 или 200→200 — молчим


    # ------------ SSL CHECK ------------
    if curr == 0:
        ssl_info = {
            "valid_from": None, "valid_to": None,
            "days_left": None, "status": "NO_SSL_CHECK"
        }
    else:
        ssl_info = check_ssl_certificate(website.url)

    # ------------ DOMAIN CHECK ------------
    domain_info = check_domain_expiration(website.url)

    # ------------ UPDATE DB ------------
    from django.utils import timezone

    website.last_status_code = curr
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
        status_code=curr,
        response_time=response_time,
        content_snippet=snippet,
        error=error_text,
    )

    return website
