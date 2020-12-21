import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE',
                      'hastexo_guacamole_client.settings')
django.setup()

from channels.auth import AuthMiddlewareStack  # noqa E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa E402

from django.urls import path  # noqa E402

from .consumers import GuacamoleWebSocketConsumer  # noqa E402


application = ProtocolTypeRouter({
    'websocket': AuthMiddlewareStack(
        URLRouter([
            path('hastexo-xblock/websocket-tunnel',
                 GuacamoleWebSocketConsumer),
        ])
    ),
})
