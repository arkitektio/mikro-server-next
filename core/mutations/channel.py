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
