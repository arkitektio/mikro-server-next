from kante.types import Info
import strawberry
from core import types, models, enums
from core import age


@strawberry.input
class ExpressionInput:
    ontology: strawberry.ID | None = None
    label: str
    description: str | None = None
    purl: str | None = None
    color: list[int] | None = None
    kind: enums.ExpressionKind
    data_kind: enums.MetricDataType | None = None


@strawberry.input
class DeleteExpressionInput:
    id: strawberry.ID



def create_expression(
    info: Info,
    input: ExpressionInput,
) -> types.Expression:
    
    ontology = models.Ontology.objects.get(id=input.ontology) if input.ontology else None

    if not ontology:

        user = info.context.request.user
    
        ontology, _ = models.Ontology.objects.get_or_create(
            user=user,
            defaults=dict(name="Default for {}".format(user.username),
            description="Default ontology for {}".format(user.username),)
        )


    if input.color:
        assert len(input.color) == 3 or len(input.color) == 4, "Color must be a list of 3 or 4 values RGBA"

    

    vocab, _ = models.Expression.objects.update_or_create(
        ontology=ontology,
        label=input.label,
        kind=input.kind,
        defaults=dict(
            description=input.description,
            purl=input.purl,
        )
    )



   
    

    return vocab


def delete_expression(
    info: Info,
    input: DeleteExpressionInput,
) -> strawberry.ID:
    item = models.Expression.objects.get(id=input.id)
    item.delete()
    return input.id

