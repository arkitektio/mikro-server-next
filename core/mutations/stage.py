from kante.types import Info
import strawberry
from core import types, models
from core.mutations._generic import make_delete, make_pin


@strawberry.input
class StageInput:
    name: str
    instrument: strawberry.ID | None = None


@strawberry.input()
class DeleteStageInput:
    id: strawberry.ID


@strawberry.input
class PinStageInput:
    id: strawberry.ID
    pin: bool


pin_stage = make_pin(models.Stage, PinStageInput, types.Stage)


delete_stage = make_delete(models.Stage, DeleteStageInput)


def create_stage(
    info: Info,
    input: StageInput,
) -> types.Stage:
    view = models.Stage.objects.create(
        name=input.name,
        instrument=input.instrument,
        organization=info.context.request.organization,
        creator=info.context.request.user,
    )
    return view
