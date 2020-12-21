import os

from django.core.exceptions import ImproperlyConfigured


def get_env_setting(setting):
    """ Get the environment setting or return exception """
    try:
        return os.environ[setting]
    except KeyError:
        error_msg = u"Set the %s env variable" % setting
        raise ImproperlyConfigured(error_msg)


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = get_env_setting('HASTEXO_GUACAMOLE_SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('HASTEXO_GUACAMOLE_DEBUG', False)

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
        'level': 'DEBUG' if DEBUG else os.getenv('DJANGO_LOG_LEVEL',
                                                 'WARNING').upper(),
    },
}

ALLOWED_HOSTS = os.getenv('HASTEXO_GUACAMOLE_ALLOWED_HOSTS', "")

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

ASGI_APPLICATION = 'hastexo_django_client.routing.application'

DATABASES = get_env_setting("HASTEXO_GUACAMOLE_DATABASES")
