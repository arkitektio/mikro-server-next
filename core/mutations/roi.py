from kante.types import Info
import kante
import strawberry
from pydantic import BaseModel, Field
from core import types, models, scalars, enums
from strawberry import ID
from core.creation import CreationContext
from core.scoping import get_for_org
from core.mutations._generic import make_delete, make_pin, self_owner


class RoiInputModel(BaseModel):
    image: str = Field(description="The image this ROI belongs to")
    vectors: list[list[float]] = Field(description="The vector coordinates defining the ROI")
    kind: enums.RoiKind = Field(description="The type/kind of ROI")


@kante.pydantic_input(RoiInputModel, description="Input for creating a region of interest (ROI) on an image")
class RoiInput:
    """Input for creating a region of interest (ROI) on an image"""

    image: ID = strawberry.field(description="The image this ROI belongs to")
    vectors: list[scalars.FiveDVector] = strawberry.field(description="The vector coordinates defining the ROI")
    kind: enums.RoiKind = strawberry.field(description="The type/kind of ROI")


class DeleteRoiInputModel(BaseModel):
    id: str = Field(description="The ID of the ROI to delete")


@kante.pydantic_input(DeleteRoiInputModel, description="Input for deleting a ROI by ID")
class DeleteRoiInput:
    """Input for deleting a ROI by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the ROI to delete")


class PinROIInputModel(BaseModel):
    id: str = Field(description="The ID of the ROI to pin or unpin")
    pin: bool = Field(description="True to pin, false to unpin")


@kante.pydantic_input(PinROIInputModel, description="Input for pinning or unpinning a ROI for quick access")
class PinROIInput:
    """Input for pinning or unpinning a ROI for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the ROI to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


pin_roi = make_pin(models.ROI, PinROIInput, types.ROI)


delete_roi = make_delete(models.ROI, DeleteRoiInput, owner=self_owner)


def create_roi(
    info: Info,
    input: RoiInput,
) -> types.ROI:
    parsed = input.to_pydantic()
    image = get_for_org(models.Image, info, id=parsed.image)

    ctx = CreationContext.from_info(info)
    roi = models.ROI.objects.create(
        image=image,
        vectors=parsed.vectors,
        kind=parsed.kind,
        creator=ctx.user,
        **ctx.provenance_kwargs(),
    )

    return roi


class UpdateRoiInputModel(BaseModel):
    roi: str = Field(description="The ID of the ROI to update")
    vectors: list[list[float]] | None = Field(default=None, description="The new vector coordinates defining the ROI")
    kind: enums.RoiKind | None = Field(default=None, description="The new type/kind of ROI")


@kante.pydantic_input(UpdateRoiInputModel, description="Input for updating an existing region of interest (ROI)")
class UpdateRoiInput:
    """Input for updating an existing region of interest (ROI)"""

    roi: ID = strawberry.field(description="The ID of the ROI to update")
    vectors: list[scalars.FiveDVector] | None = strawberry.field(default=None, description="The new vector coordinates defining the ROI")
    kind: enums.RoiKind | None = strawberry.field(default=None, description="The new type/kind of ROI")


def update_roi(
    info: Info,
    input: UpdateRoiInput,
) -> types.ROI:
    parsed = input.to_pydantic()
    item = get_for_org(models.ROI, info, id=parsed.roi)
    item.vectors = parsed.vectors if parsed.vectors else item.vectors
    item.kind = parsed.kind if parsed.kind else item.kind

    item.save()
    return item
