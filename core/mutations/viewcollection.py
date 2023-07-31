from kante.types import Info
import strawberry
from core import types, models


@strawberry.input
class ViewCollectionInput:
    name: str


def create_view_collection(
    info: Info,
    input: ViewCollectionInput,
) -> types.Channel:
    view = models.Channel.objects.create(
        name=input.name,
    )
    return view


def ensure_view_collection(
    info: Info,
    input: ViewCollectionInput,
) -> types.Channel:
    view, _ = models.Channel.objects.get_or_create(
        name=input.name,
    )
    return view
