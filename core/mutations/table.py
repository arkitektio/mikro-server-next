from kante.types import Info
import kante
import strawberry
from pydantic import BaseModel, Field

from core import types, models, scalars
from .accessor import (
    PartialImageAccessorInput,
    PartialImageAccessorInputModel,
    PartialLabelAccessorInput,
    PartialLabelAccessorInputModel,
    accessor_kwargs_from_input,
)
from core.creation import CreationContext
from core.scoping import get_for_org
from core.mutations._generic import make_delete, self_owner


class DeleteTableInputModel(BaseModel):
    id: str = Field(description="The ID of the table to delete")


@kante.pydantic_input(DeleteTableInputModel, description="Input for deleting a table by ID")
class DeleteTableInput:
    """Input for deleting a table by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the table to delete")


delete_table = make_delete(models.Table, DeleteTableInput, owner=self_owner)


class FromParquetLikeModel(BaseModel):
    dataframe: str = Field(description="The parquet dataframe to create the table from")
    name: str = Field(description="The name of the table")
    dataset: str | None = Field(default=None, description="The dataset ID this table belongs to")
    label_accessors: list[PartialLabelAccessorInputModel] | None = Field(default=None, description="Label accessors to create for this table")
    image_accessors: list[PartialImageAccessorInputModel] | None = Field(default=None, description="Image accessors to create for this table")


@kante.pydantic_input(FromParquetLikeModel, description="Input for creating a table from an uploaded parquet store")
class FromParquetLike:
    """Input for creating a table from an uploaded parquet store"""

    dataframe: scalars.ParquetLike = strawberry.field(description="The parquet dataframe to create the table from")
    name: str = strawberry.field(description="The name of the table")
    dataset: strawberry.ID | None = strawberry.field(default=None, description="The dataset ID this table belongs to")
    label_accessors: list[PartialLabelAccessorInput] | None = strawberry.field(default=None, description="Label accessors to create for this table")
    image_accessors: list[PartialImageAccessorInput] | None = strawberry.field(default=None, description="Image accessors to create for this table")


def from_parquet_like(
    info: Info,
    input: FromParquetLike,
) -> types.Table:
    parsed = input.to_pydantic()
    store = get_for_org(models.ParquetStore, info, id=parsed.dataframe)
    store.fill_info()

    ctx = CreationContext.from_info(info)
    table = models.Table.objects.create(
        dataset_id=parsed.dataset,
        name=parsed.name,
        store=store,
        creator=ctx.user,
        organization=ctx.organization,
        **ctx.provenance_kwargs(),
    )

    if parsed.label_accessors:
        for accessor in parsed.label_accessors:
            models.LabelAccessor.objects.create(
                table=table,
                pixel_view=get_for_org(models.PixelView, info, id=accessor.pixel_view),
                **accessor_kwargs_from_input(accessor),
            )

    if parsed.image_accessors:
        for accessor in parsed.image_accessors:
            models.ImageAccessor.objects.create(
                table=table,
                **accessor_kwargs_from_input(accessor),
            )

    return table
