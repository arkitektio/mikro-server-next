"""Image mutations. The bulk creation orchestration lives in core.logic.image."""

from kante.types import Info
import strawberry
import kante
from pydantic import BaseModel, Field

from core import types, models
from core.creation import CreationContext
from core.inputs.image import FromArrayLikeInput
from core.logic.image import create_image_from_array
from core.scoping import get_for_org
from core.mutations._generic import make_pin, assert_can_delete, self_owner
from django.db import transaction
from core.logic import storage


def relate_to_dataset(
    info: Info,
    id: strawberry.ID,
    other: strawberry.ID,
) -> types.Image:
    image = get_for_org(models.Image, info, id=id)
    other = get_for_org(models.Dataset, info, id=other)

    return image


class PinImageInputModel(BaseModel):
    id: str = Field(description="The ID of the image to pin or unpin")
    pin: bool = Field(description="True to pin, false to unpin")


@kante.pydantic_input(PinImageInputModel, description="Input for pinning or unpinning an image for quick access")
class PinImageInput:
    """Input for pinning or unpinning an image for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the image to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


pin_image = make_pin(models.Image, PinImageInput, types.Image)


class UpdateImageInputModel(BaseModel):
    id: str = Field(description="The ID of the image to update")
    tags: list[str] | None = Field(default=None, description="Tags to add to the image")
    name: str | None = Field(default=None, description="The new name of the image")


@kante.pydantic_input(UpdateImageInputModel, description="Input for updating an image's name or tags")
class UpdateImageInput:
    """Input for updating an image's name or tags"""

    id: strawberry.ID = strawberry.field(description="The ID of the image to update")
    tags: list[str] | None = strawberry.field(default=None, description="Tags to add to the image")
    name: str | None = strawberry.field(default=None, description="The new name of the image")


def update_image(
    info: Info,
    input: UpdateImageInput,
) -> types.Image:
    parsed = input.to_pydantic()
    image = get_for_org(models.Image, info, id=parsed.id)

    if parsed.tags:
        image.tags.add(*parsed.tags)

    if parsed.name:
        image.name = parsed.name

    image.save()

    return image


class DeleteImageInputModel(BaseModel):
    id: str = Field(description="The ID of the image to delete")


@kante.pydantic_input(DeleteImageInputModel, description="Input for deleting an image by ID")
class DeleteImageInput:
    """Input for deleting an image by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the image to delete")


def delete_image(
    info: Info,
    input: DeleteImageInput,
) -> strawberry.ID:
    parsed = input.to_pydantic()
    item = get_for_org(models.Image, info, id=parsed.id)
    assert_can_delete(info, item, self_owner)

    with transaction.atomic():
        # See `make_delete`: collect before, flag after, no S3 work in the request.
        orphaned = storage.stores_orphaned_by(item)
        item.delete()
        storage.flag_orphaned(orphaned)
    return parsed.id


def from_array_like(
    info: Info,
    input: FromArrayLikeInput,
) -> types.Image:
    ctx = CreationContext.from_info(info)
    return create_image_from_array(info, input, ctx)
