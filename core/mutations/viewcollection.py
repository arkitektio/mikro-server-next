from kante.types import Info
import strawberry
from core import types, models
from core.scoping import get_for_org


@strawberry.input
class ViewCollectionInput:
    name: str


@strawberry.input()
class DeleteViewCollectionInput:
    id: strawberry.ID


@strawberry.input
class PinViewCollectionInput:
    id: strawberry.ID
    pin: bool


def pin_view_collection(
    info: Info,
    input: PinViewCollectionInput,
) -> types.ViewCollection:
    raise NotImplementedError("TODO")


def delete_view_collection(
    info: Info,
    input: DeleteViewCollectionInput,
) -> strawberry.ID:
    item = get_for_org(models.ViewCollection, info, id=input.id)
    item.delete()
    return input.id


def create_view_collection(
    info: Info,
    input: ViewCollectionInput,
) -> types.ViewCollection:
    view = models.ViewCollection.objects.create(
        name=input.name,
    )
    return view


def ensure_view_collection(
    info: Info,
    input: ViewCollectionInput,
) -> types.ViewCollection:
    view, _ = models.ViewCollection.objects.get_or_create(
        name=input.name,
    )
    return view
