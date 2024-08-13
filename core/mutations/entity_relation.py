from kante.types import Info
import strawberry
from core import types, models


@strawberry.input
class EntityRelationInput:
    left: strawberry.ID
    right: strawberry.ID
    kind: strawberry.ID

@strawberry.input
class EntityRelationKindInput:
    left_kind: strawberry.ID
    right_kind: strawberry.ID
    kind: strawberry.ID



@strawberry.input
class DeleteEntityRelationInput:
    id: strawberry.ID


def create_entity_relation_kind(
    info: Info,
    input: EntityRelationKindInput,
) -> types.EntityRelationKind:
    
    item, _ = models.EntityRelationKind.objects.get_or_create(
        left_kind=models.EntityKind.objects.get(id=input.left_kind),
        right_kind=models.EntityKind.objects.get(id=input.right_kind),
        kind=models.EntityKind.objects.get(id=input.kind),
    )
    return item



def create_entity_relation(
    info: Info,
    input: EntityRelationInput,
) -> types.EntityRelation:
    item, _ = models.EntityRelation.objects.get_or_create(
        left=models.Entity.objects.get(id=input.left),
        right=models.Entity.objects.get(id=input.right),
        kind=models.EntityRelationKind.objects.get(id=input.kind),
    )
    return item


def delete_entity_relation(
    info: Info,
    input: DeleteEntityRelationInput,
) -> strawberry.ID:
    item = models.EntityRelation.objects.get(id=input.id)
    item.delete()
    return input.id

