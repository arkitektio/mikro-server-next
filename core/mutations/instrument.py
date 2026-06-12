from kante.types import Info
import strawberry
from core import types, models
from core.mutations._generic import make_delete


@strawberry.input
class InstrumentInput:
    serial_number: str
    manufacturer: str | None = None
    name: str | None = None
    model: str | None = None


@strawberry.input
class PinInstrumentInput:
    id: strawberry.ID
    pin: bool


def pin_instrument(
    info: Info,
    input: PinInstrumentInput,
) -> types.Instrument:
    raise NotImplementedError("TODO")


@strawberry.input()
class DeleteInstrumentInput:
    id: strawberry.ID


delete_instrument = make_delete(models.Instrument, DeleteInstrumentInput)


def create_instrument(
    info: Info,
    input: InstrumentInput,
) -> types.Instrument:
    view, _ = models.Instrument.objects.update_or_create(
        serial_number=input.serial_number,
        organization=info.context.request.organization,
        defaults=dict(
            manufacturer=input.manufacturer,
            name=input.name,
            model=input.model,
        ),
    )
    return view


def ensure_instrument(
    info: Info,
    input: InstrumentInput,
) -> types.Instrument:
    view, _ = models.Instrument.objects.get_or_create(
        serial_number=input.serial_number,
        organization=info.context.request.organization,
        defaults=dict(
            manufacturer=input.manufacturer,
            name=input.name,
            model=input.model,
        ),
    )
    return view
