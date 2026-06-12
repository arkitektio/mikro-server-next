from kante.types import Info
import strawberry
from core import types, models, scalars, enums
from strawberry import ID
import strawberry_django
from core.creation import CreationContext
from core.scoping import get_for_org
from core.mutations._generic import make_delete, make_pin


@strawberry_django.input(models.ROI, description="Input for creating a region of interest (ROI) on an image")
class RoiInput:
    """Input for creating a region of interest (ROI) on an image"""

    image: ID = strawberry.field(description="The image this ROI belongs to")
    vectors: list[scalars.FiveDVector] = strawberry.field(description="The vector coordinates defining the ROI")
    kind: enums.RoiKind = strawberry.field(description="The type/kind of ROI")


@strawberry.input(description="Input for deleting a ROI by ID")
class DeleteRoiInput:
    """Input for deleting a ROI by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the ROI to delete")


@strawberry.input(description="Input for pinning or unpinning a ROI for quick access")
class PinROIInput:
    """Input for pinning or unpinning a ROI for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the ROI to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


pin_roi = make_pin(models.ROI, PinROIInput, types.ROI)


delete_roi = make_delete(models.ROI, DeleteRoiInput)


def create_roi(
    info: Info,
    input: RoiInput,
) -> types.ROI:
    image = get_for_org(models.Image, info, id=input.image)

    ctx = CreationContext.from_info(info)
    roi = models.ROI.objects.create(
        image=image,
        vectors=input.vectors,
        kind=input.kind,
        creator=ctx.user,
        **ctx.provenance_kwargs(),
    )

    return roi


@strawberry_django.input(models.ROI, description="Input for updating an existing region of interest (ROI)")
class UpdateRoiInput:
    """Input for updating an existing region of interest (ROI)"""

    roi: ID = strawberry.field(description="The ID of the ROI to update")
    vectors: list[scalars.FiveDVector] | None = strawberry.field(default=None, description="The new vector coordinates defining the ROI")
    kind: enums.RoiKind | None = strawberry.field(default=None, description="The new type/kind of ROI")


def update_roi(
    info: Info,
    input: UpdateRoiInput,
) -> types.ROI:
    item = get_for_org(models.ROI, info, id=input.roi)
    item.vectors = input.vectors if input.vectors else item.vectors
    item.kind = input.kind if input.kind else item.kind

    item.save()
    return item
