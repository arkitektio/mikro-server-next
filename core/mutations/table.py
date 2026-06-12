from kante.types import Info
import strawberry

from core import types, models, scalars
from .accessor import (
    PartialImageAccessorInput,
    PartialLabelAccessorInput,
    accessor_kwargs_from_input,
)
from core.scoping import get_for_org


@strawberry.input
class PinTableInput:
    id: strawberry.ID
    pin: bool


def pin_table(
    info: Info,
    input: PinTableInput,
) -> types.Table:
    raise NotImplementedError("TODO")


@strawberry.input()
class DeleteTableInput:
    id: strawberry.ID


def delete_table(
    info: Info,
    input: DeleteTableInput,
) -> strawberry.ID:
    item = get_for_org(models.Table, info, id=input.id)
    item.delete()
    return input.id


@strawberry.input
class FromParquetLike:
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

    table = models.Table.objects.create(
        dataset_id=input.dataset,
        creator=info.context.request.user,
        organization=info.context.request.organization,
        name=input.name,
        store=store,
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
