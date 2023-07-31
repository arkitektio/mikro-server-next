from kante.types import Info
import strawberry
from core import types, models


@strawberry.input
class ChannelInput:
    name: str


def create_channel(
    info: Info,
    input: ChannelInput,
) -> types.Channel:
    view = models.Channel.objects.create(
        name=input.name,
    )
    return view


def ensure_channel(
    info: Info,
    input: ChannelInput,
) -> types.Channel:
    view, _ = models.Channel.objects.get_or_create(
        name=input.name,
    )
    return view
