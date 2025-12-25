from django import forms
from .models import Website, TelegramSettings

class WebsiteForm(forms.ModelForm):
    class Meta:
        model = Website
        fields = ["name", "url"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "border rounded px-3 py-2 w-full"
            }),
            "url": forms.URLInput(attrs={
                "class": "border rounded px-3 py-2 w-full"
            }),
        }


class TelegramSettingsForm(forms.ModelForm):
    class Meta:
        model = TelegramSettings
        fields = ["token", "chat_id"]
        widgets = {
            "token": forms.TextInput(attrs={
                "class": "border rounded px-3 py-2 w-full"
            }),
            "chat_id": forms.TextInput(attrs={
                "class": "border rounded px-3 py-2 w-full"
            }),
        }
