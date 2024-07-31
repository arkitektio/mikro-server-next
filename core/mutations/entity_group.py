from kante.types import Info
import strawberry
from core import types, models


@strawberry.input
class EntityGroupInput:
    name: str
    image: strawberry.ID | None = None


@strawberry.input
class DeleteEntityGroupInput:
    id: strawberry.ID



def create_entity_group(
    info: Info,
    input: EntityGroupInput,
) -> types.Entity:
    item = models.EntityGroup.objects.create(
        name=input.name,
        image=models.Image.objects.get(id=input.image) if input.image else None,
    )
    return item


def delete_entity_group(
    info: Info,
    input: DeleteEntityGroupInput,
) -> strawberry.ID:
    item = models.EntityGroup.objects.get(id=input.id)
    item.delete()
    return input.id

