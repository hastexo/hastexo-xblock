import os
from distutils.util import strtobool
from yaml import load, SafeLoader
from yaml.scanner import ScannerError

from django.core.exceptions import ImproperlyConfigured


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('HASTEXO_GUACAMOLE_SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = bool(strtobool(os.environ.get('HASTEXO_GUACAMOLE_DEBUG', 'false')))
DJANGO_LOG_LEVEL = os.environ.get('HASTEXO_GUACAMOLE_LOG_LEVEL', 'WARNING')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '%(levelname)s:%(name)s:%(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG' if DEBUG else DJANGO_LOG_LEVEL.upper()
    },
}

ALLOWED_HOSTS = os.environ.get('HASTEXO_GUACAMOLE_ALLOWED_HOSTS', '')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('HASTEXO_GUACAMOLE_DEFAULT_DB_NAME', 'edxapp'),
        'USER': os.environ.get('HASTEXO_GUACAMOLE_DATABASE_USER', 'edxapp001'),
        'PASSWORD': os.environ.get(
            'HASTEXO_GUACAMOLE_DATABASE_PASSWORD', 'password'),
        'HOST': os.environ.get('HASTEXO_GUACAMOLE_DATABASE_HOST', 'localhost'),
        'PORT': int(os.environ.get('HASTEXO_GUACAMOLE_DATABASE_PORT', '3306')),
        'ATOMIC_REQUESTS': bool(strtobool(os.environ.get(
            'HASTEXO_GUACAMOLE_DATABASE_ATOMIC_REQUESTS', 'false'))),
        'CONN_MAX_AGE': int(os.environ.get(
            'HASTEXO_GUACAMOLE_DATABASE_CONN_MAX_AGE', '0')),
        'OPTIONS': os.environ.get('HASTEXO_GUACAMOLE_DATABASE_OPTIONS', {}),
    }
}

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'hastexo_guacamole_client'
]

ASGI_APPLICATION = 'hastexo_guacamole_client.asgi:application'

CONFIG_FILE = os.environ.get('HASTEXO_GUACAMOLE_CFG', None)
if CONFIG_FILE:
    try:
        with open(CONFIG_FILE) as f:
            config_from_yaml = load(f, Loader=SafeLoader)
            vars().update(config_from_yaml)
    except OSError as e:
        raise ImproperlyConfigured(e)
    except (ValueError, TypeError, ScannerError) as e:
        raise ImproperlyConfigured(
            'Unable to update configuration '
            'with contents of %s: %s' % (CONFIG_FILE, e)
        )
