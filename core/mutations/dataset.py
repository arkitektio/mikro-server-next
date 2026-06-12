from kante.types import Info
import strawberry
from core import types, models, inputs
from typing import cast
from core.scoping import get_for_org
from core.mutations._generic import make_delete, make_pin
from koherent.utils import get_or_create_task


@strawberry.input
class CreateDatasetInput:
    name: str
    parent: strawberry.ID | None = None


@strawberry.input
class DeleteDatasetInput:
    id: strawberry.ID


@strawberry.input
class PinDatasetInput:
    id: strawberry.ID
    pin: bool


pin_dataset = make_pin(models.Dataset, PinDatasetInput, types.Dataset)


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
    assert info.context.request.user, "User not authenticated"
    task = get_or_create_task()
    view = models.Dataset.objects.create(name=input.name, creator=info.context.request.user, parent_id=input.parent if input.parent else None, organization=info.context.request.organization, membership=info.context.request.membership, created_through=task, created_through_by_id=task.assigner_id if task else None)
    return cast(types.Dataset, view)


def ensure_dataset(
    info: Info,
    input: CreateDatasetInput,
) -> types.Dataset:
    task = get_or_create_task()
    view, _ = models.Dataset.objects.get_or_create(name=input.name, creator=info.context.request.user, parent_id=input.parent if input.parent else None, organization=info.context.request.organization, membership=info.context.request.membership, defaults=dict(created_through=task, created_through_by_id=task.assigner_id if task else None))
    return cast(types.Dataset, view)


delete_dataset = make_delete(models.Dataset, DeleteDatasetInput)


def update_dataset(
    info: Info,
    input: ChangeDatasetInput,
) -> types.Dataset:
    view = get_for_org(models.Dataset, info,
        id=input.id,
    )
    view.name = input.name
    view.save()
    return view


def revert_dataset(
    info: Info,
    input: RevertInput,
) -> types.Dataset:
    dataset = get_for_org(models.Dataset, info,
        id=input.id,
    )
    historic = dataset.history.get(history_id=input.history_id)
    historic.instance.save()
    return historic.instance


def put_datasets_in_dataset(
    info: Info,
    input: inputs.AssociateInput,
) -> types.Dataset:
    parent = get_for_org(models.Dataset, info,
        id=input.other,
    )

    for i in input.selfs:
        dataset = get_for_org(models.Dataset, info,
            id=i,
        )
        dataset.parent = parent
        dataset.save()

    return dataset


def release_datasets_from_dataset(
    info: Info,
    input: inputs.DesociateInput,
) -> types.Dataset:
    for i in input.selfs:
        dataset = get_for_org(models.Dataset, info,
            id=i,
        )
        dataset.parent = None
        dataset.save()
    return dataset


def put_images_in_dataset(
    info: Info,
    input: inputs.AssociateInput,
) -> types.Dataset:
    parent = get_for_org(models.Dataset, info,
        id=input.other,
    )

    for i in input.selfs:
        image = get_for_org(models.Image, info,
            id=i,
        )
        image.dataset = parent
        image.save()

    return parent


def release_images_from_dataset(
    info: Info,
    input: inputs.DesociateInput,
) -> types.Dataset:
    for i in input.selfs:
        dataset = get_for_org(models.Image, info,
            id=i,
        )
        dataset.parent = None
        dataset.save()
    return dataset


def put_files_in_dataset(
    info: Info,
    input: inputs.AssociateInput,
) -> types.Dataset:
    parent = get_for_org(models.Dataset, info,
        id=input.other,
    )

    for i in input.selfs:
        image = get_for_org(models.File, info,
            id=i,
        )
        image.dataset = parent
        image.save()

    return parent


def release_files_from_dataset(
    info: Info,
    input: inputs.DesociateInput,
) -> types.Dataset:
    for i in input.selfs:
        dataset = get_for_org(models.File, info,
            id=i,
        )
        dataset.parent = None
        dataset.save()
    return dataset
