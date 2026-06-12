from kante.types import Info
import strawberry
from core import types, models, scalars, enums
from strawberry import ID
import strawberry_django
from core.scoping import get_for_org
from core.mutations._generic import make_delete, make_pin
from koherent.utils import get_or_create_task


@strawberry_django.input(models.ROI)
class RoiInput:
    image: ID = strawberry.field(description="The image this ROI belongs to")
    vectors: list[scalars.FiveDVector] = strawberry.field(description="The vector coordinates defining the ROI")
    kind: enums.RoiKind = strawberry.field(description="The type/kind of ROI")


@strawberry.input()
class DeleteRoiInput:
    id: strawberry.ID


@strawberry.input
class PinROIInput:
    id: strawberry.ID
    pin: bool


pin_roi = make_pin(models.ROI, PinROIInput, types.ROI)


delete_roi = make_delete(models.ROI, DeleteRoiInput)


def create_roi(
    info: Info,
    input: RoiInput,
) -> types.ROI:
    image = get_for_org(models.Image, info, id=input.image)

    roi = models.ROI.objects.create(
        image=image,
        vectors=input.vectors,
        kind=input.kind,
        creator=info.context.request.user,
        created_through=get_or_create_task(),
    )

    return roi


@strawberry_django.input(models.ROI)
class UpdateRoiInput:
    roi: ID
    vectors: list[scalars.FiveDVector] | None = None
    kind: enums.RoiKind | None = None


def update_roi(
    info: Info,
    input: UpdateRoiInput,
) -> types.ROI:
    item = get_for_org(models.ROI, info, id=input.roi)
    item.vectors = input.vectors if input.vectors else item.vectors
    item.kind = input.kind if input.kind else item.kind

    item.save()
    return item
