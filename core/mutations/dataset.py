from kante.types import Info
import strawberry
from core import types, models, inputs
from typing import cast
from core.creation import CreationContext
from core.scoping import get_for_org
from core.mutations._generic import make_delete, make_pin


@strawberry.input(description="Input for creating a new dataset to organize images and files")
class CreateDatasetInput:
    """Input for creating a new dataset to organize images and files"""

    name: str = strawberry.field(description="The name of the dataset")
    parent: strawberry.ID | None = strawberry.field(default=None, description="The ID of the parent dataset to nest this dataset under")


@strawberry.input(description="Input for deleting a dataset by ID")
class DeleteDatasetInput:
    """Input for deleting a dataset by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the dataset to delete")


@strawberry.input(description="Input for pinning or unpinning a dataset for quick access")
class PinDatasetInput:
    """Input for pinning or unpinning a dataset for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the dataset to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


pin_dataset = make_pin(models.Dataset, PinDatasetInput, types.Dataset)


@strawberry.input(description="Input for changing an existing dataset's name or parent")
class ChangeDatasetInput(CreateDatasetInput):
    """Input for changing an existing dataset's name or parent"""

    id: strawberry.ID = strawberry.field(description="The ID of the dataset to change")


@strawberry.input(description="Input for reverting a dataset to a previous history revision")
class RevertInput:
    """Input for reverting a dataset to a previous history revision"""

    id: strawberry.ID = strawberry.field(description="The ID of the dataset to revert")
    history_id: strawberry.ID = strawberry.field(description="The ID of the provenance history entry to revert the dataset to")


def create_dataset(
    info: Info,
    input: CreateDatasetInput,
) -> types.Dataset:
    assert info.context.request.user, "User not authenticated"
    ctx = CreationContext.from_info(info)
    view = models.Dataset.objects.create(
        name=input.name,
        parent_id=input.parent if input.parent else None,
        creator=ctx.user,
        organization=ctx.organization,
        membership=ctx.membership,
        **ctx.provenance_kwargs(),
    )
    return cast(types.Dataset, view)


def ensure_dataset(
    info: Info,
    input: CreateDatasetInput,
) -> types.Dataset:
    ctx = CreationContext.from_info(info)
    view, _ = models.Dataset.objects.get_or_create(
        name=input.name,
        parent_id=input.parent if input.parent else None,
        creator=ctx.user,
        organization=ctx.organization,
        membership=ctx.membership,
        defaults=ctx.provenance_kwargs(),
    )
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
