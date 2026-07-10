from kante.types import Info
import kante
import strawberry
from pydantic import BaseModel, Field

from core import types, models, scalars
from datalayer.datalayer import get_current_datalayer
from core.creation import CreationContext
from core.scoping import get_for_org
from core.mutations._generic import make_delete, self_owner


class FromFileLikeModel(BaseModel):
    file: str = Field(description="The uploaded big-file store to create the file from")
    file_name: str = Field(description="The name of the file")
    dataset: str | None = Field(default=None, description="The ID of the dataset to put the file in (defaults to the current default dataset)")
    origins: list[str] | None = Field(default=None, description="The IDs of entities this file was derived from")


@kante.pydantic_input(FromFileLikeModel, description="Input for creating a file record from an uploaded big-file store")
class FromFileLike:
    """Input for creating a file record from an uploaded big-file store"""

    file: scalars.FileLike = strawberry.field(description="The uploaded big-file store to create the file from")
    file_name: str = strawberry.field(description="The name of the file")
    dataset: strawberry.ID | None = strawberry.field(default=None, description="The ID of the dataset to put the file in (defaults to the current default dataset)")
    origins: list[strawberry.ID] | None = strawberry.field(default=None, description="The IDs of entities this file was derived from")


def from_file_like(
    info: Info,
    input: FromFileLike,
) -> types.File:
    parsed = input.to_pydantic()
    store = get_for_org(models.BigFileStore, info, id=parsed.file)
    store.fill_info()

    dl = get_current_datalayer()

    ctx = CreationContext.from_info(info)
    dataset = get_for_org(models.Dataset, info, id=parsed.dataset) if parsed.dataset else models.Dataset.objects.get_current_default(ctx)

    file = models.File.objects.create(
        dataset=dataset,
        creator=ctx.user,
        organization=ctx.organization,
        membership=ctx.membership,
        name=store.original_file_name,
        size=dl.get_object_size(store.bucket, store.key),
        content_type=store.content_type,
        store=store,
        **ctx.provenance_kwargs(),
    )

    return strawberry.cast(types.File, file)


class DeleteFileInputModel(BaseModel):
    id: str = Field(description="The ID of the file to delete")


@kante.pydantic_input(DeleteFileInputModel, description="Input for deleting a file by ID")
class DeleteFileInput:
    """Input for deleting a file by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the file to delete")


delete_file = make_delete(models.File, DeleteFileInput, owner=self_owner)
