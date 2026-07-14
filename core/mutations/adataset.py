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


class PhasorHistogramInputModel(BaseModel):
    dim: str = Field(..., description="The axis the phasor was taken over")
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
    dim: str = strawberry.field(description="The axis the phasor was taken over, e.g. 'tau'. Must be a MICROTIME or SPECTRUM axis of the dataset")
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
    dim: str = Field(..., description="The axis the correction applies to")
    harmonic: int | None = Field(None, description="The harmonic the correction applies at")
    phase_offset: float | None = Field(None, description="The phase correction in radians")
    modulation_factor: float | None = Field(None, description="The modulation correction")
    reference: str | None = Field(None, description="What the correction was measured against")


@kante.pydantic_input(PhasorCalibrationInputModel, description="Input type for an instrument-response correction: the phase offset and modulation factor taking a raw phasor to a calibrated one")
class PhasorCalibrationInput:
    dim: str = strawberry.field(description="The axis the correction applies to, e.g. 'tau'. Must be a MICROTIME or SPECTRUM axis of the dataset")
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
    dim_anchors: list[DimAnchorInputModel]
    ome_metadata: OmeMetadataInputModel | None = None
    value_histogram: ValueHistogramInputModel | None = None
    label: LabelInputModel | None = None
    light_graph: LightpathGraphInputModel | None = None
    phasor_histogram: PhasorHistogramInputModel | None = None
    phasor_calibration: PhasorCalibrationInputModel | None = None


@kante.pydantic_input(CoordinateAnchorInputModel, description="Input type for a coordinate anchor, which specifies a list of dimension anchors to anchor to")
class CoordinateAnchorInput:
    dim_anchors: list[DimAnchorInput] = strawberry.field(description="A list of dimension anchors to anchor to, e.g. [{'dim': 'z', 'value': 0}, {'dim': 't', 'value': 5}] to anchor to the first position along the z dimension and the sixth position along the t dimension")
    ome_metadata: OmeMetadataInput | None = strawberry.field(default=None, description="Optional OME metadata to associate with the choordinate anchor, which can provide additional context about the dimensions being anchored to")
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


class DerivedFromInputModel(BaseModel):
    lens: str
    kind: enums.TransformKind = enums.TransformKind.IDENTITY
    scale: list[float] | None = None
    translation: list[float] | None = None
    affine: list[list[float]] | None = None
    input_axes: list[str] | None = None
    output_axes: list[str] | None = None


@kante.pydantic_input(
    DerivedFromInputModel,
    description="Input for stating where a new dataset's pixels came from: the lens it was computed from, and the map from its pixel grid back into that lens' space",
)
class DerivedFromInput:
    """Where a derived dataset's pixels came from, and how they map back."""

    lens: strawberry.ID = strawberry.field(description="The lens this dataset was computed from. The lens, not its dataset: a lens is a selection, and its own edge back to the dataset already carries the crop -- so pointing at it gets the rest of the chain for free")
    kind: enums.TransformKind = strawberry.field(default=enums.TransformKind.IDENTITY, description="How this dataset's pixel grid maps back into the source lens' space. IDENTITY for an in-place operation (a deconvolution, a segmentation), TRANSLATION for a crop, SCALE for a resample, BY_DIMENSION for a projection that drops an axis")
    scale: list[float] | None = strawberry.field(default=None, description="(SCALE) The per-axis factors, in this dataset's axis order")
    translation: list[float] | None = strawberry.field(default=None, description="(TRANSLATION) The per-axis offsets, in this dataset's axis order")
    affine: list[list[float]] | None = strawberry.field(default=None, description="(AFFINE / ROTATION) The matrix, M x (N+1)")
    input_axes: list[str] | None = strawberry.field(default=None, description="(BY_DIMENSION) The axes of THIS dataset the map acts on, e.g. ['t','c','y','x'] for a max-z projection")
    output_axes: list[str] | None = strawberry.field(default=None, description="(BY_DIMENSION) The axes of the source lens they map onto")


class CreateDatasetInputModel(BaseModel):
    data: str
    scales: list[ScaleInputModel]
    name: str
    axes: list[AxisInputModel]
    calibration: CalibrationSpecInputModel | None = None
    anchors: list[CoordinateAnchorInputModel] | None = None
    derived_from: DerivedFromInputModel | None = None


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
    derived_from: DerivedFromInput | None = strawberry.field(
        default=None,
        description="Optional statement that this dataset was computed from an existing lens -- a deconvolution, a segmentation, a projection, a resample -- and how its pixels map back into that lens' space. Stored as an edge of the coordinate graph, not as a label: the derived dataset then inherits its source's placement, so refining the source's registration moves it too, and a layer over it resolves `pathToWorld` through the source",
    )


#: The parameter each derivation kind reads. IDENTITY and BY_DIMENSION take none: an
#: identity has nothing to say, and a BY_DIMENSION's map is the axes it names.
_DERIVATION_PARAMS_BY_KIND: dict[str, str | None] = {
    enums.TransformKind.IDENTITY.value: None,
    enums.TransformKind.SCALE.value: "scale",
    enums.TransformKind.TRANSLATION.value: "translation",
    enums.TransformKind.AFFINE.value: "affine",
    enums.TransformKind.ROTATION.value: "affine",
    enums.TransformKind.BY_DIMENSION.value: None,
}


def _write_derivation_edge(
    info: Info,
    *,
    dataset: "models.ADataset",
    intrinsic: "models.CoordinateSystem",
    derived_from: DerivedFromInputModel,
    ctx: CreationContext,
) -> "models.Transformation":
    """Store the edge from a derived dataset's pixel grid back into the lens it came from.

    The whole point of recording the derivation as an *edge* rather than as an attribute:
    the relation between a deconvolution and the data it was computed from is a spatial
    fact, and the graph is where spatial facts live. Written here, the derived dataset
    inherits its source's placement -- refine the source's registration and the derived
    data moves with it, because there is only one copy of the fact -- and a layer over it
    resolves `pathToWorld` by walking through the source.

    The edge points at the source *lens'* system, in the same child-to-parent direction as
    every other structural edge (array -> intrinsic, lens -> array).
    """
    lens = get_for_org(models.Lens, info, id=derived_from.lens)
    source_system = getattr(lens, "coordinate_system", None)
    if source_system is None:
        raise ValueError(f"Lens {lens.pk} has no coordinate system, so there is no space to derive from")

    kind = derived_from.kind.value
    if kind not in _DERIVATION_PARAMS_BY_KIND:
        raise ValueError(f"A derivation cannot be a {kind}. Use IDENTITY for an in-place operation, TRANSLATION for a crop, SCALE for a resample, or BY_DIMENSION for a projection that drops an axis.")

    params: dict = {}
    field = _DERIVATION_PARAMS_BY_KIND[kind]
    if field is not None:
        value = getattr(derived_from, field)
        if value is None:
            raise ValueError(f"A {kind} derivation requires `{field}`")
        params[field] = value

    # The same rank check every other edge gets. It is what stops an IDENTITY derivation
    # from a lens whose axes differ -- a projection wearing an identity's clothes.
    graph_logic.assert_edge_rank(
        kind=kind,
        params=params,
        input_axes=derived_from.input_axes,
        output_axes=derived_from.output_axes,
        input_system=intrinsic,
        output_system=source_system,
    )

    return models.Transformation.objects.create(
        kind=kind,
        name=f"{dataset.name} <- {lens.dataset.name}",
        input=intrinsic,
        output=source_system,
        input_axes=derived_from.input_axes,
        output_axes=derived_from.output_axes,
        params=params,
        creator=ctx.user,
        organization=ctx.organization,
    )


def _parse_ome_metadata(metadata_string: str | None) -> dict:
    """Parse the OME metadata a client sent, and say so when it is not what it claims to be.

    `OmeMetadata.metadata` is a JSONField, so `metadata_string` must be a JSON *object*. It is
    an easy field to get wrong -- OME metadata is classically XML, and an empty upload is a
    string of whitespace -- and a bare `json.loads` reports every one of those the same way:
    "Expecting value: line 1 column 1 (char 0)", with no hint that it was talking about this
    field rather than, say, the zarr metadata read a few lines earlier.
    """
    if metadata_string is None or metadata_string.strip() == "":
        return {}

    try:
        metadata = json.loads(metadata_string)
    except json.JSONDecodeError as exc:
        head = metadata_string.strip()[:80]
        hint = " It looks like XML; OME-XML must be converted to JSON before it is sent." if head.startswith("<") else ""
        raise ValueError(f"anchor.omeMetadata.metadataString is not valid JSON ({exc}).{hint} It starts: {head!r}") from exc

    if not isinstance(metadata, dict):
        raise ValueError(f"anchor.omeMetadata.metadataString must be a JSON object, not a {type(metadata).__name__}.")

    return metadata


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

    if model.derived_from:
        _write_derivation_edge(info, dataset=dataset, intrinsic=intrinsic, derived_from=model.derived_from, ctx=ctx)

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
                metadata=_parse_ome_metadata(anchor.ome_metadata.metadata_string),
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
# on (anchor, dim, harmonic).
#
# They are attached post-ingest far more often than at ingest: a distribution
# means reading the cube, and a calibration means measuring a reference dye.
# Until now there was no way to attach any metadata to a dataset after ingest at
# all -- anchors were only ever created inside create_adataset.
# ---------------------------------------------------------------------------


def _assert_phasor_axis(dim: str, axis_specs: list[coords_logic.AxisSpec]) -> None:
    """Check the dim a phasor was taken over is an axis a DFT means something over.

    The same rule the render node enforces (`core.mutations.layer.assert_phasor_dim`), applied
    at the metadata boundary too: a density stored against the `z` axis is not a phasor, and
    nothing downstream could tell it from one.
    """
    axis = next((spec for spec in axis_specs if spec.name == dim), None)
    if axis is None:
        raise ValueError(f"dim '{dim}' is not a dimension of this dataset ({[spec.name for spec in axis_specs]})")
    if not coords_logic.is_phasor_axis(axis.type):
        raise ValueError(f"dim '{dim}' is a {axis.type} axis, not a MICROTIME or SPECTRUM axis. A phasor is only defined over a continuously sampled axis -- an arrival-time histogram or a spectrum.")


def _write_phasor_histogram(anchor: "models.CoordinateAnchor", input: PhasorHistogramInputModel, axis_specs: list[coords_logic.AxisSpec]) -> "models.PhasorHistogram":
    """Create or replace the phasor distribution at (anchor, dim, harmonic)."""
    _assert_phasor_axis(input.dim, axis_specs)

    bins = input.bins if input.bins is not None else 256
    if len(input.counts) != bins * bins:
        raise ValueError(f"counts has {len(input.counts)} entries but bins is {bins}, which needs {bins * bins}. It is the flattened bins x bins density grid, row-major with s outermost.")

    histogram, _ = models.PhasorHistogram.objects.update_or_create(
        anchor=anchor,
        dim=input.dim,
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
    """Create or replace the instrument-response correction at (anchor, dim, harmonic)."""
    _assert_phasor_axis(input.dim, axis_specs)

    calibration, _ = models.PhasorCalibration.objects.update_or_create(
        anchor=anchor,
        dim=input.dim,
        harmonic=input.harmonic if input.harmonic is not None else 1,
        defaults={
            "phase_offset": input.phase_offset,
            "modulation_factor": input.modulation_factor,
            "reference": input.reference,
        },
    )
    return calibration


def _get_or_create_anchor(dataset: "models.ADataset", dim_anchors: list[DimAnchorInputModel] | None) -> "models.CoordinateAnchor":
    """The anchor at these coordinates on this dataset, creating it if it is new.

    Get-or-create rather than create: a phasor distribution and an intensity histogram at the
    same coordinate are two spokes of *one* anchor, and a second anchor at the same coordinates
    would split the metadata of one pixel across two hubs.
    """
    coordinates = {anchor.dim: anchor.value for anchor in dim_anchors or []}
    anchor, _ = models.CoordinateAnchor.objects.get_or_create(dataset=dataset, coordinates=coordinates)
    return anchor


class CreatePhasorHistogramInputModel(PhasorHistogramInputModel):
    dataset: str = Field(description="The ID of the dataset the phasor was computed from")
    dim_anchors: list[DimAnchorInputModel] | None = Field(None, description="The coordinates the distribution is pinned to")


@kante.pydantic_input(CreatePhasorHistogramInputModel, description="Attach a phasor distribution to a dataset: the 2D (g, s) density of a phasor taken over one axis at one harmonic. Computed after ingest by a task that reads the cube; recomputing at the same harmonic replaces it, while a second harmonic lands beside the first")
class CreatePhasorHistogramInput:
    dataset: strawberry.ID = strawberry.field(description="The ID of the dataset the phasor was computed from")
    dim: str = strawberry.field(description="The axis the phasor was taken over, e.g. 'tau'. Must be a MICROTIME or SPECTRUM axis of the dataset")
    counts: list[float] = strawberry.field(description="The flattened bins x bins (g, s) density, row-major with s outermost")
    dim_anchors: list[DimAnchorInput] | None = strawberry.field(default=None, description="The coordinates the distribution is pinned to, e.g. [{'dim': 'c', 'value': 0}] for one detection channel. Omit for a distribution global over the dataset")
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
    anchor = _get_or_create_anchor(dataset, model.dim_anchors)
    return _write_phasor_histogram(anchor, model, dataset.axis_specs)


class CreatePhasorCalibrationInputModel(PhasorCalibrationInputModel):
    dataset: str = Field(description="The ID of the dataset the correction applies to")
    dim_anchors: list[DimAnchorInputModel] | None = Field(None, description="The coordinates the correction is pinned to")


@kante.pydantic_input(CreatePhasorCalibrationInputModel, description="Attach an instrument-response correction to a dataset, taking a raw phasor to a calibrated one. Measured once per detector from a reference acquisition. Its absence is legitimate: an uncalibrated phasor still renders, its hue is just not traceable to an absolute lifetime")
class CreatePhasorCalibrationInput:
    dataset: strawberry.ID = strawberry.field(description="The ID of the dataset the correction applies to")
    dim: str = strawberry.field(description="The axis the correction applies to, e.g. 'tau'. Must be a MICROTIME or SPECTRUM axis of the dataset")
    dim_anchors: list[DimAnchorInput] | None = strawberry.field(default=None, description="The coordinates the correction is pinned to, e.g. [{'dim': 'c', 'value': 0}] -- the IRF differs per detector. Omit for a correction global over the dataset")
    harmonic: int | None = strawberry.field(default=None, description="The harmonic the correction applies at (default 1)")
    phase_offset: float | None = strawberry.field(default=None, description="The phase correction in radians, added to each pixel's phase")
    modulation_factor: float | None = strawberry.field(default=None, description="The modulation correction, multiplied into each pixel's modulus")
    reference: str | None = strawberry.field(default=None, description="What the correction was measured against, e.g. 'Rhodamine 6G, 4.1 ns'")


def create_phasor_calibration(info: Info, input: CreatePhasorCalibrationInput) -> types.PhasorCalibration:
    """Attach an instrument-response correction to a dataset."""
    model = input.to_pydantic()

    dataset = get_for_org(models.ADataset, info, id=model.dataset)
    anchor = _get_or_create_anchor(dataset, model.dim_anchors)
    return _write_phasor_calibration(anchor, model, dataset.axis_specs)


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
