import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-cle-a-changer-en-production")
DEBUG = os.environ.get("DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o]

# Render fournit l'adresse publique du service.
_RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
if _RENDER_URL:
    CSRF_TRUSTED_ORIGINS.append(_RENDER_URL)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "gestion",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "atelier.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "gestion.context.atelier",
    ]},
}]

WSGI_APPLICATION = "atelier.wsgi.application"

# DATABASE_URL (PostgreSQL sur Render) ; à défaut, un fichier SQLite local.
DATABASES = {"default": dj_database_url.config(default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=600)}

LANGUAGE_CODE = "fr"
TIME_ZONE = "Africa/Douala"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/connexion/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/connexion/"

# Adresse publique de l'application : c'est elle qui est encodée dans les QR codes.
SITE_URL = (os.environ.get("SITE_URL") or _RENDER_URL or "http://127.0.0.1:8000").rstrip("/")
ATELIER_NOM = os.environ.get("ATELIER_NOM", "Atelier de couture")

# Tant que le contrat Orange Money / Mobile Money n'est pas signé : laisser à 0 (caisse uniquement).
PAIEMENT_MOBILE_ACTIF = os.environ.get("PAIEMENT_MOBILE_ACTIF", "0") == "1"

# --- Paiement : numéros affichés au membre qui choisit Orange Money ou Mobile Money
ORANGE_MONEY_NUMERO = os.environ.get("ORANGE_MONEY_NUMERO", "")
MOMO_NUMERO = os.environ.get("MOMO_NUMERO", "")

# --- Alertes SMS + WhatsApp
# "console" : les messages sont seulement écrits dans les journaux (essais). "twilio" : envoi réel.
NOTIF_BACKEND = os.environ.get("NOTIF_BACKEND", "console")
PAYS_INDICATIF = os.environ.get("PAYS_INDICATIF", "237")
ADMIN_TELEPHONES = [t for t in os.environ.get("ADMIN_TELEPHONES", "").split(",") if t.strip()]
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_SMS_FROM = os.environ.get("TWILIO_SMS_FROM", "")            # ex. +1555...
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "")  # ex. +1415...
