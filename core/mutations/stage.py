from kante.types import Info
import strawberry
from core import types, models
from core.creation import CreationContext
from core.mutations._generic import make_delete, make_pin


@strawberry.input(description="Input for creating a stage, a physical coordinate system for positioning images")
class StageInput:
    """Input for creating a stage, a physical coordinate system for positioning images"""

    name: str = strawberry.field(description="The name of the stage")
    instrument: strawberry.ID | None = strawberry.field(default=None, description="The ID of the instrument this stage belongs to")


@strawberry.input(description="Input for deleting a stage by ID")
class DeleteStageInput:
    """Input for deleting a stage by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the stage to delete")


@strawberry.input(description="Input for pinning or unpinning a stage for quick access")
class PinStageInput:
    """Input for pinning or unpinning a stage for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the stage to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


pin_stage = make_pin(models.Stage, PinStageInput, types.Stage)


delete_stage = make_delete(models.Stage, DeleteStageInput)


def create_stage(
    info: Info,
    input: StageInput,
) -> types.Stage:
    ctx = CreationContext.from_info(info)
    view = models.Stage.objects.create(
        name=input.name,
        instrument=input.instrument,
        creator=ctx.user,
        organization=ctx.organization,
        **ctx.provenance_kwargs(),
    )
    return view
