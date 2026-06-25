from kante.types import Info
import strawberry
from core import types, models
from core.mutations._generic import make_delete, make_pin


@strawberry.input(description="Input for creating a view collection to group views")
class ViewCollectionInput:
    """Input for creating a view collection to group views"""

    name: str = strawberry.field(description="The name of the view collection")


@strawberry.input(description="Input for deleting a view collection by ID")
class DeleteViewCollectionInput:
    """Input for deleting a view collection by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the view collection to delete")


@strawberry.input(description="Input for pinning or unpinning a view collection for quick access")
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
    view = models.ViewCollection.objects.create(
        name=input.name,
        organization=info.context.request.organization,
    )
    return view
