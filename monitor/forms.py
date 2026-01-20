from django import forms
from urllib.parse import urlparse
from .models import TelegramSettings


BASE_INPUT_CLASSES = (
    "w-full rounded-xl border border-slate-300 bg-white/80 px-4 py-3 "
    "text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
)

FORBIDDEN_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
}

class AddSiteForm(forms.Form):
    name = forms.CharField(
        label="Название сайта",
        max_length=255,
        widget=forms.TextInput(attrs={
            "class": BASE_INPUT_CLASSES,
            "placeholder": "Например: Мой сайт",
        })
    )

    url = forms.URLField(
        label="URL",
        widget=forms.URLInput(attrs={
            "class": BASE_INPUT_CLASSES,
            "placeholder": "example.ru",
            "inputmode": "url",
            "autocomplete": "url",
        })
    )

    def clean_url(self):
        url = self.cleaned_data["url"].strip()

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        parsed = urlparse(url)
        host = parsed.hostname

        if not host:
            raise forms.ValidationError("Введите корректный URL")

        if host in FORBIDDEN_HOSTS:
            raise forms.ValidationError("Локальные адреса запрещены")

        if host.endswith(".local"):
            raise forms.ValidationError("Домены .local запрещены")

        return url

class TelegramSettingsForm(forms.ModelForm):
    class Meta:
        model = TelegramSettings
        fields = [
            "token",
            "chat_id",
            "is_active",
            "notify_down",
            "notify_up",
            "notify_timeout",
            "email_enabled",
        ]
        widgets = {
            "token": forms.TextInput(attrs={
                "class": "border rounded px-3 py-2 w-full",
            }),
            "chat_id": forms.TextInput(attrs={
                "class": "border rounded px-3 py-2 w-full",
            }),
        }