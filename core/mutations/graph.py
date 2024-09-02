from kante.types import Info
import strawberry
from core import types, models,age


@strawberry.input
class GraphInput:
    name: str
    experiment: strawberry.ID | None = None


@strawberry.input
class DeleteGraphInput:
    id: strawberry.ID



def create_graph(
    info: Info,
    input: GraphInput,
) -> types.Graph:
    item, created = models.Graph.objects.update_or_create(
        age_name=f"{input.name.replace(' ', '_').lower()}",
        defaults=dict(
            experiment=models.Experiment.objects.get(id=input.experiment) if input.experiment else None,
            name=input.name,
            user=info.context.request.user,
        )
    )
    if created:
        age.create_age_graph(item.age_name)

    return item


def delete_graph(
    info: Info,
    input: DeleteGraphInput,
) -> strawberry.ID:
    item = models.Graph.objects.get(id=input.id)
    item.delete()
    return input.id

