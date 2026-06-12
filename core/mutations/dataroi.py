from kante.types import Info
import strawberry

from core import types, models, scalars

import kante
from pydantic import BaseModel
from core import base_models, inputs, enums
from core.scoping import get_for_org


class CreateDataRoiInputModel(BaseModel):
    dataset: str
    kind: enums.RoiKind
    x_dim: str
    y_dim: str
    z_dim: str | None = None
    vectors: list[list[float]] | None = None
    slices: list[base_models.SliceInputModel] | None = None
    drawn_on_lens: str | None = None


@kante.pydantic_input(CreateDataRoiInputModel, description="Input type for creating an image from an array-like object")
class CreateDataRoiInput:
    dataset: strawberry.ID = strawberry.field(description="The ID of an existing dataset to create the lens from. If not provided, a new dataset will be created for the lens")
    kind: enums.RoiKind = strawberry.field(description="The kind of ROI to create, e.g. 'polygon', 'path', 'point', or 'slice'. This can determine the specific format of the vectors field and how the ROI is interpreted and visualized in the frontend")
    x_dim: str = strawberry.field(description="The name of the x dimension in the data source")
    y_dim: str = strawberry.field(description="The name of the y dimension in the data source")
    z_dim: str | None = strawberry.field(default=None, description="The name of the z dimension in the data source, if applicable")
    vectors: list[scalars.ThreeDVector] = strawberry.field(
        default=None, description="A list of vectors that define the ROI, where the specific format of the vectors can depend on the kind of ROI being created (e.g. a path ROI might be defined by a list of points, while a polygon ROI might be defined by a list of vertices)"
    )
    slices: list[inputs.SliceInput] = strawberry.field(default=None, description="Optional list of choordinate anchors to associate with the image, which can specify specific positions along certain dimensions to anchor to and optional OME metadata for additional context about those dimensions")
    drawn_on_lens: strawberry.ID | None = strawberry.field(default=None, description="Optional ID of a lens that this ROI was drawn on, which can be used to link the ROI to a specific view or subset of the data for organizational purposes")


def create_data_roi(
    info: Info,
    input: CreateDataRoiInput,
) -> types.DataRoi:
    """
    Creates a Region of Interest using raw vectors and a discriminator kind,
    while maintaining high-speed spatial bounding boxes for the database.
    """
    model = input.to_pydantic()

    # 1. Fetch related provenance records
    dataset = get_for_org(models.ADataset, info, id=model.dataset)

    if model.drawn_on_lens:
        # only validates the lens is visible to this organization
        get_for_org(models.Lens, info, id=model.drawn_on_lens)

    x_dim = model.x_dim
    y_dim = model.y_dim
    z_dim = model.z_dim if model.z_dim else None

    x_min = None
    x_max = None
    y_min = None
    y_max = None
    z_min = None
    z_max = None

    # 3. Extract N-Dimensional Constraints (The "Non-Spatial" Slice)
    n_dim_constraints = {}
    if model.slices:
        for slc in model.slices:
            if slc.dim not in [x_dim, y_dim, z_dim]:
                n_dim_constraints[slc.dim] = {
                    "start": slc.start,
                    "stop": slc.stop,
                    "step": slc.step,
                }
            else:
                # If the slice applies to a spatial dimension, we can also use it to set the bounding box
                if slc.dim == x_dim:
                    x_min = slc.start
                    x_max = slc.stop
                elif slc.dim == y_dim:
                    y_min = slc.start
                    y_max = slc.stop
                elif z_dim and slc.dim == z_dim:
                    z_min = slc.start
                    z_max = slc.stop

    # 4. Initialize the ROI Model
    # Directly storing the raw vectors and the kind discriminator
    roi = models.DataRoi(
        dataset=dataset,
        name=f"ROI on {dataset.name}",
        kind=model.kind.value,  # The frontend discriminator
        vectors=model.vectors or [],  # The raw coordinate payload
        x_dim=x_dim,
        y_dim=y_dim,
        z_dim=z_dim,
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        z_min=z_min,
        z_max=z_max,
        constraints=n_dim_constraints,
    )

    # Save and return
    roi.save()
    return roi


@kante.input(description="Delete a DataRoi by ID")
class DeleteDataRoiInput:
    id: strawberry.ID = strawberry.field(description="The ID of the DataRoi to delete")


def delete_data_roi(info: Info, input: DeleteDataRoiInput) -> bool:
    """
    Deletes a DataRoi by ID.
    """
    try:
        roi = get_for_org(models.DataRoi, info, id=input.id)
        roi.delete()
        return True
    except models.DataRoi.DoesNotExist:
        return False
