from kante.types import Info
import strawberry
from core import types, models


@strawberry.input
class InstrumentInput:
    serial_number: str
    manufacturer: str | None = None
    name: str | None = None
    model: str | None = None


def create_instrument(
    info: Info,
    input: InstrumentInput,
) -> types.Instrument:
    view = models.Instrument.objects.create(
        serial_number=input.serial_number,
        manufacturer=input.manufacturer,
        name=input.name,
        model=input.model,
    )
    return view


def ensure_instrument(
    info: Info,
    input: InstrumentInput,
) -> types.Instrument:
    view, _ = models.Instrument.objects.get_or_create(
        serial_number=input.serial_number,
        defaults=dict(
            manufacturer=input.manufacturer,
            name=input.name,
            model=input.model,
        ),
    )
    return view
