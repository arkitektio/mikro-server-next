from kante.types import Info
import strawberry
from core import types, models
from core.mutations._generic import make_delete


@strawberry.input
class ObjectiveInput:
    serial_number: str
    name: str | None = None
    na: float | None = None
    magnification: float | None = None
    immersion: str | None = None


@strawberry.input
class PinObjectiveInput:
    id: strawberry.ID
    pin: bool


def pin_objective(
    info: Info,
    input: PinObjectiveInput,
) -> types.Objective:
    raise NotImplementedError("TODO")


@strawberry.input()
class DeleteObjectiveInput:
    id: strawberry.ID


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
