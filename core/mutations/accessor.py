import strawberry
from core import models
from strawberry import ID
import strawberry_django
from core.mutations._generic import make_delete


@strawberry_django.input(models.Accessor, description="Base input describing which table columns and rows an accessor refers to")
class AccessorInput:
    """Base input describing which table columns and rows an accessor refers to"""

    keys: list[str] = strawberry.field(description="The column keys of the table this accessor refers to")
    min_index: int | None = strawberry.field(default=None, description="The minimum row index this accessor applies to")
    max_index: int | None = strawberry.field(default=None, description="The maximum row index this accessor applies to")


@strawberry_django.input(models.LabelAccessor, description="Input for a label accessor on a table, linking columns to a pixel view (without the table reference)")
class PartialLabelAccessorInput(AccessorInput):
    """Input for a label accessor on a table, linking columns to a pixel view (without the table reference)"""

    pixel_view: ID = strawberry.field(description="The ID of the pixel view the label values refer to")
    pass


@strawberry_django.input(models.ImageAccessor, description="Input for an image accessor on a table, linking columns to an image (without the table reference)")
class PartialImageAccessorInput(AccessorInput):
    """Input for an image accessor on a table, linking columns to an image (without the table reference)"""

    image: ID = strawberry.field(description="The ID of the image the accessor values refer to")
    pass


@strawberry_django.input(models.AffineTransformationView, description="Input for creating a label accessor that links table columns to a pixel view")
class LabelAccessorInput(PartialLabelAccessorInput):
    """Input for creating a label accessor that links table columns to a pixel view"""

    table: ID = strawberry.field(description="The ID of the table to create the accessor on")


@strawberry_django.input(models.LabelView, description="Input for creating an image accessor that links table columns to an image")
class ImageAccessorInput(PartialImageAccessorInput):
    """Input for creating an image accessor that links table columns to an image"""

    table: ID = strawberry.field(description="The ID of the table to create the accessor on")


def accessor_kwargs_from_input(input: LabelAccessorInput) -> dict:
    is_global = all(
        x is None
        for x in [
            input.min_index,
            input.max_index,
        ]
    )

    is_global = is_global and len(input.keys) == 0

    return dict(
        keys=input.keys,
        min_index=input.min_index,
        max_index=input.max_index,
        is_global=is_global,
    )


@strawberry.input(description="Input for deleting an accessor by ID")
class DeleteAccesorInput:
    """Input for deleting an accessor by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the accessor to delete")


delete_accessor = make_delete(models.Accessor, DeleteAccesorInput)
