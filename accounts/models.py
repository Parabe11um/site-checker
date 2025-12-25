from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_CHOICES = (
        ("user", "Обычный пользователь"),
        ("staff", "Персонал"),
        ("admin", "Администратор"),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="user")
    email = models.EmailField(unique=True)

    REQUIRED_FIELDS = ["email"]

    def __str__(self):
        return self.username