from kante.types import Info
import strawberry
from core import types, models
from core.mutations._generic import make_delete, make_pin


@strawberry.input
class MultiWellPlateInput:
    name: str
    columns: int | None = None
    rows: int | None = None


@strawberry.input
class DeleteMultiWellInput:
    id: strawberry.ID


@strawberry.input
class PintMultiWellPlateInput:
    id: strawberry.ID
    pin: bool


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
