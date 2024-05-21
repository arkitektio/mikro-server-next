from kante.types import Info
import strawberry
from core import types, models, scalars
from strawberry import ID
import strawberry_django


@strawberry_django.input(models.ROI)
class RoiInput:
    image: ID
    vectors: list[scalars.FiveDVector]
    kind: strawberry.auto


@strawberry.input()
class DeleteRoiInput:
    id: strawberry.ID


@strawberry.input
class PinROIInput:
    id: strawberry.ID
    pin: bool


def pin_roi(
    info: Info,
    input: PinROIInput,
) -> types.Instrument:
    raise NotImplementedError("TODO")


def delete_roi(
    info: Info,
    input: DeleteRoiInput,
) -> strawberry.ID:
    item = models.ROI.objects.get(id=input.id)
    item.delete()
    return input.id


def create_roi(
    info: Info,
    input: RoiInput,
) -> types.ROI:
    image = models.Image.objects.get(id=input.image)

    roi = models.ROI.objects.create(
        image=image,
        vectors=input.vectors,
        kind=input.kind,
        creator=info.context.request.user
    )
    return roi
