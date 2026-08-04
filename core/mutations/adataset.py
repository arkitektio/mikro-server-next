from kante.types import Info
import strawberry

from core import types, models, scalars
from datalayer.datalayer import get_current_datalayer
import json

import kante
from pydantic import BaseModel, Field
from lightpath.inputs.types import LightpathGraphInput
from optikit.inputs import OptikitStateInput
from optikit.models import OptikitStateModel
from lightpath.inputs.models import LightpathGraphInputModel
from core.creation import CreationContext
from core.inputs.coords import AxisInput, AxisInputModel, DerivedFromInput, DerivedFromSpec
from core.inputs.file_link import SourceFileInput, SourceFileInputModel
from core.logic import coordinate_system as coordinate_system_logic
from core.logic import file_link as file_link_logic
from core.logic import coords as coords_logic
from core.logic import graph as graph_logic
from core.mutations._generic import assert_can_delete, make_delete, self_owner, dataset_owner
from core.scoping import get_for_org
import logging

logger = logging.getLogger(__name__)


class AxisAnchorInputModel(BaseModel):
    axis: str
    value: int


@kante.pydantic_input(AxisAnchorInputModel, description="Input type for an axis anchor, which pins one axis to one discrete position")
class AxisAnchorInput:
    axis: str = strawberry.field(description="The axis to anchor to, e.g. 'x', 'y', 'z', 'c', or 't'")
    value: int = strawberry.field(description="The position to anchor the axis to, e.g. 0 for the first position along that axis")


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


class PhasorHistogramInputModel(BaseModel):
    axis: str = Field(..., description="The axis the phasor was taken over")
    counts: list[float] = Field(..., description="The flattened bins x bins density")
    # Optional with a None default rather than a real default, because the strawberry bridge
    # passes None through for an unset field; the defaults are applied where they are written.
    harmonic: int | None = Field(None, description="The harmonic the phasor was taken at")
    bins: int | None = Field(None, description="The resolution of the square (g, s) density grid")
    g_min: float | None = Field(None)
    g_max: float | None = Field(None)
    s_min: float | None = Field(None)
    s_max: float | None = Field(None)
    total: int | None = Field(None)
    calibrated: bool | None = Field(None)
    profile: list[float] | None = Field(None)


@kante.pydantic_input(PhasorHistogramInputModel, description="Input type for a phasor distribution: the 2D (g, s) density of a phasor taken over one axis at one harmonic, plus the summed profile it came from. Persisted so a client can pick a value range for a phasor overlay without reading the cube")
class PhasorHistogramInput:
    axis: str = strawberry.field(description="The axis the phasor was taken over, e.g. 'tau'. Must be a MICROTIME or SPECTRUM axis of the dataset")
    counts: list[float] = strawberry.field(description="The flattened bins x bins (g, s) density, row-major with s outermost")
    harmonic: int | None = strawberry.field(default=None, description="The harmonic the phasor was taken at (default 1)")
    bins: int | None = strawberry.field(default=None, description="The resolution of the square density grid (default 256)")
    g_min: float | None = strawberry.field(default=None, description="The lower g bound of the grid (default 0)")
    g_max: float | None = strawberry.field(default=None, description="The upper g bound of the grid (default 1)")
    s_min: float | None = strawberry.field(default=None, description="The lower s bound of the grid (default 0)")
    s_max: float | None = strawberry.field(default=None, description="The upper s bound of the grid (default 0.6)")
    total: int | None = strawberry.field(default=None, description="The number of pixels that contributed, so counts can be normalized")
    calibrated: bool | None = strawberry.field(default=None, description="Whether the g/s were reference-corrected when computed (default false)")
    profile: list[float] | None = strawberry.field(default=None, description="The summed profile along the phasor axis: a decay for a MICROTIME axis, a spectrum for a SPECTRUM one")


class PhasorCalibrationInputModel(BaseModel):
    axis: str = Field(..., description="The axis the correction applies to")
    harmonic: int | None = Field(None, description="The harmonic the correction applies at")
    phase_offset: float | None = Field(None, description="The phase correction in radians")
    modulation_factor: float | None = Field(None, description="The modulation correction")
    reference: str | None = Field(None, description="What the correction was measured against")


@kante.pydantic_input(PhasorCalibrationInputModel, description="Input type for an instrument-response correction: the phase offset and modulation factor taking a raw phasor to a calibrated one")
class PhasorCalibrationInput:
    axis: str = strawberry.field(description="The axis the correction applies to, e.g. 'tau'. Must be a MICROTIME or SPECTRUM axis of the dataset")
    harmonic: int | None = strawberry.field(default=None, description="The harmonic the correction applies at (default 1)")
    phase_offset: float | None = strawberry.field(default=None, description="The phase correction in radians, added to each pixel's phase")
    modulation_factor: float | None = strawberry.field(default=None, description="The modulation correction, multiplied into each pixel's modulus")
    reference: str | None = strawberry.field(default=None, description="What the correction was measured against, e.g. 'Rhodamine 6G, 4.1 ns'")


class LabelInputModel(BaseModel):
    label: str


@kante.pydantic_input(LabelInputModel, description="Input type for a label, which specifies a label to associate with a coordinate anchor or an image")
class LabelInput:
    label: str = strawberry.field(description="The label to associate with the coordinate anchor or image, which can provide additional context about the content of the image or the significance of the coordinate anchor")


class CoordinateAnchorInputModel(BaseModel):
    axis_anchors: list[AxisAnchorInputModel]
    microscope: OptikitStateModel | None = None
    ome_metadata: OmeMetadataInputModel | None = None
    value_histogram: ValueHistogramInputModel | None = None
    label: LabelInputModel | None = None
    light_graph: LightpathGraphInputModel | None = None
    phasor_histogram: PhasorHistogramInputModel | None = None
    phasor_calibration: PhasorCalibrationInputModel | None = None


@kante.pydantic_input(CoordinateAnchorInputModel, description="Input type for a coordinate anchor, which specifies a list of dimension anchors to anchor to")
class CoordinateAnchorInput:
    axis_anchors: list[AxisAnchorInput] = strawberry.field(description="A list of dimension anchors to anchor to, e.g. [{'axis': 'z', 'value': 0}, {'axis': 't', 'value': 5}] to anchor to the first position along the z dimension and the sixth position along the t dimension")
    microscope: OptikitStateInput | None = strawberry.field(default=None, description="Optional recorded microscope (Optikit) state to associate with the coordinate anchor: the hardware truth -- stage pose, environment, per-device settings -- at this coordinate, as composable typed input (quantities like '100.5 um' or '20 mW' where the setting carries a unit). An acquisition fact, recorded at ingest like the other spokes")
    ome_metadata: OmeMetadataInput | None = strawberry.field(default=None, description="Optional OME metadata to associate with the coordinate anchor, which can provide additional context about the axes being anchored to")
    value_histogram: ValueHistogramInput | None = strawberry.field(default=None, description="Optional value histogram to associate with the coordinate anchor, which can provide additional context about the distribution of pixel values along the anchored dimensions")
    label: LabelInput | None = strawberry.field(default=None, description="Optional label to associate with the coordinate anchor, which can provide additional context about the significance of the coordinate anchor or the content of the image at that coordinate")
    light_graph: LightpathGraphInput | None = strawberry.field(default=None, description="Optional lightpath graph to associate with the coordinate anchor, which can provide additional context about the optical path that was used to acquire the image at that coordinate")
    phasor_histogram: PhasorHistogramInput | None = strawberry.field(default=None, description="Optional phasor distribution to associate with the coordinate anchor, for a converter that already computed one. It is more usually attached after ingest with createPhasorHistogram, since computing it means reading the cube")
    phasor_calibration: PhasorCalibrationInput | None = strawberry.field(default=None, description="Optional instrument-response correction to associate with the coordinate anchor, taking a raw phasor at this coordinate to a calibrated one")


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
    axes: list[AxisInputModel]
    anchors: list[CoordinateAnchorInputModel] | None = None
    derived_from: list[DerivedFromSpec] | None = None
    source_files: list[SourceFileInputModel] | None = None


@kante.pydantic_input(CreateDatasetInputModel, description="Input type for creating an array dataset. Its axes are structural (name and kind); physical units, if known, arrive afterwards through createCoordinateSystem with a registrations entry naming the dataset")
class CreateADatasetInput:
    """Input for creating an array dataset."""

    data: scalars.ArrayLike = strawberry.field(description="The array-like object to create the image from")
    scales: list[ScaleInput] = strawberry.field(description="The lower-resolution pyramid levels. Each level's absolute scale is derived from its actual shape against level 0's -- a pyramid whose axes do not halve cleanly is described correctly, and no caller can supply a wrong factor")
    name: str = strawberry.field(description="The name of the image")
    axes: list[AxisInput] = strawberry.field(
        description="The dataset's structural axes, in array order (slowest-varying first). They must be ordered by type -- time, then channel and custom types, then space -- and are rejected if not. They carry no units: the intrinsic space is the pixel grid"
    )
    anchors: list[CoordinateAnchorInput] | None = strawberry.field(
        default=None, description="Optional list of coordinate anchors to associate with the dataset, each pinning metadata spokes (OME metadata, histograms, labels) to specific positions along certain axes"
    )
    derived_from: list[DerivedFromInput] | None = strawberry.field(
        default=None,
        description="Optional statement of where this dataset's pixels came from: one entry per source lens -- a deconvolution or resample has one, a fusion of two channels or tiles has several -- each carrying the map back into that lens' space. Stored as edges of the coordinate graph, not as labels: the derived dataset then inherits its sources' placements, so refining a source's registration moves it too, and a layer over it resolves `pathToWorld` through a source. The order is the priority: the first entry is the primary parent (it drives `derivedFrom` order and the lineage root); later entries are additional sources whose edges are just as walkable. An UNMAPPABLE entry records history only and may not precede a mappable one",
    )
    source_files: list[SourceFileInput] | None = strawberry.field(
        default=None,
        description=(
            "Optional statement of which files this dataset's arrays were converted from -- the CZI or LIF a converter read to write this Zarr, named per series. **Not a "
            "`derivedFrom` entry, deliberately**: a derivation is an edge of the coordinate graph and every one of them relates two spaces, while a file has no space at all. "
            "This records lineage between bytes and data, claims no geometry, and leaves the graph untouched"
        ),
    )


def _parse_json_object(value: str | None, field: str) -> dict:
    """Parse a JSON-object string a client sent, and say so when it is not what it claims to be.

    The spoke columns are JSONFields, so the string must be a JSON *object*. It is an easy
    field to get wrong -- OME metadata is classically XML, and an empty upload is a string of
    whitespace -- and a bare `json.loads` reports every one of those the same way:
    "Expecting value: line 1 column 1 (char 0)", with no hint that it was talking about this
    field rather than, say, the zarr metadata read a few lines earlier.
    """
    if value is None or value.strip() == "":
        return {}

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        head = value.strip()[:80]
        hint = " It looks like XML; OME-XML must be converted to JSON before it is sent." if head.startswith("<") else ""
        raise ValueError(f"{field} is not valid JSON ({exc}).{hint} It starts: {head!r}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"{field} must be a JSON object, not a {type(parsed).__name__}.")

    return parsed


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
    # The space first, then the data that lives in it. Under residence nothing points from a
    # space back at its data, so there is no cycle to break and no second write: one INSERT
    # each, in the order the dependency actually runs.
    intrinsic = models.CoordinateSystem.objects.create(
        name=f"{model.name}/intrinsic",
        creator=ctx.user,
        organization=ctx.organization,
    )
    dataset = models.ADataset.objects.create(
        name=model.name,
        coordinate_system=intrinsic,
        creator=ctx.user,
        organization=ctx.organization,
        **ctx.provenance_kwargs(),
    )
    graph_logic.create_pixel_axes(intrinsic, model.axes)

    levels = [(0, data_store)] + [(scale.level, get_for_org(models.ZarrStore, info, id=scale.array)) for scale in model.scales]

    for level, store in levels:
        if level != 0:
            store.fill_info(datalayer)
            assert len(store.shape) == len(base_shape), "Dimension length mismatch for scale level {}: the data has {} dimensions but level 0 has {}".format(level, len(store.shape), len(base_shape))

        # Level 0 lives in the dataset's own grid -- it *is* that grid -- so it points at
        # the same space rather than getting a duplicate node joined by an all-ones SCALE.
        # Only a level whose space really differs gets one of its own.
        array_system = intrinsic
        if level != 0:
            array_system = models.CoordinateSystem.objects.create(
                name=f"{model.name}/{level}",
                creator=ctx.user,
                organization=ctx.organization,
            )

        data_array = models.DataArray.objects.create(
            level=level,
            store=store,
            dataset=dataset,
            coordinate_system=array_system,
            shape=store.shape,
            chunk_shape=store.chunks,
        )

        if level == 0:
            continue

        graph_logic.create_pixel_axes(array_system, model.axes)

        graph_logic.create_level_edge(
            array_system=array_system,
            intrinsic=intrinsic,
            shape_0=base_shape,
            shape_level=store.shape,
            axis_specs=axis_specs,
            ctx=ctx,
        )

    if model.derived_from:
        coordinate_system_logic.write_derivation_edges(info, name=dataset.name, own_system=intrinsic, derived_from=model.derived_from, ctx=ctx)

    file_link_logic.write_file_links(info, container=dataset, source_files=model.source_files or [], ctx=ctx)

    for anchor in model.anchors or []:
        coordinate_anchor = models.CoordinateAnchor.objects.create(
            dataset=dataset,
            coordinates={axis_anchor.axis: axis_anchor.value for axis_anchor in anchor.axis_anchors},
        )

        if anchor.microscope:
            # The same write path as the lightpath graph: the typed model's dump IS the
            # stored JSON, so the column never grows a shape the types cannot express.
            models.OptikitState.objects.create(
                anchor=coordinate_anchor,
                state=anchor.microscope.model_dump(),
            )

        if anchor.ome_metadata:
            logger.debug("Creating OME metadata for coordinate anchor with coordinates %s", coordinate_anchor.coordinates)
            models.OmeMetadata.objects.create(
                anchor=coordinate_anchor,
                metadata=_parse_json_object(anchor.ome_metadata.metadata_string, "anchor.omeMetadata.metadataString"),
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
            # The storage graph's dump, not the input's: `to_graph` builds the union the
            # read side rebuilds, so the column cannot grow a shape the types cannot
            # express -- which is what the comment above claims for every spoke, and what
            # dumping the input model directly quietly broke for this one.
            models.LightPath.objects.create(
                anchor=coordinate_anchor,
                graph=anchor.light_graph.to_graph().model_dump(mode="json"),
            )

        if anchor.phasor_histogram:
            _write_phasor_histogram(coordinate_anchor, anchor.phasor_histogram, axis_specs)

        if anchor.phasor_calibration:
            _write_phasor_calibration(coordinate_anchor, anchor.phasor_calibration, axis_specs)

    return dataset


# ---------------------------------------------------------------------------
# Phasor metadata
#
# Both spokes describe a *phasor*: the DFT of a pixel's profile along one axis at
# one harmonic. Neither the axis nor the harmonic is an array coordinate, so the
# anchor's `coordinates` dict cannot pin them -- which is why both spokes carry
# them as columns, are ForeignKeys rather than the usual OneToOne, and are keyed
# on (anchor, axis, harmonic).
#
# They are attached post-ingest far more often than at ingest: a distribution
# means reading the cube, and a calibration means measuring a reference dye.
# Until now there was no way to attach any metadata to a dataset after ingest at
# all -- anchors were only ever created inside create_adataset.
# ---------------------------------------------------------------------------


def _assert_phasor_axis(axis_name: str, axis_specs: list[coords_logic.AxisSpec]) -> None:
    """Check the axis a phasor was taken over is one a DFT means something over.

    The same rule the render node enforces (`core.mutations.layer.assert_phasor_axis`), applied
    at the metadata boundary too: a density stored against the `z` axis is not a phasor, and
    nothing downstream could tell it from one.
    """
    axis = next((spec for spec in axis_specs if spec.name == axis_name), None)
    if axis is None:
        raise ValueError(f"axis '{axis_name}' is not an axis of this dataset ({[spec.name for spec in axis_specs]})")
    if not coords_logic.is_phasor_axis(axis.type):
        raise ValueError(f"axis '{axis_name}' is a {axis.type} axis, not a MICROTIME or SPECTRUM axis. A phasor is only defined over a continuously sampled axis -- an arrival-time histogram or a spectrum.")


def _write_phasor_histogram(anchor: "models.CoordinateAnchor", input: PhasorHistogramInputModel, axis_specs: list[coords_logic.AxisSpec]) -> "models.PhasorHistogram":
    """Create or replace the phasor distribution at (anchor, axis, harmonic)."""
    _assert_phasor_axis(input.axis, axis_specs)

    bins = input.bins if input.bins is not None else 256
    if len(input.counts) != bins * bins:
        raise ValueError(f"counts has {len(input.counts)} entries but bins is {bins}, which needs {bins * bins}. It is the flattened bins x bins density grid, row-major with s outermost.")

    histogram, _ = models.PhasorHistogram.objects.update_or_create(
        anchor=anchor,
        axis=input.axis,
        harmonic=input.harmonic if input.harmonic is not None else 1,
        defaults={
            "bins": bins,
            "counts": input.counts,
            "g_min": input.g_min if input.g_min is not None else 0.0,
            "g_max": input.g_max if input.g_max is not None else 1.0,
            "s_min": input.s_min if input.s_min is not None else 0.0,
            "s_max": input.s_max if input.s_max is not None else 0.6,
            "total": input.total,
            "calibrated": input.calibrated if input.calibrated is not None else False,
            "profile": input.profile or [],
        },
    )
    return histogram


def _write_phasor_calibration(anchor: "models.CoordinateAnchor", input: PhasorCalibrationInputModel, axis_specs: list[coords_logic.AxisSpec]) -> "models.PhasorCalibration":
    """Create or replace the instrument-response correction at (anchor, axis, harmonic)."""
    _assert_phasor_axis(input.axis, axis_specs)

    calibration, _ = models.PhasorCalibration.objects.update_or_create(
        anchor=anchor,
        axis=input.axis,
        harmonic=input.harmonic if input.harmonic is not None else 1,
        defaults={
            "phase_offset": input.phase_offset,
            "modulation_factor": input.modulation_factor,
            "reference": input.reference,
        },
    )
    return calibration


def _get_or_create_anchor(dataset: "models.ADataset", axis_anchors: list[AxisAnchorInputModel] | None) -> "models.CoordinateAnchor":
    """The anchor at these coordinates on this dataset, creating it if it is new.

    Get-or-create rather than create: a phasor distribution and an intensity histogram at the
    same coordinate are two spokes of *one* anchor, and a second anchor at the same coordinates
    would split the metadata of one pixel across two anchors.
    """
    coordinates = {axis_anchor.axis: axis_anchor.value for axis_anchor in axis_anchors or []}
    anchor, _ = models.CoordinateAnchor.objects.get_or_create(dataset=dataset, coordinates=coordinates)
    return anchor


class CreatePhasorHistogramInputModel(PhasorHistogramInputModel):
    dataset: str = Field(description="The ID of the dataset the phasor was computed from")
    axis_anchors: list[AxisAnchorInputModel] | None = Field(None, description="The coordinates the distribution is pinned to")


@kante.pydantic_input(CreatePhasorHistogramInputModel, description="Attach a phasor distribution to a dataset: the 2D (g, s) density of a phasor taken over one axis at one harmonic. Computed after ingest by a task that reads the cube; recomputing at the same harmonic replaces it, while a second harmonic lands beside the first")
class CreatePhasorHistogramInput:
    dataset: strawberry.ID = strawberry.field(description="The ID of the dataset the phasor was computed from")
    axis: str = strawberry.field(description="The axis the phasor was taken over, e.g. 'tau'. Must be a MICROTIME or SPECTRUM axis of the dataset")
    counts: list[float] = strawberry.field(description="The flattened bins x bins (g, s) density, row-major with s outermost")
    axis_anchors: list[AxisAnchorInput] | None = strawberry.field(default=None, description="The coordinates the distribution is pinned to, e.g. [{'axis': 'c', 'value': 0}] for one detection channel. Omit for a distribution global over the dataset")
    harmonic: int | None = strawberry.field(default=None, description="The harmonic the phasor was taken at (default 1)")
    bins: int | None = strawberry.field(default=None, description="The resolution of the square density grid (default 256)")
    g_min: float | None = strawberry.field(default=None, description="The lower g bound of the grid (default 0)")
    g_max: float | None = strawberry.field(default=None, description="The upper g bound of the grid (default 1)")
    s_min: float | None = strawberry.field(default=None, description="The lower s bound of the grid (default 0)")
    s_max: float | None = strawberry.field(default=None, description="The upper s bound of the grid (default 0.6)")
    total: int | None = strawberry.field(default=None, description="The number of pixels that contributed, so counts can be normalized")
    calibrated: bool | None = strawberry.field(default=None, description="Whether the g/s were reference-corrected when computed (default false)")
    profile: list[float] | None = strawberry.field(default=None, description="The summed profile along the phasor axis: a decay for a MICROTIME axis, a spectrum for a SPECTRUM one")


def create_phasor_histogram(info: Info, input: CreatePhasorHistogramInput) -> types.PhasorHistogram:
    """Attach a phasor distribution to a dataset."""
    model = input.to_pydantic()

    dataset = get_for_org(models.ADataset, info, id=model.dataset)
    anchor = _get_or_create_anchor(dataset, model.axis_anchors)
    return _write_phasor_histogram(anchor, model, dataset.axis_specs)


class CreatePhasorCalibrationInputModel(PhasorCalibrationInputModel):
    dataset: str = Field(description="The ID of the dataset the correction applies to")
    axis_anchors: list[AxisAnchorInputModel] | None = Field(None, description="The coordinates the correction is pinned to")


@kante.pydantic_input(CreatePhasorCalibrationInputModel, description="Attach an instrument-response correction to a dataset, taking a raw phasor to a calibrated one. Measured once per detector from a reference acquisition. Its absence is legitimate: an uncalibrated phasor still renders, its hue is just not traceable to an absolute lifetime")
class CreatePhasorCalibrationInput:
    dataset: strawberry.ID = strawberry.field(description="The ID of the dataset the correction applies to")
    axis: str = strawberry.field(description="The axis the correction applies to, e.g. 'tau'. Must be a MICROTIME or SPECTRUM axis of the dataset")
    axis_anchors: list[AxisAnchorInput] | None = strawberry.field(default=None, description="The coordinates the correction is pinned to, e.g. [{'axis': 'c', 'value': 0}] -- the IRF differs per detector. Omit for a correction global over the dataset")
    harmonic: int | None = strawberry.field(default=None, description="The harmonic the correction applies at (default 1)")
    phase_offset: float | None = strawberry.field(default=None, description="The phase correction in radians, added to each pixel's phase")
    modulation_factor: float | None = strawberry.field(default=None, description="The modulation correction, multiplied into each pixel's modulus")
    reference: str | None = strawberry.field(default=None, description="What the correction was measured against, e.g. 'Rhodamine 6G, 4.1 ns'")


def create_phasor_calibration(info: Info, input: CreatePhasorCalibrationInput) -> types.PhasorCalibration:
    """Attach an instrument-response correction to a dataset."""
    model = input.to_pydantic()

    dataset = get_for_org(models.ADataset, info, id=model.dataset)
    anchor = _get_or_create_anchor(dataset, model.axis_anchors)
    return _write_phasor_calibration(anchor, model, dataset.axis_specs)


class UpdateADatasetInputModel(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None


@kante.pydantic_input(
    UpdateADatasetInputModel,
    description="Input for renaming or redescribing a dataset. These two fields are the whole of what is editable: the arrays, the axes and the coordinate systems built from them are fixed at creation, and a recomputation is a new dataset",
)
class UpdateADatasetInput:
    """Input for updating a dataset."""

    id: strawberry.ID = strawberry.field(description="The ID of the dataset to update")
    name: str | None = strawberry.field(default=None, description="A new name")
    description: str | None = strawberry.field(default=None, description="A new description")


def update_adataset(info: Info, input: UpdateADatasetInput) -> types.ADataset:
    """Rename a dataset, or redescribe it. Those two fields are the whole of what is editable.

    Deliberately not here: the arrays, the axes, and the coordinate systems derived from them.
    The dataset's geometry is not a set of columns to be corrected -- its dimensions live on
    its INTRINSIC system's axes, and ``Axis.order`` is written by enumeration with the rest of
    the graph measured against it, so an axis edit is a *different space*, not a repair of this
    one. ``updateCoordinateSystem`` refuses a dataset's own system for that reason; it serves
    anchors alone. A recomputation is a new dataset.

    Both fields are audited: ``ADataset.provenance`` records a history row per save, attributed
    to the client, user and task the change happened under, and ``ADataset.provenanceEntries``
    reads them back. That is the whole point of routing a rename through a mutation rather than
    leaving the column writable by whatever happens to hold the row.
    """
    model = input.to_pydantic()
    dataset = get_for_org(models.ADataset, info, id=model.id)
    if model.name is not None:
        dataset.name = model.name
    if model.description is not None:
        dataset.description = model.description
    dataset.save()
    return dataset


class SetDefaultSceneInputModel(BaseModel):
    """A dataset and the scene it nominates, or null to clear."""

    dataset: str = Field(description="The dataset to nominate a scene for")
    scene: str | None = Field(default=None, description="The scene to nominate, or null to clear the nomination")


@kante.pydantic_input(SetDefaultSceneInputModel, description="Nominate the scene to open for a dataset, and take its thumbnail from")
class SetDefaultSceneInput:
    """Input for nominating a dataset's default scene."""

    dataset: strawberry.ID = strawberry.field(description="The dataset to nominate a scene for")
    scene: strawberry.ID | None = strawberry.field(default=None, description="The scene to nominate. Null clears the nomination, and the dataset then reports no `latestSnapshot`")


def nominate_default_scene(info: Info, dataset: "models.ADataset", scene: "models.Scene | None") -> "models.ADataset":
    """Write one dataset's nomination, having checked the caller may.

    **Guarded on the dataset, not the scene**, and that is not a detail: `Scene` carries no
    `creator` column at all -- which is why `delete_scene` passes `owner=None` -- so a check on
    the scene has nothing to read. The dataset does carry one, and the dataset is what this
    writes. Without the check any member of the organization could repoint any dataset's
    thumbnail.

    Org scoping is the caller's job (both ids arrive through `get_for_org`); this is the
    ownership half, which scoping does not cover.
    """
    assert_can_delete(info, dataset, self_owner)
    dataset.default_scene = scene
    dataset.save(update_fields=["default_scene"])
    return dataset


def set_default_scene(info: Info, input: SetDefaultSceneInput) -> types.ADataset:
    """Nominate the scene to open for a dataset, or clear the nomination.

    No check that the scene actually shows the dataset. Two dataset-to-scene relations already
    exist and disagree -- layer-based (`ADataset.scenes`) and the anchor-based rule this field
    replaced -- so validating against either would silently pick one as authoritative and make
    the nomination a claim about placement, which is exactly what it must not be.
    """
    model = input.to_pydantic()
    dataset = get_for_org(models.ADataset, info, id=model.dataset)
    scene = get_for_org(models.Scene, info, id=model.scene) if model.scene else None
    return nominate_default_scene(info, dataset, scene)


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
