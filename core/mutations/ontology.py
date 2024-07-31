from kante.types import Info
import strawberry
from core import types, models


@strawberry.input
class OntologyInput:
    name: str
    description: str | None = None
    purl: str | None = None


@strawberry.input
class DeleteOntologyInput:
    id: strawberry.ID



def create_ontology(
    info: Info,
    input: OntologyInput,
) -> types.Ontology:
    
    item, _ = models.Ontology.objects.update_or_create(
        name=input.name,
        defaults=dict(
        description=input.description,
        purl=input.purl)
    )
    
    return item


def delete_ontology(
    info: Info,
    input: DeleteOntologyInput,
) -> strawberry.ID:
    item = models.Entity.objects.get(id=input.id)
    item.delete()
    return input.id

