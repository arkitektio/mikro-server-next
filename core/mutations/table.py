from kante.types import Info
import strawberry

from core import types, models, scalars
from .accessor import (
    PartialImageAccessorInput,
    PartialLabelAccessorInput,
    accessor_kwargs_from_input,
)
from core.creation import CreationContext
from core.scoping import get_for_org
from core.mutations._generic import make_delete


@strawberry.input(description="Input for pinning or unpinning a table for quick access")
class PinTableInput:
    """Input for pinning or unpinning a table for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the table to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


def pin_table(
    info: Info,
    input: PinTableInput,
) -> types.Table:
    raise NotImplementedError("TODO")


@strawberry.input(description="Input for deleting a table by ID")
class DeleteTableInput:
    """Input for deleting a table by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the table to delete")


delete_table = make_delete(models.Table, DeleteTableInput)


@strawberry.input(description="Input for creating a table from an uploaded parquet store")
class FromParquetLike:
    """Input for creating a table from an uploaded parquet store"""

    dataframe: scalars.ParquetLike = strawberry.field(description="The parquet dataframe to create the table from")
    name: str = strawberry.field(description="The name of the table")
    origins: list[strawberry.ID] | None = strawberry.field(default=None, description="The IDs of tables this table was derived from")
    dataset: strawberry.ID | None = strawberry.field(default=None, description="The dataset ID this table belongs to")
    label_accessors: list[PartialLabelAccessorInput] | None = strawberry.field(default=None, description="Label accessors to create for this table")
    image_accessors: list[PartialImageAccessorInput] | None = strawberry.field(default=None, description="Image accessors to create for this table")


def from_parquet_like(
    info: Info,
    input: FromParquetLike,
) -> types.Table:
    store = get_for_org(models.ParquetStore, info, id=input.dataframe)
    store.fill_info()

    ctx = CreationContext.from_info(info)
    table = models.Table.objects.create(
        dataset_id=input.dataset,
        name=input.name,
        store=store,
        creator=ctx.user,
        organization=ctx.organization,
        **ctx.provenance_kwargs(),
    )

    if input.label_accessors:
        for accessor in input.label_accessors:
            models.LabelAccessor.objects.create(
                table=table,
                pixel_view=get_for_org(models.PixelView, info, id=accessor.pixel_view),
                **accessor_kwargs_from_input(accessor),
            )

    if input.image_accessors:
        for accessor in input.image_accessors:
            models.ImageAccessor.objects.create(
                table=table,
                **accessor_kwargs_from_input(accessor),
            )

    return table
