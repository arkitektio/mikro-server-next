from kante.types import Info
import strawberry
from core import types, models, enums
from django.conf import settings
from strawberry.file_uploads import Upload

@strawberry.input
class RGBContextViewInput:
    c_max: int
    c_min: int
    gamma: float | None = None
    contrast_limit_min: float | None = None
    contrast_limit_max: float | None = None
    rescale: bool | None = None
    scale: float | None = None
    active: bool | None = None
    color_map: enums.ColorMap | None = None


@strawberry.input
class CreateRGBContextInput:
    name: str | None = None
    thumbnail: strawberry.ID | None = None
    image: strawberry.ID
    views: list[RGBContextViewInput] | None = None


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
    input: CreateRGBContextInput,
) -> types.RGBContext:
    context = models.RGBRenderContext.objects.create(
        name=input.name,
        image=models.Image.objects.get(id=input.image),
    )

    print(input)
    if input.thumbnail:
        media_store = models.MediaStore.objects.get(id=input.thumbnail)

        snapshot = models.Snapshot.objects.create(
            name = "RGB SNapshort", store=media_store, image_id=input.image, context=context
        )
        print("Created Snapshot")
        





    for view_input in input.views:

        x, _ = models.RGBView.objects.get_or_create(
            image_id=input.image,
            c_max=view_input.c_max,
            c_min=view_input.c_min,
            gamma=view_input.gamma,
            contrast_limit_min=view_input.contrast_limit_min,
            contrast_limit_max=view_input.contrast_limit_max,
            rescale=view_input.rescale,
            active=view_input.active,
            color_map=view_input.color_map,
        )

        context.views.add(x)

    context.save()

    return context

