from kante.types import Info
import strawberry
from core import types, models
import datetime
from core.creation import CreationContext
from core.mutations._generic import make_delete, make_pin


@strawberry.input(description="Input for creating an era, a time period to which timepoint views relate")
class EraInput:
    """Input for creating an era, a time period to which timepoint views relate"""

    name: str = strawberry.field(description="The name of the era")
    begin: datetime.datetime | None = strawberry.field(default=None, description="The datetime at which the era begins")


@strawberry.input(description="Input for deleting an era by ID")
class DeleteEraInput:
    """Input for deleting an era by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the era to delete")


@strawberry.input(description="Input for pinning or unpinning an era for quick access")
class PinEraInput:
    """Input for pinning or unpinning an era for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the era to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


pin_era = make_pin(models.Era, PinEraInput, types.Era)


def create_era(
    info: Info,
    input: EraInput,
) -> types.Era:
    ctx = CreationContext.from_info(info)
    view = models.Era.objects.create(
        name=input.name,
        begin=input.begin,
        organization=ctx.organization,
        **ctx.provenance_kwargs(),
    )
    return view


delete_era = make_delete(models.Era, DeleteEraInput)
