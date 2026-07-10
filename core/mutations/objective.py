from kante.types import Info
import kante
import strawberry
from pydantic import BaseModel, Field
from core import types, models
from core.mutations._generic import make_delete, make_pin


class ObjectiveInputModel(BaseModel):
    serial_number: str = Field(description="The unique serial number of the objective")
    name: str | None = Field(default=None, description="The name of the objective")
    na: float | None = Field(default=None, description="The numerical aperture of the objective")
    magnification: float | None = Field(default=None, description="The magnification of the objective")
    immersion: str | None = Field(default=None, description="The immersion medium of the objective (e.g. oil, water, air)")


@kante.pydantic_input(ObjectiveInputModel, description="Input for creating or ensuring a microscope objective")
class ObjectiveInput:
    """Input for creating or ensuring a microscope objective"""

    serial_number: str = strawberry.field(description="The unique serial number of the objective")
    name: str | None = strawberry.field(default=None, description="The name of the objective")
    na: float | None = strawberry.field(default=None, description="The numerical aperture of the objective")
    magnification: float | None = strawberry.field(default=None, description="The magnification of the objective")
    immersion: str | None = strawberry.field(default=None, description="The immersion medium of the objective (e.g. oil, water, air)")


class PinObjectiveInputModel(BaseModel):
    id: str = Field(description="The ID of the objective to pin or unpin")
    pin: bool = Field(description="True to pin, false to unpin")


@kante.pydantic_input(PinObjectiveInputModel, description="Input for pinning or unpinning an objective for quick access")
class PinObjectiveInput:
    """Input for pinning or unpinning an objective for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the objective to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


pin_objective = make_pin(models.Objective, PinObjectiveInput, types.Objective)


class DeleteObjectiveInputModel(BaseModel):
    id: str = Field(description="The ID of the objective to delete")


@kante.pydantic_input(DeleteObjectiveInputModel, description="Input for deleting an objective by ID")
class DeleteObjectiveInput:
    """Input for deleting an objective by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the objective to delete")


delete_objective = make_delete(models.Objective, DeleteObjectiveInput)


def create_objective(
    info: Info,
    input: ObjectiveInput,
) -> types.Objective:
    parsed = input.to_pydantic()
    view = models.Objective.objects.create(
        organization=info.context.request.organization,
        serial_number=parsed.serial_number,
        na=parsed.na,
        name=parsed.name,
        magnification=parsed.magnification,
        immersion=parsed.immersion,
    )
    return view


def ensure_objective(
    info: Info,
    input: ObjectiveInput,
) -> types.Objective:
    parsed = input.to_pydantic()
    view, _ = models.Objective.objects.get_or_create(
        serial_number=parsed.serial_number,
        organization=info.context.request.organization,
        defaults=dict(
            name=parsed.name,
            na=parsed.na,
            magnification=parsed.magnification,
            immersion=parsed.immersion,
        ),
    )
    return view
