from kante.types import Info
import strawberry
from core import types, models


@strawberry.input
class RGBContextInput:
    name: str | None = None


@strawberry.input
class PinRGBContextInput:
    id: strawberry.ID
    pin: bool


def pin_rgb_context(
    info: Info,
    input: PinRGBContextInput,
) -> types.RGBContext:
    raise NotImplementedError("TODO")


@strawberry.input()
class DeleteRGBContextInput:
    id: strawberry.ID


def delete_rgb_context(
    info: Info,
    input: DeleteRGBContextInput,
) -> strawberry.ID:
    item = models.RGBRenderContext.objects.get(id=input.id)
    item.delete()
    return input.id


def create_rgb_context(
    info: Info,
    input: RGBContextInput,
) -> types.RGBContext:
    view = models.RGBRenderContext.objects.create(
        name=input.name,
    )
    return view

