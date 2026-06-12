from kante.types import Info
import strawberry
from core import types, models, inputs
from typing import cast
from core.scoping import get_for_org


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
    assert info.context.request.user, "User not authenticated"
    view = models.Dataset.objects.create(name=input.name, creator=info.context.request.user, parent_id=input.parent if input.parent else None, organization=info.context.request.organization, membership=info.context.request.membership)
    return cast(types.Dataset, view)


def ensure_dataset(
    info: Info,
    input: CreateDatasetInput,
) -> types.Dataset:
    view, _ = models.Dataset.objects.get_or_create(name=input.name, creator=info.context.request.user, parent_id=input.parent if input.parent else None, organization=info.context.request.organization, membership=info.context.request.membership)
    return cast(types.Dataset, view)


def delete_dataset(
    info: Info,
    input: DeleteDatasetInput,
) -> strawberry.ID:
    view = get_for_org(models.Dataset, info,
        id=input.id,
    )
    view.delete()
    return input.id


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
