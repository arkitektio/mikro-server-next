from typing import AsyncGenerator
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from kante.types import Info
from kante.channel import build_channel


image_broadcast, image_listen = build_channel("image")
provenance_broadcast, provenance_listen = build_channel("provenance")
