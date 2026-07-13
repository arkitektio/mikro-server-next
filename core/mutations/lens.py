from kante.types import Info
import strawberry

from core import types, models, enums

import kante
from pydantic import BaseModel, Field
from core import base_models, inputs
from core.creation import CreationContext
from core.logic import graph as graph_logic
from core.scoping import get_for_org
from core.mutations._generic import make_delete, dataset_owner


class CreateLensInputModel(BaseModel):
    dataset: str
    slices: list[base_models.SliceInputModel] | None = None


@kante.pydantic_input(CreateLensInputModel, description="Input type for creating an image from an array-like object")
class CreateLensInput:
    dataset: strawberry.ID = strawberry.field(description="The ID of an existing dataset to create the lens from. If not provided, a new dataset will be created for the lens")
    slices: list[inputs.SliceInput] = strawberry.field(default=None, description="Optional list of choordinate anchors to associate with the image, which can specify specific positions along certain dimensions to anchor to and optional OME metadata for additional context about those dimensions")


def create_lens(
    info: Info,
    input: CreateLensInput,
) -> types.Lens:
    """Create a lens, its coordinate system, and the edge placing it back in its dataset.

    The lens' shape and dims are not written: they follow from the dataset and the
    slices, and a second copy could only drift from the first.
    """
    model = input.to_pydantic()

    dataset = get_for_org(models.ADataset, info, id=model.dataset)
    intrinsic = dataset.intrinsic_coordinate_system
    if intrinsic is None:
        raise ValueError(f"Dataset {dataset.pk} has no intrinsic coordinate system")

    base = dataset.data_arrays.order_by("level").first()
    if base is None:
        raise ValueError(f"Dataset {dataset.pk} has no level-0 data array to place the lens against")

    ctx = CreationContext.from_info(info)
    slices = model.slices or []

    lens = models.Lens.objects.create(
        dataset=dataset,
        slices=[slice.model_dump() for slice in slices],
    )

    lens_system = models.CoordinateSystem.objects.create(
        name=f"{dataset.name}/lens/{lens.pk}",
        kind=enums.CoordinateSystemKindChoices.ARRAY.value,
        lens=lens,
        creator=ctx.user,
        organization=ctx.organization,
    )
    # A lens sees the same axes as the array it slices; only the extent changes.
    graph_logic.create_axes(lens_system, dataset.axes, as_array_indices=True)

    # Without this edge, slicing shifts voxel coordinates and nothing records the
    # shift: an ROI drawn on a cropped lens has no defined path back to its dataset.
    graph_logic.create_lens_edge(
        lens_system=lens_system,
        parent_system=base.coordinate_system,
        dataset_dims=dataset.dims_list,
        slices=lens.slices_list,
        ctx=ctx,
    )

    return lens


class DeleteLensInputModel(BaseModel):
    id: str = Field(description="The ID of the lens to delete")


@kante.pydantic_input(DeleteLensInputModel, description="Input for deleting a lens by ID")
class DeleteLensInput:
    """Input for deleting a lens by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the lens to delete")


delete_lens = make_delete(models.Lens, DeleteLensInput, owner=dataset_owner)
