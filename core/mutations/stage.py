from kante.types import Info
import strawberry
from core import types, models


@strawberry.input
class StageInput:
    name: str
    instrument: strawberry.ID | None = None


def create_stage(
    info: Info,
    input: StageInput,
) -> types.Stage:
    view = models.Stage.objects.create(
        name=input.name,
        instrument=input.instrument,
    )
    return view
