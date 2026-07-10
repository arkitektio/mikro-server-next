import kante
import strawberry
from pydantic import BaseModel, Field
from core import models
from strawberry import ID
from core.mutations._generic import make_delete, table_owner


class AccessorInputModel(BaseModel):
    keys: list[str] = Field(description="The column keys of the table this accessor refers to")
    min_index: int | None = Field(default=None, description="The minimum row index this accessor applies to")
    max_index: int | None = Field(default=None, description="The maximum row index this accessor applies to")


@kante.pydantic_input(AccessorInputModel, description="Base input describing which table columns and rows an accessor refers to")
class AccessorInput:
    """Base input describing which table columns and rows an accessor refers to"""

    keys: list[str] = strawberry.field(description="The column keys of the table this accessor refers to")
    min_index: int | None = strawberry.field(default=None, description="The minimum row index this accessor applies to")
    max_index: int | None = strawberry.field(default=None, description="The maximum row index this accessor applies to")


class PartialLabelAccessorInputModel(AccessorInputModel):
    pixel_view: str = Field(description="The ID of the pixel view the label values refer to")


@kante.pydantic_input(PartialLabelAccessorInputModel, description="Input for a label accessor on a table, linking columns to a pixel view (without the table reference)")
class PartialLabelAccessorInput(AccessorInput):
    """Input for a label accessor on a table, linking columns to a pixel view (without the table reference)"""

    pixel_view: ID = strawberry.field(description="The ID of the pixel view the label values refer to")
    pass


class PartialImageAccessorInputModel(AccessorInputModel):
    image: str = Field(description="The ID of the image the accessor values refer to")


@kante.pydantic_input(PartialImageAccessorInputModel, description="Input for an image accessor on a table, linking columns to an image (without the table reference)")
class PartialImageAccessorInput(AccessorInput):
    """Input for an image accessor on a table, linking columns to an image (without the table reference)"""

    image: ID = strawberry.field(description="The ID of the image the accessor values refer to")
    pass


class LabelAccessorInputModel(PartialLabelAccessorInputModel):
    table: str = Field(description="The ID of the table to create the accessor on")


@kante.pydantic_input(LabelAccessorInputModel, description="Input for creating a label accessor that links table columns to a pixel view")
class LabelAccessorInput(PartialLabelAccessorInput):
    """Input for creating a label accessor that links table columns to a pixel view"""

    table: ID = strawberry.field(description="The ID of the table to create the accessor on")


class ImageAccessorInputModel(PartialImageAccessorInputModel):
    table: str = Field(description="The ID of the table to create the accessor on")


@kante.pydantic_input(ImageAccessorInputModel, description="Input for creating an image accessor that links table columns to an image")
class ImageAccessorInput(PartialImageAccessorInput):
    """Input for creating an image accessor that links table columns to an image"""

    table: ID = strawberry.field(description="The ID of the table to create the accessor on")


def accessor_kwargs_from_input(input: AccessorInputModel) -> dict:
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


class DeleteAccesorInputModel(BaseModel):
    id: str = Field(description="The ID of the accessor to delete")


@kante.pydantic_input(DeleteAccesorInputModel, description="Input for deleting an accessor by ID")
class DeleteAccesorInput:
    """Input for deleting an accessor by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the accessor to delete")


delete_accessor = make_delete(models.Accessor, DeleteAccesorInput, owner=table_owner)
