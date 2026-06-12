from kante.types import Info
import strawberry
from core import types, models
import datetime
from core.mutations._generic import make_delete, make_pin


@strawberry.input
class EraInput:
    name: str
    begin: datetime.datetime | None = None


@strawberry.input
class DeleteEraInput:
    id: strawberry.ID


@strawberry.input
class PinEraInput:
    id: strawberry.ID
    pin: bool


pin_era = make_pin(models.Era, PinEraInput, types.Era)


def create_era(
    info: Info,
    input: EraInput,
) -> types.Era:
    view = models.Era.objects.create(
        name=input.name,
        organization=info.context.request.organization,
        begin=input.begin,
    )
    return view


delete_era = make_delete(models.Era, DeleteEraInput)
