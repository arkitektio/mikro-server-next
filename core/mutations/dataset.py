from kante.types import Info
import strawberry
from core import types, models
from typing import cast


@strawberry.input
class CreateDatasetInput:
    name: str


@strawberry.input
class DeleteDatasetInput:
    id: strawberry.ID


@strawberry.input
class PinDatasetInput:
    id: strawberry.ID
    pin: bool


def pin_dataset(
    info: Info,
    input: PinDatasetInput,
) -> types.Dataset:
    raise NotImplementedError("TODO")


@strawberry.input()
class ChangeDatasetInput(CreateDatasetInput):
    id: strawberry.ID


@strawberry.input()
class RevertInput:
    id: strawberry.ID
    history_id: strawberry.ID


def create_dataset(
    info: Info,
    input: CreateDatasetInput,
) -> types.Dataset:
    view = models.Dataset.objects.create(
        name=input.name,
    )
    return cast(types.Dataset, view)


def delete_dataset(
    info: Info,
    input: DeleteDatasetInput,
) -> strawberry.ID:
    view = models.Dataset.objects.get(
        id=input.id,
    )
    view.delete()
    return input.id


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
