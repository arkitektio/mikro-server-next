from kante.types import Info
import strawberry
from core import types, models


@strawberry.input
class ObjectiveInput:
    serial_number: str
    name: str | None = None
    na: float | None = None
    magnification: float | None = None
    immersion: str | None = None


def create_objective(
    info: Info,
    input: ObjectiveInput,
) -> types.Objective:
    view = models.Objective.objects.create(
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
        defaults=dict(
            name=input.name,
            na=input.na,
            magnification=input.magnification,
            immersion=input.immersion,
        ),
    )
    return view
