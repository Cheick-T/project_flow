"""Development settings."""

from __future__ import annotations

import os

from django.core.management.utils import get_random_secret_key

from .base import *  # noqa: F401,F403

DEBUG = True

if SECRET_KEY == "dev-secret-key":
    SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", get_random_secret_key())

if not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["*"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
INTERNAL_IPS = ["127.0.0.1", "localhost"]
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
