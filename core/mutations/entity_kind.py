from kante.types import Info
import strawberry
from core import types, models


@strawberry.input
class EntityKindInput:
    ontology: strawberry.ID | None = None
    label: str
    description: str | None = None
    purl: str | None = None


@strawberry.input
class DeleteEntityKindInput:
    id: strawberry.ID



def create_entity_kind(
    info: Info,
    input: EntityKindInput,
) -> types.EntityKind:
    
    ontology = models.Ontology.objects.get(id=input.ontology) if input.ontology else None

    if not ontology:

        user = info.context.request.user
    
        ontology, _ = models.Ontology.objects.get_or_create(
            user=user,
            defaults=dict(name="Default for {}".format(user.username),
            description="Default ontology for {}".format(user.username),)
        )


    item, _ = models.EntityKind.objects.update_or_create(
        ontology=ontology,
        label=input.label,
        defaults=dict(description=input.description,
        purl=input.purl)
    )
    return item


def delete_entity_kind(
    info: Info,
    input: DeleteEntityKindInput,
) -> strawberry.ID:
    item = models.EntityKind.objects.get(id=input.id)
    item.delete()
    return input.id

