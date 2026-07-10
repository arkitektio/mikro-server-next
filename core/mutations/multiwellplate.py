from kante.types import Info
import kante
import strawberry
from pydantic import BaseModel, Field
from core import types, models
from core.mutations._generic import make_delete, make_pin


class MultiWellPlateInputModel(BaseModel):
    name: str = Field(description="The name of the multi-well plate")
    columns: int | None = Field(default=None, description="The number of columns in the plate")
    rows: int | None = Field(default=None, description="The number of rows in the plate")


@kante.pydantic_input(MultiWellPlateInputModel, description="Input for creating or ensuring a multi-well plate")
class MultiWellPlateInput:
    """Input for creating or ensuring a multi-well plate"""

    name: str = strawberry.field(description="The name of the multi-well plate")
    columns: int | None = strawberry.field(default=None, description="The number of columns in the plate")
    rows: int | None = strawberry.field(default=None, description="The number of rows in the plate")


class DeleteMultiWellInputModel(BaseModel):
    id: str = Field(description="The ID of the multi-well plate to delete")


@kante.pydantic_input(DeleteMultiWellInputModel, description="Input for deleting a multi-well plate by ID")
class DeleteMultiWellInput:
    """Input for deleting a multi-well plate by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the multi-well plate to delete")


class PintMultiWellPlateInputModel(BaseModel):
    id: str = Field(description="The ID of the multi-well plate to pin or unpin")
    pin: bool = Field(description="True to pin, false to unpin")


@kante.pydantic_input(PintMultiWellPlateInputModel, description="Input for pinning or unpinning a multi-well plate for quick access")
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
    parsed = input.to_pydantic()
    item = models.MultiWellPlate.objects.create(
        name=parsed.name,
        organization=info.context.request.organization,
        columns=parsed.columns,
        rows=parsed.rows,
    )
    return item


def ensure_multi_well_plate(
    info: Info,
    input: MultiWellPlateInput,
) -> types.MultiWellPlate:
    parsed = input.to_pydantic()
    item, _ = models.MultiWellPlate.objects.update_or_create(
        name=parsed.name,
        organization=info.context.request.organization,
        defaults=dict(
            columns=parsed.columns,
            rows=parsed.rows,
        ),
    )
    return item
