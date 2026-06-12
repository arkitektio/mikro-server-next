from kante.types import Info
import strawberry
from core import types, models
from core.mutations._generic import make_delete


@strawberry.input(description="Input for creating or ensuring a microscope instrument")
class InstrumentInput:
    """Input for creating or ensuring a microscope instrument"""

    serial_number: str = strawberry.field(description="The unique serial number of the instrument")
    manufacturer: str | None = strawberry.field(default=None, description="The manufacturer of the instrument")
    name: str | None = strawberry.field(default=None, description="The name of the instrument")
    model: str | None = strawberry.field(default=None, description="The model of the instrument")


@strawberry.input(description="Input for pinning or unpinning an instrument for quick access")
class PinInstrumentInput:
    """Input for pinning or unpinning an instrument for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the instrument to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


def pin_instrument(
    info: Info,
    input: PinInstrumentInput,
) -> types.Instrument:
    raise NotImplementedError("TODO")


@strawberry.input(description="Input for deleting an instrument by ID")
class DeleteInstrumentInput:
    """Input for deleting an instrument by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the instrument to delete")


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
