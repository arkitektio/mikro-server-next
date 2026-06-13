from kante.types import Info
import strawberry
from core import types, models
from core.mutations._generic import make_delete, make_pin


@strawberry.input(description="Input for creating or ensuring a microscope objective")
class ObjectiveInput:
    """Input for creating or ensuring a microscope objective"""

    serial_number: str = strawberry.field(description="The unique serial number of the objective")
    name: str | None = strawberry.field(default=None, description="The name of the objective")
    na: float | None = strawberry.field(default=None, description="The numerical aperture of the objective")
    magnification: float | None = strawberry.field(default=None, description="The magnification of the objective")
    immersion: str | None = strawberry.field(default=None, description="The immersion medium of the objective (e.g. oil, water, air)")


@strawberry.input(description="Input for pinning or unpinning an objective for quick access")
class PinObjectiveInput:
    """Input for pinning or unpinning an objective for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the objective to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


pin_objective = make_pin(models.Objective, PinObjectiveInput, types.Objective)


@strawberry.input(description="Input for deleting an objective by ID")
class DeleteObjectiveInput:
    """Input for deleting an objective by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the objective to delete")


delete_objective = make_delete(models.Objective, DeleteObjectiveInput)


def create_objective(
    info: Info,
    input: ObjectiveInput,
) -> types.Objective:
    view = models.Objective.objects.create(
        organization=info.context.request.organization,
        serial_number=input.serial_number,
        na=input.na,
        name=input.name,
        magnification=input.magnification,
        immersion=input.immersion,
    )
    return view


def ensure_objective(
    info: Info,
    input: ObjectiveInput,
) -> types.Objective:
    view, _ = models.Objective.objects.get_or_create(
        serial_number=input.serial_number,
        organization=info.context.request.organization,
        defaults=dict(
            name=input.name,
            na=input.na,
            magnification=input.magnification,
            immersion=input.immersion,
        ),
    )
    return view
