import requests
from monitor.models import TelegramSettings


def get_settings():
    try:
        return TelegramSettings.objects.first()
    except:
        return None


def send_telegram(msg: str):
    print("=== DEBUG: send_telegram() called ===")

    cfg = get_settings()
    if not cfg:
        print("Telegram settings not configured.")
        return

    url = f"https://api.telegram.org/bot{cfg.token}/sendMessage"

    r = requests.post(url, data={
        "chat_id": cfg.chat_id.strip(),
        "text": msg,
        "parse_mode": "HTML"
    })

    print("TELEGRAM RESPONSE:", r.status_code, r.text)


# def send_telegram(msg: str):
#     cfg = get_settings()
#     if not cfg:
#         print("Telegram settings not configured.")
#         return
#
#     url = f"https://api.telegram.org/bot{cfg.token}/sendMessage"
#     requests.post(url, data={
#         "chat_id": cfg.chat_id,
#         "text": msg,
#         "parse_mode": "HTML"
#     })


def send_photo(path: str, caption: str = None):
    cfg = get_settings()
    if not cfg:
        print("Telegram settings not configured.")
        return

    url = f"https://api.telegram.org/bot{cfg.token}/sendPhoto"
    with open(path, "rb") as photo:
        requests.post(
            url,
            data={"chat_id": cfg.chat_id, "caption": caption or ""},
            files={"photo": photo}
        )
