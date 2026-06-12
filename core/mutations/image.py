"""Image mutations. The bulk creation orchestration lives in core.logic.image."""

from kante.types import Info
import strawberry

from core import types, models
from core.creation import CreationContext
from core.inputs.image import FromArrayLikeInput
from core.logic.image import create_image_from_array
from core.scoping import get_for_org
from core.mutations._generic import make_pin


@strawberry.input(description="Input for marking one image as the origin of another")
class SetAsOriginInput:
    """Input for marking one image as the origin of another"""

    child: strawberry.ID = strawberry.field(description="The ID of the image that derives from the origin")
    origin: bool = strawberry.field(description="The ID of the image to set as the origin")


def set_other_as_origin(
    info: Info,
    input: SetAsOriginInput,
) -> types.Image:
    image = get_for_org(models.Image, info, id=input.child)
    other = get_for_org(models.Image, info, id=input.origin)

    image.origins.add(other)
    return image


def relate_to_dataset(
    info: Info,
    id: strawberry.ID,
    other: strawberry.ID,
) -> types.Image:
    image = get_for_org(models.Image, info, id=id)
    other = get_for_org(models.Dataset, info, id=other)

    return image


@strawberry.input(description="Input for pinning or unpinning an image for quick access")
class PinImageInput:
    """Input for pinning or unpinning an image for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the image to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


pin_image = make_pin(models.Image, PinImageInput, types.Image)


@strawberry.input(description="Input for updating an image's name or tags")
class UpdateImageInput:
    """Input for updating an image's name or tags"""

    id: strawberry.ID = strawberry.field(description="The ID of the image to update")
    tags: list[str] | None = strawberry.field(default=None, description="Tags to add to the image")
    name: str | None = strawberry.field(default=None, description="The new name of the image")


def update_image(
    info: Info,
    input: UpdateImageInput,
) -> types.Image:
    image = get_for_org(models.Image, info, id=input.id)

    if input.tags:
        image.tags.add(*input.tags)

    if input.name:
        image.name = input.name

    image.save()

    return image


@strawberry.input(description="Input for deleting an image by ID")
class DeleteImageInput:
    """Input for deleting an image by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the image to delete")


def delete_image(
    info: Info,
    input: DeleteImageInput,
) -> strawberry.ID:
    item = get_for_org(models.Image, info, id=input.id)
    assert item.creator == info.context.request.user, "You can only delete your own images"

    item.delete()
    return input.id


def from_array_like(
    info: Info,
    input: FromArrayLikeInput,
) -> types.Image:
    ctx = CreationContext.from_info(info)
    return create_image_from_array(info, input, ctx)
