from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm

User = get_user_model()


BASE_INPUT_CLASSES = (
    "w-full px-4 py-3 rounded-lg "
    "border border-slate-300 "
    "focus:ring-2 focus:ring-blue-500 focus:outline-none"
)

class RegisterForm(forms.ModelForm):
    username = forms.CharField(
        label="Имя пользователя",
        widget=forms.TextInput(attrs={
            "class": BASE_INPUT_CLASSES,
            "placeholder": "Имя пользователя",
        })
    )

    email = forms.EmailField(
        label="Email",
        required=True,
        widget=forms.EmailInput(attrs={
            "class": BASE_INPUT_CLASSES,
            "placeholder": "Email",
        })
    )

    password1 = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(attrs={
            "class": BASE_INPUT_CLASSES,
            "placeholder": "Пароль",
        })
    )

    password2 = forms.CharField(
        label="Повторите пароль",
        widget=forms.PasswordInput(attrs={
            "class": BASE_INPUT_CLASSES,
            "placeholder": "Повторите пароль",
        })
    )

    class Meta:
        model = User
        fields = ["username", "email"]

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Этот email уже используется")
        return email

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") != cleaned.get("password2"):
            raise forms.ValidationError("Пароли не совпадают")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.set_password(self.cleaned_data["password1"])

        # 🔒 задел под подтверждение email
        user.is_active = False

        if commit:
            user.save()
        return user

class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Email или логин",
        widget=forms.TextInput(attrs={
            "class": BASE_INPUT_CLASSES,
            "placeholder": "Email или логин",
        })
    )

    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(attrs={
            "class": BASE_INPUT_CLASSES,
            "placeholder": "Пароль",
        })
    )