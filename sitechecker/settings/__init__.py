import os

env = os.getenv("DJANGO_ENV", "production")

if env == "local":
    from .local import *
else:
    from .production import *
