from kante.types import Info
import strawberry

from core import types, models, scalars

import kante
from pydantic import BaseModel
from core import enums
from core.scoping import get_for_org
from core.creation import CreationContext
from core.logic import graph as graph_logic
from core.mutations._generic import assert_can_delete, self_owner


class SelectorInputModel(BaseModel):
    axis: str
    index: int


@kante.pydantic_input(SelectorInputModel, description="Input for pinning an ROI to a coordinate on a discrete axis, e.g. a timepoint or a channel")
class SelectorInput:
    """Input for pinning an ROI to a coordinate on a discrete axis."""

    axis: str = strawberry.field(description="The name of the discrete axis, e.g. 't' or 'c'")
    index: int = strawberry.field(description="The coordinate along that axis")


class CreateDataRoiInputModel(BaseModel):
    coordinate_system: str
    kind: enums.RoiKind
    name: str | None = None
    vectors: list[list[float]] | None = None
    selectors: list[SelectorInputModel] | None = None


@kante.pydantic_input(CreateDataRoiInputModel, description="Input for drawing a region of interest in a coordinate system")
class CreateDataRoiInput:
    """Input for drawing a region of interest in a coordinate system."""

    coordinate_system: strawberry.ID = strawberry.field(
        description="The coordinate system this ROI's geometry is expressed in -- normally a dataset's INTRINSIC system or a lens' system. The ROI belongs to that system, not to a scene: delete the scene and the ROI survives"
    )
    kind: enums.RoiKind = strawberry.field(description="The kind of ROI to create, e.g. 'polygon', 'path', 'point'. This determines how the vectors are interpreted and drawn")
    name: str | None = strawberry.field(default=None, description="Optional name for the ROI. Defaults to a name derived from its coordinate system")
    vectors: list[scalars.ThreeDVector] = strawberry.field(default=None, description="The ROI's vertices, in the coordinate system's own coordinates (pixels for an intrinsic or lens system)")
    selectors: list[SelectorInput] | None = strawberry.field(
        default=None, description="The discrete coordinates this ROI is pinned to, e.g. [{axis: 't', index: 0}, {axis: 'c', index: 0}]. An axis the ROI does not pin is one it spans"
    )


def create_data_roi(
    info: Info,
    input: CreateDataRoiInput,
) -> types.DataRoi:
    """Draw a region of interest in a coordinate system, and derive its bounding box in intrinsic space."""
    model = input.to_pydantic()

    ctx = CreationContext.from_info(info)
    system = get_for_org(models.CoordinateSystem, info, id=model.coordinate_system)

    vectors = model.vectors or []

    # Pushed through every corner of the box, not just the two extremes: an
    # affine-transformed AABB is not an AABB, and min/max alone is strictly too
    # small under any rotation or shear. Intrinsic, not world -- see DataRoi.
    intrinsic_bbox = graph_logic.compute_intrinsic_bbox(system, vectors)

    roi = models.DataRoi.objects.create(
        coordinate_system=system,
        name=model.name or f"ROI on {system.name}",
        kind=model.kind.value,
        vectors=vectors,
        # Stored keyed by axis name -- the same shape as CoordinateAnchor.coordinates,
        # and GIN-queryable. The API keeps the typed list shape.
        selectors={selector.axis: selector.index for selector in (model.selectors or [])},
        intrinsic_bbox=intrinsic_bbox,
        created_with_transforms=graph_logic.transform_version(system),
        creator=ctx.user,
        **ctx.provenance_kwargs(),
    )

    return roi


@kante.input(description="Delete a DataRoi by ID")
class DeleteDataRoiInput:
    id: strawberry.ID = strawberry.field(description="The ID of the DataRoi to delete")


def delete_data_roi(info: Info, input: DeleteDataRoiInput) -> bool:
    """Delete a DataRoi by ID."""
    try:
        roi = get_for_org(models.DataRoi, info, id=input.id)
        # The ROI carries its own creator: its parent is now a CoordinateSystem whose
        # dataset is nullable (a world or atlas system has none), so inheriting
        # ownership from a dataset would dereference None.
        assert_can_delete(info, roi, self_owner)
        roi.delete()
        return True
    except models.DataRoi.DoesNotExist:
        return False
