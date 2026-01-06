import os

ENV = os.getenv("DJANGO_ENV", "local")

if ENV == "production":
    from .production import *
else:
    from .local import *
