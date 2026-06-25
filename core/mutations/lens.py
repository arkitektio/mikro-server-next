from kante.types import Info
import strawberry

from core import types, models

import kante
from pydantic import BaseModel
from core import base_models, inputs
from core.scoping import get_for_org


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
    model = input.to_pydantic()

    dataset = get_for_org(models.ADataset, info, id=model.dataset)

    shape = []
    dims = []
    dim_descriptors = []
    slice_dict = {s.dim: s for s in model.slices}

    for dim, dim_size, dim_descriptor in zip(dataset.dims_list, dataset.shape_list, dataset.dim_descriptors_list):
        if dim in slice_dict:
            custom_slice = slice_dict[dim]

            # Create a standard Python slice. It naturally accepts None for missing bounds.
            py_slice = slice(custom_slice.start, custom_slice.stop, custom_slice.step)

            # .indices() resolves start, end, and step against the actual dimension size.
            # This safely handles negatives, Nones, and prevents out-of-bounds errors.
            start, stop, step = py_slice.indices(dim_size)

            # len(range(...)) calculates the exact resulting size mathematically correctly.
            shape.append(len(range(start, stop, step)))
            dims.append(dim)
            dim_descriptors.append(dim_descriptor)
        else:
            # If no slice applies to this dimension, keep the original size
            shape.append(dim_size)
            dims.append(dim)
            dim_descriptors.append(dim_descriptor)

    x = models.Lens.objects.create(
        dataset=dataset,
        slices=[slice.model_dump() for slice in model.slices],
        shape=shape,
        dims=dims,
        dim_descriptors=[dim_descriptor.model_dump() for dim_descriptor in dim_descriptors],
    )

    return x
