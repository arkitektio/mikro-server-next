from kante.types import Info
import kante
import strawberry
from pydantic import BaseModel, Field
from core import types, models
from core.mutations._generic import make_delete, make_pin


class ViewCollectionInputModel(BaseModel):
    name: str = Field(description="The name of the view collection")


@kante.pydantic_input(ViewCollectionInputModel, description="Input for creating a view collection to group views")
class ViewCollectionInput:
    """Input for creating a view collection to group views"""

    name: str = strawberry.field(description="The name of the view collection")


class DeleteViewCollectionInputModel(BaseModel):
    id: str = Field(description="The ID of the view collection to delete")


@kante.pydantic_input(DeleteViewCollectionInputModel, description="Input for deleting a view collection by ID")
class DeleteViewCollectionInput:
    """Input for deleting a view collection by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the view collection to delete")


class PinViewCollectionInputModel(BaseModel):
    id: str = Field(description="The ID of the view collection to pin or unpin")
    pin: bool = Field(description="True to pin, false to unpin")


@kante.pydantic_input(PinViewCollectionInputModel, description="Input for pinning or unpinning a view collection for quick access")
class PinViewCollectionInput:
    """Input for pinning or unpinning a view collection for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the view collection to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


pin_view_collection = make_pin(models.ViewCollection, PinViewCollectionInput, types.ViewCollection)


delete_view_collection = make_delete(models.ViewCollection, DeleteViewCollectionInput)


def create_view_collection(
    info: Info,
    input: ViewCollectionInput,
) -> types.ViewCollection:
    parsed = input.to_pydantic()
    view = models.ViewCollection.objects.create(
        name=parsed.name,
        organization=info.context.request.organization,
    )
    return view
