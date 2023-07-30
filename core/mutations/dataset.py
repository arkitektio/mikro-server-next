from kante.types import Info
import strawberry
from core import types, models


@strawberry.input
class DatasetInput:
    name: str


@strawberry.input()
class ChangeDatasetInput(DatasetInput):
    id: strawberry.ID


@strawberry.input()
class RevertInput:
    id: strawberry.ID
    history_id: strawberry.ID


def create_dataset(
    info: Info,
    input: DatasetInput,
) -> types.Dataset:
    view = models.Dataset.objects.create(
        name=input.name,
    )
    return view


def update_dataset(
    info: Info,
    input: ChangeDatasetInput,
) -> types.Dataset:
    view = models.Dataset.objects.get(
        id=input.id,
    )
    view.name = input.name
    view.save()
    return view


def revert_dataset(
    info: Info,
    input: RevertInput,
) -> types.Dataset:
    dataset = models.Dataset.objects.get(
        id=input.id,
    )
    historic = dataset.history.get(history_id=input.history_id)
    historic.instance.save()
    return historic.instance
