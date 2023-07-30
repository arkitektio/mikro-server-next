from kante.types import Info
import strawberry
from core import types, models, scalars
from strawberry import ID
import strawberry_django


@strawberry_django.input(models.ROI)
class RoiInput:
    image: ID
    vectors: list[scalars.Vector]
    kind: strawberry.auto


def create_roi(
    info: Info,
    input: RoiInput,
) -> types.View:
    image = models.Image.objects.get(id=input.image)

    roi = models.ROI.objects.create(
        image=image,
        vectors=input.vectors,
        kind=input.kind,
    )
    return roi
