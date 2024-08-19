from kante.types import Info
import strawberry
from core import types, models, age
from django.db import connections
from contextlib import contextmanager



@strawberry.input
class OntologyInput:
    name: str
    description: str | None = None
    purl: str | None = None


@strawberry.input
class DeleteOntologyInput:
    id: strawberry.ID


def to_snake_case(string):
    return string.replace(" ", "_").lower()


def create_ontology(
    info: Info,
    input: OntologyInput,
) -> types.Ontology:
    
    item, _ = models.Ontology.objects.update_or_create(
        name=to_snake_case(input.name),
        defaults=dict(
        description=input.description or "",
        purl=input.purl)
    )

    age.create_age_ontology(item.name)
    
    return item


def delete_ontology(
    info: Info,
    input: DeleteOntologyInput,
) -> strawberry.ID:
    item = models.Ontology.objects.get(id=input.id)
    

    with graph_cursor() as cursor:
        cursor.execute(
            "SELECT delete_graph(%s);",
            [item.name]
        )
        print(cursor.fetchone())

    item.delete()

    return input.id

