from kante.types import Info
import strawberry
from core import types, models
import uuid




@strawberry.input
class EntityInput:
    kind: strawberry.ID
    group: strawberry.ID  | None = None
    parent: strawberry.ID | None = None
    instance_kind: str | None = None
    name: str | None = None


@strawberry.input
class DeleteEntityInput:
    id: strawberry.ID



def create_entity(
    info: Info,
    input: EntityInput,
) -> types.Entity:
    
    if input.group:
        group = models.EntityGroup.objects.get(id=input.group)
    else:
        group, _ = models.EntityGroup.objects.get_or_create(name="All entitites")


    input_kind = models.EntityKind.objects.get(id=input.kind)



    item, _ = models.Entity.objects.get_or_create(
        name=input.name or uuid.uuid4().hex,
        group=group,
        kind=input_kind,
        defaults=dict(
            name=input.name or uuid.uuid4().hex,
            instance_kind=input.instance_kind,
        )
    )



    assert item.kind.id == input_kind.id, f"Entity kind mismatch {item.kind} vs {input_kind}"




    return item


def delete_entity(
    info: Info,
    input: DeleteEntityInput,
) -> strawberry.ID:
    item = models.Entity.objects.get(id=input.id)
    item.delete()
    return input.id

