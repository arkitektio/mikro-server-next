from kante.types import Info
import kante
import strawberry
from pydantic import BaseModel, Field
from core import types, models, inputs
from typing import cast
from core.creation import CreationContext
from core.scoping import get_for_org
from core.mutations._generic import make_delete, make_pin, self_owner


class CreateDatasetInputModel(BaseModel):
    name: str = Field(description="The name of the dataset")
    parent: str | None = Field(default=None, description="The ID of the parent dataset to nest this dataset under")


@kante.pydantic_input(CreateDatasetInputModel, description="Input for creating a new dataset to organize images and files")
class CreateDatasetInput:
    """Input for creating a new dataset to organize images and files"""

    name: str = strawberry.field(description="The name of the dataset")
    parent: strawberry.ID | None = strawberry.field(default=None, description="The ID of the parent dataset to nest this dataset under")


class DeleteDatasetInputModel(BaseModel):
    id: str = Field(description="The ID of the dataset to delete")


@kante.pydantic_input(DeleteDatasetInputModel, description="Input for deleting a dataset by ID")
class DeleteDatasetInput:
    """Input for deleting a dataset by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the dataset to delete")


class PinDatasetInputModel(BaseModel):
    id: str = Field(description="The ID of the dataset to pin or unpin")
    pin: bool = Field(description="True to pin, false to unpin")


@kante.pydantic_input(PinDatasetInputModel, description="Input for pinning or unpinning a dataset for quick access")
class PinDatasetInput:
    """Input for pinning or unpinning a dataset for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the dataset to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


pin_dataset = make_pin(models.Dataset, PinDatasetInput, types.Dataset)


class ChangeDatasetInputModel(CreateDatasetInputModel):
    id: str = Field(description="The ID of the dataset to change")


@kante.pydantic_input(ChangeDatasetInputModel, description="Input for changing an existing dataset's name or parent")
class ChangeDatasetInput(CreateDatasetInput):
    """Input for changing an existing dataset's name or parent"""

    id: strawberry.ID = strawberry.field(description="The ID of the dataset to change")


class RevertInputModel(BaseModel):
    id: str = Field(description="The ID of the dataset to revert")
    history_id: str = Field(description="The ID of the provenance history entry to revert the dataset to")


@kante.pydantic_input(RevertInputModel, description="Input for reverting a dataset to a previous history revision")
class RevertInput:
    """Input for reverting a dataset to a previous history revision"""

    id: strawberry.ID = strawberry.field(description="The ID of the dataset to revert")
    history_id: strawberry.ID = strawberry.field(description="The ID of the provenance history entry to revert the dataset to")


def create_dataset(
    info: Info,
    input: CreateDatasetInput,
) -> types.Dataset:
    parsed = input.to_pydantic()
    assert info.context.request.user, "User not authenticated"
    ctx = CreationContext.from_info(info)
    view = models.Dataset.objects.create(
        name=parsed.name,
        parent_id=parsed.parent if parsed.parent else None,
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
    parsed = input.to_pydantic()
    ctx = CreationContext.from_info(info)
    view, _ = models.Dataset.objects.get_or_create(
        name=parsed.name,
        parent_id=parsed.parent if parsed.parent else None,
        creator=ctx.user,
        organization=ctx.organization,
        membership=ctx.membership,
        defaults=ctx.provenance_kwargs(),
    )
    return cast(types.Dataset, view)


delete_dataset = make_delete(models.Dataset, DeleteDatasetInput, owner=self_owner)


def update_dataset(
    info: Info,
    input: ChangeDatasetInput,
) -> types.Dataset:
    parsed = input.to_pydantic()
    view = get_for_org(models.Dataset, info,
        id=parsed.id,
    )
    view.name = parsed.name
    view.save()
    return view


def revert_dataset(
    info: Info,
    input: RevertInput,
) -> types.Dataset:
    parsed = input.to_pydantic()
    dataset = get_for_org(models.Dataset, info,
        id=parsed.id,
    )
    historic = dataset.history.get(history_id=parsed.history_id)
    historic.instance.save()
    return historic.instance


def put_datasets_in_dataset(
    info: Info,
    input: inputs.AssociateInput,
) -> types.Dataset:
    parsed = input.to_pydantic()
    parent = get_for_org(models.Dataset, info,
        id=parsed.other,
    )

    for i in parsed.selfs:
        dataset = get_for_org(models.Dataset, info,
            id=i,
        )
        dataset.parent = parent
        dataset.save()

    return parent


def release_datasets_from_dataset(
    info: Info,
    input: inputs.DesociateInput,
) -> types.Dataset:
    parsed = input.to_pydantic()
    for i in parsed.selfs:
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
    parsed = input.to_pydantic()
    parent = get_for_org(models.Dataset, info,
        id=parsed.other,
    )

    for i in parsed.selfs:
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
    parsed = input.to_pydantic()
    parent = get_for_org(models.Dataset, info,
        id=parsed.other,
    )

    for i in parsed.selfs:
        image = get_for_org(models.Image, info,
            id=i,
        )
        image.dataset = None
        image.save()

    return parent


def put_files_in_dataset(
    info: Info,
    input: inputs.AssociateInput,
) -> types.Dataset:
    parsed = input.to_pydantic()
    parent = get_for_org(models.Dataset, info,
        id=parsed.other,
    )

    for i in parsed.selfs:
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
    parsed = input.to_pydantic()
    parent = get_for_org(models.Dataset, info,
        id=parsed.other,
    )

    for i in parsed.selfs:
        file = get_for_org(models.File, info,
            id=i,
        )
        file.dataset = None
        file.save()

    return parent
