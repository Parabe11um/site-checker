import requests
from monitor.models import TelegramSettings


def get_user_settings(user):
    """
    Получить Telegram-настройки конкретного пользователя
    """
    try:
        return TelegramSettings.objects.get(user=user, is_active=True)
    except TelegramSettings.DoesNotExist:
        return None


def send_telegram(user, msg: str):
    """
    Отправка текстового сообщения пользователю в Telegram
    """
    cfg = get_user_settings(user)
    if not cfg:
        return  # пользователь не подключил Telegram

    url = f"https://api.telegram.org/bot{cfg.token}/sendMessage"

    try:
        requests.post(
            url,
            json={
                "chat_id": cfg.chat_id,
                "text": msg,
                "parse_mode": "HTML",
            },
            timeout=5
        )
    except Exception:
        # в проде можно залогировать
        pass


def send_photo(user, path: str, caption: str | None = None):
    """
    Отправка фото пользователю в Telegram
    """
    cfg = get_user_settings(user)
    if not cfg:
        return

    url = f"https://api.telegram.org/bot{cfg.token}/sendPhoto"

    try:
        with open(path, "rb") as photo:
            requests.post(
                url,
                data={
                    "chat_id": cfg.chat_id,
                    "caption": caption or "",
                },
                files={"photo": photo},
                timeout=10
            )
    except Exception:
        pass
