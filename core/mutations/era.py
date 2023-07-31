from kante.types import Info
import strawberry
from core import types, models
import datetime


@strawberry.input
class EraInput:
    name: str
    begin: datetime.datetime | None = None


def create_era(
    info: Info,
    input: EraInput,
) -> types.Era:
    view = models.Era.objects.create(
        name=input.name,
        begin=input.begin,
    )
    return view
