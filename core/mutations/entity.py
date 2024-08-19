from kante.types import Info
import strawberry
from core import types, models, age
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


    id = uuid.uuid4().hex

    item, _ = models.Entity.objects.get_or_create(
        name=id,
        group=group,
        kind=input_kind,
        defaults=dict(
            name=id,
            instance_kind=input.instance_kind,
        )
    )

    age.create_age_entity(input_kind.ontology.age_name, input_kind.age_name, id)





    assert item.kind.id == input_kind.id, f"Entity kind mismatch {item.kind} vs {input_kind}"




    return item


def delete_entity(
    info: Info,
    input: DeleteEntityInput,
) -> strawberry.ID:
    item = models.Entity.objects.get(id=input.id)
    item.delete()
    return input.id

