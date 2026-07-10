from kante.types import Info
import kante
import strawberry
from pydantic import BaseModel, Field
from core import types, models
from core.mutations._generic import make_delete, make_pin


class InstrumentInputModel(BaseModel):
    serial_number: str = Field(description="The unique serial number of the instrument")
    manufacturer: str | None = Field(default=None, description="The manufacturer of the instrument")
    name: str | None = Field(default=None, description="The name of the instrument")
    model: str | None = Field(default=None, description="The model of the instrument")


@kante.pydantic_input(InstrumentInputModel, description="Input for creating or ensuring a microscope instrument")
class InstrumentInput:
    """Input for creating or ensuring a microscope instrument"""

    serial_number: str = strawberry.field(description="The unique serial number of the instrument")
    manufacturer: str | None = strawberry.field(default=None, description="The manufacturer of the instrument")
    name: str | None = strawberry.field(default=None, description="The name of the instrument")
    model: str | None = strawberry.field(default=None, description="The model of the instrument")


class PinInstrumentInputModel(BaseModel):
    id: str = Field(description="The ID of the instrument to pin or unpin")
    pin: bool = Field(description="True to pin, false to unpin")


@kante.pydantic_input(PinInstrumentInputModel, description="Input for pinning or unpinning an instrument for quick access")
class PinInstrumentInput:
    """Input for pinning or unpinning an instrument for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the instrument to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


pin_instrument = make_pin(models.Instrument, PinInstrumentInput, types.Instrument)


class DeleteInstrumentInputModel(BaseModel):
    id: str = Field(description="The ID of the instrument to delete")


@kante.pydantic_input(DeleteInstrumentInputModel, description="Input for deleting an instrument by ID")
class DeleteInstrumentInput:
    """Input for deleting an instrument by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the instrument to delete")


delete_instrument = make_delete(models.Instrument, DeleteInstrumentInput)


def create_instrument(
    info: Info,
    input: InstrumentInput,
) -> types.Instrument:
    parsed = input.to_pydantic()
    view, _ = models.Instrument.objects.update_or_create(
        serial_number=parsed.serial_number,
        organization=info.context.request.organization,
        defaults=dict(
            manufacturer=parsed.manufacturer,
            name=parsed.name,
            model=parsed.model,
        ),
    )
    return view


def ensure_instrument(
    info: Info,
    input: InstrumentInput,
) -> types.Instrument:
    parsed = input.to_pydantic()
    view, _ = models.Instrument.objects.get_or_create(
        serial_number=parsed.serial_number,
        organization=info.context.request.organization,
        defaults=dict(
            manufacturer=parsed.manufacturer,
            name=parsed.name,
            model=parsed.model,
        ),
    )
    return view
