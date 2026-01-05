from django import forms
from .models import Website, TelegramSettings

class AddSiteForm(forms.Form):
    name = forms.CharField(
        label="Название сайта",
        max_length=255,
        widget=forms.TextInput(attrs={
            "class": "border rounded px-3 py-2 w-full",
            "placeholder": "Например: Мой сайт",
        })
    )

    url = forms.URLField(
        label="URL",
        widget=forms.URLInput(attrs={
            "class": "border rounded px-3 py-2 w-full",
            "placeholder": "https://example.com",
        })
    )

    def clean_url(self):
        url = self.cleaned_data["url"].strip()

        if not url.startswith(("http://", "https://")):
            raise forms.ValidationError("URL должен начинаться с http:// или https://")

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
        ]
        widgets = {
            "token": forms.TextInput(attrs={
                "class": "border rounded px-3 py-2 w-full",
            }),
            "chat_id": forms.TextInput(attrs={
                "class": "border rounded px-3 py-2 w-full",
            }),
        }
