# core/settings.py
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = os.getenv('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '').split(',')

if not SECRET_KEY or 'django-insecure' in (SECRET_KEY or ''):
    import warnings
    warnings.warn(
        'SECRET_KEY ausente ou insegura no .env — configure uma chave aleatória '
        'forte antes de ir para produção.'
    )

csrf_env = os.getenv('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in csrf_env.split(',') if origin.strip()]

# Apps
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

LOCAL_APPS = [
    'apps.accounts',
    'apps.products',
    'apps.payments',
    'apps.delivery',
    'apps.cart',
]

INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.accounts.middleware.TwoFactorVerificationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],  # pasta global de templates
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# Banco de dados (SQLite em dev, PostgreSQL em produção — definido via .env)
DATABASES = {
    'default': {
        'ENGINE': os.getenv('DB_ENGINE', 'django.db.backends.sqlite3'),
        'NAME': os.getenv('DB_NAME', str(BASE_DIR / 'db.sqlite3')),
        'USER': os.getenv('DB_USER', ''),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', ''),
        'PORT': os.getenv('DB_PORT', ''),
    }
}

# Segurança HTTP (habilite no .env quando estiver atrás de proxy/nginx + HTTPS)
SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'False') == 'True'
SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'False') == 'True'
CSRF_COOKIE_SECURE = os.getenv('CSRF_COOKIE_SECURE', 'False') == 'True'
SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = (
    os.getenv('SECURE_HSTS_INCLUDE_SUBDOMAINS', 'False') == 'True'
)
SECURE_HSTS_PRELOAD = os.getenv('SECURE_HSTS_PRELOAD', 'False') == 'True'
if os.getenv('USE_PROXY_SSL', 'False') == 'True':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# Senha
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internacionalização
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

# Arquivos estáticos
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Arquivos de mídia (capas públicas)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Arquivos protegidos (PDFs dos eBooks — NUNCA públicos!)
PROTECTED_ROOT = BASE_DIR / 'protected'

# Usuário customizado
AUTH_USER_MODEL = 'accounts.User'

# Login
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTHENTICATION_BACKENDS = [
    'apps.accounts.backends.EmailBackend',
]

# Asaas
ASAAS_API_KEY = os.getenv('ASAAS_API_KEY', '')
ASAAS_ENV     = os.getenv('ASAAS_ENV', 'sandbox')
ASAAS_URL     = (
    'https://sandbox.asaas.com/api/v3'
    if os.getenv('ASAAS_ENV') == 'sandbox'
    else 'https://api.asaas.com/api/v3'
)

ASAAS_WEBHOOK_TOKEN = os.getenv('ASAAS_WEBHOOK_TOKEN', '')

# Melhor Envios
ME_CLIENT_ID      = os.getenv('ME_CLIENT_ID', '')
ME_CLIENT_SECRET  = os.getenv('ME_CLIENT_SECRET', '')
ME_REDIRECT_URI   = os.getenv('ME_REDIRECT_URI', '')
ME_WEBHOOK_TOKEN  = os.getenv('ME_WEBHOOK_TOKEN', '')
ME_ENV            = os.getenv('ME_ENV', 'sandbox')  # sandbox | production
ME_URL            = (
    'https://sandbox.melhorenvio.com.br'
    if os.getenv('ME_ENV') == 'sandbox'
    else 'https://melhorenvio.com.br'
)
ME_API_SCOPES = (
    'shipping-calculate shipping-checkout shipping-generate '
    'shipping-print shipping-tracking shipping-cancel '
    'cart-write cart-read orders-read purchases-read'
)

# Email
EMAIL_BACKEND       = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST          = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT          = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS       = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_USE_SSL       = os.getenv('EMAIL_USE_SSL', 'False') == 'True'
EMAIL_TIMEOUT       = int(os.getenv('EMAIL_TIMEOUT', 30))
EMAIL_HOST_USER     = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL  = os.getenv('DEFAULT_FROM_EMAIL', 'BookHub <noreply@erd.com.br>')

# Em desenvolvimento, mostra emails no terminal apenas se não houver SMTP configurado
if DEBUG and not EMAIL_HOST_USER:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# URL pública do site (usada nos e-mails)
SITE_URL = os.getenv('SITE_URL', 'http://127.0.0.1:8000')

# Logging (webhook do Asaas)
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'webhook_file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'webhook.log',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'apps.payments.views': {
            'handlers': ['console', 'webhook_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
