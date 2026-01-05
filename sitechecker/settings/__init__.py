import os

env = os.getenv("DJANGO_ENV", "local")

if env == "production":
    from .production import *
else:
    from .local import *
