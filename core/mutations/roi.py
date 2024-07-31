from kante.types import Info
import strawberry
from core import types, models, scalars, enums
from strawberry import ID
import strawberry_django


@strawberry_django.input(models.ROI)
class RoiInput:
    image: ID
    vectors: list[scalars.FiveDVector]
    kind: enums.RoiKind
    entity: ID | None = None
    entity_kind: ID | None = None
    entity_group: ID | None = None
    entity_parent: ID | None = None




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

    if input.entity_kind:
        entity_kind = models.EntityKind.objects.get(id=input.entity_kind)

        if input.entity_group:
            entity_group = models.EntityGroup.objects.get(id=input.entity_group)
        else:
            entity_group, _ = models.EntityGroup.objects.get_or_create(
                image=image,
                defaults=dict(name=f"Auto Group")
            )


        if input.entity_parent:
            entity_parent = models.Entity.objects.get(id=input.entity_parent)

        else:
            entity_parent = None

        entity = models.Entity.objects.create(
            kind=entity_kind,
            group=entity_group,
            parent=entity_parent,
            name=f"{entity_kind.label} {roi.id}",
        )

        roi.entity = entity
        roi.save()


    
    return roi
