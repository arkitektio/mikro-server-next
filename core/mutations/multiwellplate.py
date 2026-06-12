from kante.types import Info
import strawberry
from core import types, models
from core.mutations._generic import make_delete, make_pin


@strawberry.input(description="Input for creating or ensuring a multi-well plate")
class MultiWellPlateInput:
    """Input for creating or ensuring a multi-well plate"""

    name: str = strawberry.field(description="The name of the multi-well plate")
    columns: int | None = strawberry.field(default=None, description="The number of columns in the plate")
    rows: int | None = strawberry.field(default=None, description="The number of rows in the plate")


@strawberry.input(description="Input for deleting a multi-well plate by ID")
class DeleteMultiWellInput:
    """Input for deleting a multi-well plate by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the multi-well plate to delete")


@strawberry.input(description="Input for pinning or unpinning a multi-well plate for quick access")
class PintMultiWellPlateInput:
    """Input for pinning or unpinning a multi-well plate for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the multi-well plate to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


pin_multi_well_plate = make_pin(models.MultiWellPlate, PintMultiWellPlateInput, types.MultiWellPlate)


delete_multi_well_plate = make_delete(models.MultiWellPlate, DeleteMultiWellInput)


def create_multi_well_plate(
    info: Info,
    input: MultiWellPlateInput,
) -> types.MultiWellPlate:
    item = models.MultiWellPlate.objects.create(
        name=input.name,
        organization=info.context.request.organization,
        columns=input.columns,
        rows=input.rows,
    )
    return item


def ensure_multi_well_plate(
    info: Info,
    input: MultiWellPlateInput,
) -> types.MultiWellPlate:
    item, _ = models.MultiWellPlate.objects.update_or_create(
        name=input.name,
        organization=info.context.request.organization,
        defaults=dict(
            columns=input.columns,
            rows=input.rows,
        ),
    )
    return item
