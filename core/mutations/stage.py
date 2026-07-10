from kante.types import Info
import kante
import strawberry
from pydantic import BaseModel, Field
from core import types, models
from core.creation import CreationContext
from core.mutations._generic import make_delete, make_pin, self_owner


class StageInputModel(BaseModel):
    name: str = Field(description="The name of the stage")
    instrument: str | None = Field(default=None, description="The ID of the instrument this stage belongs to")


@kante.pydantic_input(StageInputModel, description="Input for creating a stage, a physical coordinate system for positioning images")
class StageInput:
    """Input for creating a stage, a physical coordinate system for positioning images"""

    name: str = strawberry.field(description="The name of the stage")
    instrument: strawberry.ID | None = strawberry.field(default=None, description="The ID of the instrument this stage belongs to")


class DeleteStageInputModel(BaseModel):
    id: str = Field(description="The ID of the stage to delete")


@kante.pydantic_input(DeleteStageInputModel, description="Input for deleting a stage by ID")
class DeleteStageInput:
    """Input for deleting a stage by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the stage to delete")


class PinStageInputModel(BaseModel):
    id: str = Field(description="The ID of the stage to pin or unpin")
    pin: bool = Field(description="True to pin, false to unpin")


@kante.pydantic_input(PinStageInputModel, description="Input for pinning or unpinning a stage for quick access")
class PinStageInput:
    """Input for pinning or unpinning a stage for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the stage to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


pin_stage = make_pin(models.Stage, PinStageInput, types.Stage)


delete_stage = make_delete(models.Stage, DeleteStageInput, owner=self_owner)


def create_stage(
    info: Info,
    input: StageInput,
) -> types.Stage:
    parsed = input.to_pydantic()
    ctx = CreationContext.from_info(info)
    view = models.Stage.objects.create(
        name=parsed.name,
        instrument=parsed.instrument,
        creator=ctx.user,
        organization=ctx.organization,
        **ctx.provenance_kwargs(),
    )
    return view
