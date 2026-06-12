from kante.types import Info
import strawberry
from core import types, models
import datetime
from core.scoping import get_for_org


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


def pin_era(
    info: Info,
    input: PinEraInput,
) -> types.Era:
    raise NotImplementedError("TODO")


def create_era(
    info: Info,
    input: EraInput,
) -> types.Era:
    view = models.Era.objects.create(
        name=input.name,
        begin=input.begin,
    )
    return view


def delete_era(
    info: Info,
    input: DeleteEraInput,
) -> strawberry.ID:
    item = get_for_org(models.Era, info, id=input.id)
    item.delete()
    return input.id
