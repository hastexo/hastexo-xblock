import asyncio
import urllib.parse
import os

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from distutils.util import strtobool
from guacamole.client import GuacamoleClient
from hastexo.models import Stack
from hastexo.common import get_xblock_settings


class GuacamoleWebSocketConsumer(AsyncWebsocketConsumer):
    client = None
    task = None
    read_only = False

    async def connect(self):
        """
        Initiate the GuacamoleClient and create a connection to it.
        """
        guacd_hostname = os.getenv('GUACD_SERVICE_HOST', 'guacd')
        guacd_port = int(os.getenv('GUACD_SERVICE_PORT', '4822'))

        settings = get_xblock_settings()

        params = urllib.parse.parse_qs(self.scope['query_string'].decode())
        stack_name = params.get('stack')[0]

        stack = await database_sync_to_async(self.get_stack)(stack_name)
        default_port = 3389 if stack.protocol == 'rdp' else 22

        self.read_only = bool(strtobool(params.get('read_only')[0]))

        self.client = GuacamoleClient(guacd_hostname, guacd_port)
        self.client.handshake(
            protocol=stack.protocol,
            width=params.get('width', [1024])[0],
            height=params.get('height', [768])[0],
            hostname=stack.ip,
            port=params.get('port', [default_port])[0],
            username=stack.user,
            password=stack.password,
            private_key=stack.key,
            color_scheme=settings.get("terminal_color_scheme"),
            font_name=settings.get("terminal_font_name"),
            font_size=settings.get("terminal_font_size"),
        )

        if self.client.connected:
            # start receiving data from GuacamoleClient
            loop = asyncio.get_running_loop()
            self.task = loop.create_task(self.open())

            # Accept connection
            await self.accept(subprotocol='guacamole')
        else:
            await self.close()

    def get_stack(self, stack_name):
        return Stack.objects.get(name=stack_name)

    async def disconnect(self, code):
        """
        Close the GuacamoleClient connection on WebSocket disconnect.
        """
        self.task.cancel()
        # explicitly set thread_sensitive=False here to allow concurrent
        # GuacamoleClient connections
        await sync_to_async(self.client.close, thread_sensitive=False)()

    async def receive(self, text_data=None, bytes_data=None):
        """
        Handle data received in the WebSocket, send to GuacamoleClient.
        """
        if text_data is not None:
            # ignore all 'key' and 'mouse' events when set to 'read_only" mode
            if self.read_only and ('key' in text_data or 'mouse' in text_data):
                pass
            else:
                self.client.send(text_data)

    async def open(self):
        """
        Receive data from GuacamoleClient and pass it to the WebSocket
        """
        while True:
            # explicitly set thread_sensitive=False here to allow
            # concurrent GuacamoleClient connections
            content = await sync_to_async(
                self.client.receive, thread_sensitive=False)()
            if content:
                await self.send(text_data=content)
