from kante.types import Info
import strawberry

from core import types, models, scalars, enums
from datalayer.datalayer import get_current_datalayer
import json

import kante
from pydantic import BaseModel, Field
from lightpath.inputs.types import LightpathGraphInput
from lightpath.inputs.models import LightpathGraphInputModel
from core.creation import CreationContext
from core.inputs.coords import AxisInput, AxisInputModel, CalibrationSpecInput, CalibrationSpecInputModel
from core.logic import coords as coords_logic
from core.logic import graph as graph_logic
from core.mutations._generic import make_delete, self_owner, dataset_owner
from core.scoping import get_for_org
import logging

logger = logging.getLogger(__name__)


class DimAnchorInputModel(BaseModel):
    dim: str
    value: int


@kante.pydantic_input(DimAnchorInputModel, description="Input type for a dimension anchor, which specifies a dimension and a value to anchor to")
class DimAnchorInput:
    dim: str = strawberry.field(description="The dimension to anchor to, e.g. 'x', 'y', 'z', 'c', or 't'")
    value: int = strawberry.field(description="The value to anchor the dimension to, e.g. 0 for the first position along that dimension")


class OmeMetadataInputModel(BaseModel):
    metadata_string: str = Field(..., description="The OME metadata as a JSON string")


@kante.pydantic_input(OmeMetadataInputModel, description="Input type for OME metadata")
class OmeMetadataInput:
    metadata_string: str = strawberry.field(description="The OME metadata as a JSON string")


class ValueHistogramInputModel(BaseModel):
    histogram: list[float] = Field(..., description="The histogram of the pixel values (y values)")
    bins: list[float] = Field(..., description="The bin indices of the histogram (x values)")
    min: float | None = Field(None, description="The minimum pixel value of the histogram")
    max: float | None = Field(None, description="The maximum pixel value of the histogram")
    p1: float | None = Field(None, description="The 1st percentile pixel value of the histogram")
    p99: float | None = Field(None, description="The 99th percentile pixel value of the histogram")


@kante.pydantic_input(ValueHistogramInputModel, description="Input type for a value histogram, which specifies the histogram of pixel values along certain dimensions to provide additional context about the distribution of pixel values in an image")
class ValueHistogramInput:
    histogram: list[float] = strawberry.field(description="The histogram of the pixel values (y values)")
    bins: list[float] = strawberry.field(description="The bin indices of the histogram (x values)")
    min: float | None = strawberry.field(default=None, description="The minimum pixel value of the histogram")
    max: float | None = strawberry.field(default=None, description="The maximum pixel value of the histogram")
    p1: float | None = strawberry.field(default=None, description="The 1st percentile pixel value of the histogram")
    p99: float | None = strawberry.field(default=None, description="The 99th percentile pixel value of the histogram")


class LabelInputModel(BaseModel):
    label: str


@kante.pydantic_input(LabelInputModel, description="Input type for a label, which specifies a label to associate with a coordinate anchor or an image")
class LabelInput:
    label: str = strawberry.field(description="The label to associate with the coordinate anchor or image, which can provide additional context about the content of the image or the significance of the coordinate anchor")


class CoordinateAnchorInputModel(BaseModel):
    dim_anchors: list[DimAnchorInputModel]
    ome_metadata: OmeMetadataInputModel | None = None
    value_histogram: ValueHistogramInputModel | None = None
    label: LabelInputModel | None = None
    light_graph: LightpathGraphInputModel | None = None


@kante.pydantic_input(CoordinateAnchorInputModel, description="Input type for a coordinate anchor, which specifies a list of dimension anchors to anchor to")
class CoordinateAnchorInput:
    dim_anchors: list[DimAnchorInput] = strawberry.field(description="A list of dimension anchors to anchor to, e.g. [{'dim': 'z', 'value': 0}, {'dim': 't', 'value': 5}] to anchor to the first position along the z dimension and the sixth position along the t dimension")
    ome_metadata: OmeMetadataInput | None = strawberry.field(default=None, description="Optional OME metadata to associate with the choordinate anchor, which can provide additional context about the dimensions being anchored to")
    value_histogram: ValueHistogramInput | None = strawberry.field(default=None, description="Optional value histogram to associate with the coordinate anchor, which can provide additional context about the distribution of pixel values along the anchored dimensions")
    label: LabelInput | None = strawberry.field(default=None, description="Optional label to associate with the coordinate anchor, which can provide additional context about the significance of the coordinate anchor or the content of the image at that coordinate")
    light_graph: LightpathGraphInput | None = strawberry.field(default=None, description="Optional lightpath graph to associate with the coordinate anchor, which can provide additional context about the optical path that was used to acquire the image at that coordinate")


class ScaleInputModel(BaseModel):
    level: int
    array: str = Field(..., description="The array-like object to create the image from")


@kante.pydantic_input(ScaleInputModel, description="Input type for one pyramid level: the array backing it. Its scale is derived from its actual shape, never supplied")
class ScaleInput:
    """Input for one pyramid level."""

    level: int = strawberry.field(description="The level of the scale, where 0 is the highest resolution scale and higher levels are lower resolution scales")
    array: scalars.ArrayLike = strawberry.field(description="The array-like object to create the image from")
    scale_method: str | None = strawberry.field(default=None, description="The method used to create the scale, e.g. 'nearest', 'bilinear', 'bicubic'. Recorded as provenance on the level's transformation")


class CreateDatasetInputModel(BaseModel):
    data: str
    scales: list[ScaleInputModel]
    name: str
    dataset: strawberry.ID | None = None
    axes: list[AxisInputModel]
    calibration: CalibrationSpecInputModel | None = None
    anchors: list[CoordinateAnchorInputModel] | None = None


@kante.pydantic_input(CreateDatasetInputModel, description="Input type for creating an array dataset. Its axes are structural (name and kind); physical units, if known, arrive as an optional calibration")
class CreateADatasetInput:
    """Input for creating an array dataset."""

    data: scalars.ArrayLike = strawberry.field(description="The array-like object to create the image from")
    scales: list[ScaleInput] = strawberry.field(description="The lower-resolution pyramid levels. Each level's absolute scale is derived from its actual shape against level 0's -- a pyramid whose axes do not halve cleanly is described correctly, and no caller can supply a wrong factor")
    name: str = strawberry.field(description="The name of the image")
    axes: list[AxisInput] = strawberry.field(
        description="The dataset's structural axes, in array order (slowest-varying first). They must be ordered by type -- time, then channel and custom types, then space -- and are rejected if not. They carry no units: the intrinsic space is the pixel grid"
    )
    calibration: CalibrationSpecInput | None = strawberry.field(
        default=None,
        description="An optional calibration to create alongside the dataset: a PHYSICAL coordinate system plus the edge mapping intrinsic pixels into it. Sugar for a separate createCalibration call -- ingest usually knows the pixel size up front. Omit it for data with no physical interpretation",
    )
    anchors: list[CoordinateAnchorInput] | None = strawberry.field(
        default=None, description="Optional list of choordinate anchors to associate with the image, which can specify specific positions along certain dimensions to anchor to and optional OME metadata for additional context about those dimensions"
    )


def create_adataset(
    info: Info,
    input: CreateADatasetInput,
) -> types.ADataset:
    """Create an array dataset, its coordinate systems and the edges placing every level in its intrinsic space."""
    model = input.to_pydantic()

    datalayer = get_current_datalayer()

    data_store = get_for_org(models.ZarrStore, info, id=model.data)
    data_store.fill_info(datalayer)

    base_shape = data_store.shape
    assert len(base_shape) == len(model.axes), "Dimension length mismatch. You provided {} axes but the data has {} dimensions".format(len(model.axes), len(base_shape))

    axis_specs = [coords_logic.AxisSpec(name=axis.name, type=axis.type.value) for axis in model.axes]

    # A hard validation rather than a test: the render axes are derived from the
    # *position* of the spatial axes, so out-of-order axes do not make that
    # derivation fail, they make it quietly wrong.
    coords_logic.assert_axis_type_order(axis_specs)

    ctx = CreationContext.from_info(info)
    dataset = models.ADataset.objects.create(
        name=model.name,
        creator=ctx.user,
        organization=ctx.organization,
        **ctx.provenance_kwargs(),
    )

    intrinsic = models.CoordinateSystem.objects.create(
        name=f"{model.name}/intrinsic",
        kind=enums.CoordinateSystemKindChoices.INTRINSIC.value,
        intrinsic_of=dataset,
        creator=ctx.user,
        organization=ctx.organization,
    )
    graph_logic.create_pixel_axes(intrinsic, model.axes)

    levels = [(0, data_store)] + [(scale.level, get_for_org(models.ZarrStore, info, id=scale.array)) for scale in model.scales]

    for level, store in levels:
        if level != 0:
            store.fill_info(datalayer)
            assert len(store.shape) == len(base_shape), "Dimension length mismatch for scale level {}: the data has {} dimensions but level 0 has {}".format(level, len(store.shape), len(base_shape))

        data_array = models.DataArray.objects.create(
            level=level,
            store=store,
            dataset=dataset,
            shape=store.shape,
            chunk_shape=store.chunks,
        )

        array_system = models.CoordinateSystem.objects.create(
            name=f"{model.name}/{level}",
            kind=enums.CoordinateSystemKindChoices.ARRAY.value,
            data_array=data_array,
            creator=ctx.user,
            organization=ctx.organization,
        )
        graph_logic.create_pixel_axes(array_system, model.axes)

        graph_logic.create_level_edge(
            array_system=array_system,
            intrinsic=intrinsic,
            shape_0=base_shape,
            shape_level=store.shape,
            axis_specs=axis_specs,
            ctx=ctx,
        )

    if model.calibration:
        graph_logic.create_calibration(
            dataset=dataset,
            name=model.calibration.name,
            axes=model.calibration.axes,
            scale=model.calibration.scale,
            translation=model.calibration.translation,
            affine=model.calibration.affine,
            ctx=ctx,
        )

    for anchor in model.anchors or []:
        coordinate_anchor = models.CoordinateAnchor.objects.create(
            dataset=dataset,
            coordinates={anchor.dim: anchor.value for anchor in anchor.dim_anchors},
        )

        if anchor.ome_metadata:
            logger.debug("Creating OME metadata for coordinate anchor with coordinates %s", coordinate_anchor.coordinates)
            models.OmeMetadata.objects.create(
                anchor=coordinate_anchor,
                metadata={} if anchor.ome_metadata.metadata_string == "" else json.loads(anchor.ome_metadata.metadata_string),
            )

        if anchor.value_histogram:
            models.ValueHistogram.objects.create(
                anchor=coordinate_anchor,
                histogram=anchor.value_histogram.histogram,
                bins=anchor.value_histogram.bins,
                min=anchor.value_histogram.min,
                max=anchor.value_histogram.max,
                p1=anchor.value_histogram.p1,
                p99=anchor.value_histogram.p99,
            )

        if anchor.label:
            models.ChannelLabel.objects.create(
                anchor=coordinate_anchor,
                label=anchor.label.label,
            )

        if anchor.light_graph:
            models.LightPath.objects.create(
                anchor=coordinate_anchor,
                graph=anchor.light_graph.model_dump(),
            )

    return dataset


class DeleteADatasetInputModel(BaseModel):
    id: str = Field(description="The ID of the array dataset to delete")


@kante.pydantic_input(DeleteADatasetInputModel, description="Input for deleting an array dataset by ID")
class DeleteADatasetInput:
    """Input for deleting an array dataset by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the array dataset to delete")


class DeleteDataArrayInputModel(BaseModel):
    id: str = Field(description="The ID of the data array to delete")


@kante.pydantic_input(DeleteDataArrayInputModel, description="Input for deleting a data array by ID")
class DeleteDataArrayInput:
    """Input for deleting a data array by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the data array to delete")


delete_adataset = make_delete(models.ADataset, DeleteADatasetInput, owner=self_owner)
delete_data_array = make_delete(models.DataArray, DeleteDataArrayInput, owner=dataset_owner)
