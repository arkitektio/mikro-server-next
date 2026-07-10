from kante.types import Info
import kante
import strawberry
from pydantic import BaseModel, Field
from core import types, models
import datetime
from core.creation import CreationContext
from core.mutations._generic import make_delete, make_pin, self_owner


class EraInputModel(BaseModel):
    name: str = Field(description="The name of the era")
    begin: datetime.datetime | None = Field(default=None, description="The datetime at which the era begins")


@kante.pydantic_input(EraInputModel, description="Input for creating an era, a time period to which timepoint views relate")
class EraInput:
    """Input for creating an era, a time period to which timepoint views relate"""

    name: str = strawberry.field(description="The name of the era")
    begin: datetime.datetime | None = strawberry.field(default=None, description="The datetime at which the era begins")


class DeleteEraInputModel(BaseModel):
    id: str = Field(description="The ID of the era to delete")


@kante.pydantic_input(DeleteEraInputModel, description="Input for deleting an era by ID")
class DeleteEraInput:
    """Input for deleting an era by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the era to delete")


class PinEraInputModel(BaseModel):
    id: str = Field(description="The ID of the era to pin or unpin")
    pin: bool = Field(description="True to pin, false to unpin")


@kante.pydantic_input(PinEraInputModel, description="Input for pinning or unpinning an era for quick access")
class PinEraInput:
    """Input for pinning or unpinning an era for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the era to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


pin_era = make_pin(models.Era, PinEraInput, types.Era)


def create_era(
    info: Info,
    input: EraInput,
) -> types.Era:
    parsed = input.to_pydantic()
    ctx = CreationContext.from_info(info)
    view = models.Era.objects.create(
        name=parsed.name,
        begin=parsed.begin,
        organization=ctx.organization,
        **ctx.provenance_kwargs(),
    )
    return view


delete_era = make_delete(models.Era, DeleteEraInput, owner=self_owner)
