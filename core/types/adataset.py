import datetime

import strawberry
from strawberry import auto
from typing import Annotated, List
from core import models, scalars, filters, enums
from kante.types import Info
from lightpath.objects.types import LightpathGraph
from lightpath.objects.models import LightpathGraphModel
from core.render.layer.types import LayerRenderGraph
from core.render.layer.models import LayerRenderGraphModel
from core.types.mesh import Mesh
from core.types.coords import CoordinateSystem, MeshCollection, PlacementStep, Transformation
import kante
from datalayer.types import ZarrStore

from kanne_server import scalars as kanne_scalars

from core import order, base_models
from core.logic import coords as coords_logic
from core.logic import graph as graph_logic
from core.logic import phasor as phasor_logic
from core.logic import scene_graph

from core.types.auth import ProvenanceEntry, Task, User


@kante.django_type(
    models.ADataset,
    filters=filters.ADatasetFilter,
    ordering=order.ADatasetOrder,
    pagination=True,
    description="A multi-dimensional array dataset. Its dimensions and their types live on the axes of its INTRINSIC (pixel grid) coordinate system; physical units live on its calibrations; its pyramid levels are DataArrays, each mapping into the one intrinsic system",
)
class ADataset:
    """A multi-dimensional array dataset with named dimensions, described by its intrinsic pixel-grid coordinate system."""

    id: auto
    name: auto
    description: str | None
    created_through: Task | None = kante.django_field(description="The task this dataset was created through, if any")
    created_through_by: User | None = kante.django_field(description="The assigner of the creating task, if any")
    data_arrays: List["DataArray"] = kante.django_field(description="The multiscale data arrays belonging to this dataset")
    calibrations: List[CoordinateSystem] = kante.django_field(
        description="The dataset's calibrated PHYSICAL spaces (pixel size, stage pose, ...). Each is reached from the intrinsic system by a single transformation edge; refining a calibration bumps that edge's version and moves nothing drawn in pixels"
    )

    @kante.django_field(description="The dataset's INTRINSIC coordinate system: its level-0 pixel grid, the space every pyramid level and lens maps into and the space ROIs resolve against. Structural and calibration-independent")
    def intrinsic_system(self, info: Info) -> CoordinateSystem | None:
        """The dataset's INTRINSIC coordinate system."""
        return self.intrinsic_coordinate_system

    @kante.django_field(
        description="The edges from this dataset's pixel grid back into the lenses it was computed from, when it is a derived dataset: one for a deconvolution or a resample, several for a fusion of channels or tiles. Empty for a dataset that was acquired rather than derived. The order is the priority its creator declared: the first edge is the primary parent, the one that places the dataset. They are edges, not labels: each carries the map itself, so a client can compose it -- and they are why a derived dataset inherits its sources' placements instead of needing its own registration"
    )
    def derived_from(self, info: Info) -> List[Transformation]:
        """The stored derivation edges, primary parent first, if this dataset was computed from others."""
        return graph_logic.derivation_edges(self)

    @kante.django_field(description="Whether this dataset carries a resolution pyramid. Derived: true when it has more than one level")
    def multiscale(self, info: Info) -> bool:
        """Whether the dataset has more than one pyramid level."""
        return self.multiscale

    @kante.django_field(description="The dataset's axis names, in array order. Derived from the axes of its intrinsic coordinate system")
    def axis_names(self, info: Info) -> List[str]:
        """The dataset's axis names."""
        return self.axis_names

    @kante.django_field(description="The dataset's shape: that of its level-0 array")
    def shape(self, info: Info) -> List[int]:
        """The dataset's shape."""
        return self.shape_list

    @kante.django_field(
        description="The scenes this dataset is rendered in, reached through its lenses' layers. Derived, never stored: a scene is a composition and this is a fact of the graph, so there is no dataset-to-scene column that could disagree with it. The scene createADataset's bootstrapScene creates is found here"
    )
    def scenes(self, info: Info) -> List["Scene"]:
        """The scenes this dataset is rendered in, through its lenses' layers."""
        return list(models.Scene.objects.filter(layers__lens__dataset=self).distinct())


@kante.django_type(
    models.DataArray,
    filters=filters.DataArrayFilter,
    ordering=order.DataArrayOrder,
    pagination=True,
    description="One level of a dataset's resolution pyramid: a zarr-backed array, with its own voxel-index coordinate system and a stored edge into the dataset's intrinsic space",
)
class DataArray:
    """One level of a dataset's resolution pyramid, with the edge that places it in the dataset's intrinsic space."""

    id: auto
    store: ZarrStore
    shape: list[int]
    chunk_shape: list[int]
    level: int
    @kante.django_field(
        select_related=["coordinate_system", "dataset__intrinsic_system"],
        description="The coordinate system this level's voxels live in. Level 0 owns none: the dataset's INTRINSIC system IS the level-0 pixel grid, so this resolves to it. Higher levels own an ARRAY (voxel index) system",
    )
    def coordinate_system(self, info: Info) -> CoordinateSystem | None:
        """The system this level's voxels live in: its own ARRAY system, or intrinsic for level 0."""
        return self.space

    @kante.django_field(
        description="The edge from this level's voxel space into the dataset's intrinsic space. Its scale is absolute -- derived from the actual shapes, not from a nominal 2**level -- so a pyramid whose axes do not halve cleanly is described correctly. Null for level 0: its space IS the intrinsic space, and there is nothing to map",
    )
    def to_parent(self, info: Info) -> Transformation | None:
        """The stored level-to-intrinsic edge."""
        return self.to_parent


@kante.django_type(
    models.OptikitState,
    filters=filters.OptikitStateFilter,
    pagination=True,
    description="The hardware truth: the recorded microscope (Optikit) state pinned to a coordinate anchor",
)
class OptikitState:
    """The hardware truth: the recorded microscope (Optikit) state pinned to a coordinate anchor"""

    id: auto

    @kante.django_field(description="The recorded microscope state")
    def state(self, info: Info) -> scalars.Any:
        """The recorded microscope state."""
        return self.state


@kante.django_type(
    models.ValueHistogram,
    filters=filters.ValueHistogramFilter,
    pagination=True,
    description="The distribution of pixel values pinned to a coordinate anchor, including histogram bins, min/max and percentile limits",
)
class ValueHistogram:
    """The distribution of pixel values pinned to a coordinate anchor, including histogram bins, min/max and percentile limits"""

    id: auto
    p1: float | None
    p99: float | None
    histogram: list[float]
    bins: list[float]
    min: float | None
    max: float | None


@kante.django_type(
    models.LightPath,
    filters=filters.LightPathFilter,
    pagination=True,
    description="The light path truth: the optical light path graph pinned to a coordinate anchor",
)
class LightPath:
    """The light path truth: the optical light path graph pinned to a coordinate anchor"""

    id: auto

    @kante.django_field()
    def graph(self, info: Info) -> LightpathGraph:
        return LightpathGraphModel(**self.graph)


@kante.django_type(
    models.ChannelLabel,
    filters=filters.ChannelLabelFilter,
    pagination=True,
    description="The channel truth: a human-readable label for a channel, pinned to a coordinate anchor",
)
class ChannelLabel:
    """The channel truth: a human-readable label for a channel, pinned to a coordinate anchor"""

    id: auto
    label: str


@kante.django_type(
    models.PhasorHistogram,
    pagination=True,
    description="The distribution of a phasor pinned to a coordinate anchor: a 2D (g, s) density plus the summed profile it was computed from. What ValueHistogram is to an intensity channel -- it lets a client pick a sane value range for a phasor overlay without reading the cube",
)
class PhasorHistogram:
    """The distribution of a phasor pinned to a coordinate anchor."""

    id: auto
    axis: str
    harmonic: int
    bins: int
    g_min: float
    g_max: float
    s_min: float
    s_max: float
    total: int | None
    calibrated: bool

    @kante.django_field(description="The flattened bins x bins (g, s) density, row-major with s outermost")
    def counts(self, info: Info) -> list[float]:
        return self.counts

    @kante.django_field(description="The summed profile along the phasor axis (a decay for a MICROTIME axis, a spectrum for a SPECTRUM one), one value per bin")
    def profile(self, info: Info) -> list[float]:
        return self.profile


@kante.django_type(
    models.PhasorCalibration,
    pagination=True,
    description="The instrument-response correction taking a raw phasor to a calibrated one, pinned to a coordinate anchor. An acquisition fact, not a display choice: two layers over one dataset cannot coherently disagree about it. Its absence means the phasor is uncalibrated, which still renders",
)
class PhasorCalibration:
    """The instrument-response correction taking a raw phasor to a calibrated one."""

    id: auto
    axis: str
    harmonic: int
    phase_offset: float | None
    modulation_factor: float | None
    reference: str | None


@kante.django_type(
    models.CoordinateAnchor,
    filters=filters.CoordinateAnchorFilter,
    pagination=True,
    description="The axis-agnostic hub that pins metadata spokes (microscope state, OME metadata, value histograms, channel labels, light paths, phasor distributions and calibrations) to specific coordinates of a dataset",
)
class CoordinateAnchor:
    """The axis-agnostic hub that pins metadata spokes (microscope state, OME metadata, value histograms, channel labels, light paths, phasor distributions and calibrations) to specific coordinates of a dataset"""

    id: auto
    # The reverse accessor from OptikitState.anchor is `microscope`, not `optikit_state`.
    microscope: OptikitState | None = kante.django_field(description="The microscope state recorded at this coordinate")
    value_histogram: ValueHistogram | None
    channel_label: ChannelLabel | None
    light_graph: LightPath | None
    # Lists, not single spokes: one anchor may carry a phasor at several harmonics, and over
    # several axes -- neither of which the anchor's coordinates can pin.
    phasor_histograms: list[PhasorHistogram]
    phasor_calibrations: list[PhasorCalibration]

    @kante.django_field(
        description="The coordinates this anchor is pinned to, e.g. {'c': 0, 't': 5}. Level-0 pixel indices, i.e. coordinates of the dataset's INTRINSIC system. An anchor that omits an axis is global along it"
    )
    def coordinates(self, info: Info) -> scalars.Any:
        """The coordinates this anchor is pinned to."""
        return self.coordinates


@kante.django_type(
    models.OmeMetadata,
    filters=filters.OmeMetadataFilter,
    pagination=True,
    description="The image truth: OME image metadata pinned to a coordinate anchor",
)
class OmeMetadata:
    """The image truth: OME image metadata pinned to a coordinate anchor"""

    id: auto

    @kante.django_field(description="The OME image metadata")
    def metadata(self, info: Info) -> scalars.Any:
        """The OME image metadata."""
        return self.metadata


@kante.django_type(
    models.OmePlaneMetadata,
    filters=filters.OmePlaneMetadataFilter,
    pagination=True,
    description="The plane truth: OME plane metadata pinned to a coordinate anchor",
)
class OmePlaneMetaData:
    """The plane truth: OME plane metadata pinned to a coordinate anchor"""

    id: auto

    @kante.django_field(description="The OME plane metadata")
    def plane_metadata(self, info: Info) -> scalars.Any:
        """The OME plane metadata."""
        return self.plane_metadata


@kante.django_type(
    models.Scene,
    filters=filters.SceneFilter,
    pagination=True,
    ordering=order.SceneOrder,
    description="A composition of layers over a shared WORLD coordinate system. The scene carries no units of its own -- they are per-axis, on the axes of its world system",
)
class Scene:
    """A composition of layers over a shared WORLD coordinate system."""

    id: auto
    name: auto
    layers: List["Layer"] = kante.django_field(
        filters=filters.LayerFilter,
        ordering=order.LayerOrder,
        pagination=True,
        description="The layers placed in this scene (a heterogeneous list of layer kinds)",
    )
    world_coordinate_system: CoordinateSystem | None = kante.django_field(description="The scene's shared WORLD coordinate system, into which each of its layers is registered")
    registrations: List[Transformation] = kante.django_field(
        field_name="coordinate_transformations",
        description="The registration edges belonging to this scene's composition -- mostly the edges placing each layer's dataset into the world system. This membership set is what `layers.pathToWorld` searches; composing the matrices stays the client's job. Removing one does not undo it: the edge remains a fact about two coordinate systems",
    )

    @kante.django_field(description="Every coordinate system reachable in this scene: its world system plus those its transformation edges touch")
    def coordinate_systems(self, info: Info) -> List[CoordinateSystem]:
        """The coordinate systems reachable from this scene's edges."""
        return scene_graph.for_request(info, self).reachable_systems()

    @kante.django_field(description="The ROIs drawn in a coordinate system this scene can reach. Reachability, not containment: an ROI belongs to a coordinate system, and survives the scene's deletion")
    def rois(self, info: Info) -> List["DataRoi"]:
        """The ROIs whose coordinate system is reachable in this scene's graph."""
        # The same closure `coordinateSystems` walks: asking a scene for both used to walk
        # it twice. Reachability is a property of the scene, not of the field asking.
        return models.DataRoi.objects.filter(coordinate_system__in=scene_graph.for_request(info, self).reachable_system_ids())


@kante.pydantic_type(base_models.SliceModel, description="A slice along a named axis, with optional start, stop and step")
class Slice:
    """A slice along a named axis, with optional start, stop and step"""

    axis: str
    start: int | None
    stop: int | None
    step: int | None


@kante.django_type(
    models.Lens,
    filters=filters.LensFilter,
    ordering=order.LensOrder,
    pagination=True,
    description="A Lens is a way of looking at a dataset: a dimensional selection (slices) over a dataset that defines a view of its data",
)
class Lens:
    """A selection over a dataset. Its shape and axes are derived from the dataset and the slices."""

    id: auto
    dataset: ADataset

    @kante.django_field(
        select_related=["coordinate_system", "dataset__intrinsic_system"],
        description="The coordinate system the lens' selection is expressed in. A sliced lens owns one (the space its slices cut out, with the derived edge recording the shift); an unsliced lens selects everything, so this resolves to the dataset's INTRINSIC system",
    )
    def coordinate_system(self, info: Info) -> CoordinateSystem | None:
        """The system the lens' selection is expressed in: its own, or intrinsic when unsliced."""
        return self.space

    @kante.django_field(description="The lens' axis names, in array order. A selection never drops or reorders an axis")
    def axis_names(self, info: Info) -> List[str]:
        """The lens' axis names."""
        return self.axis_names

    @kante.django_field(description="The shape this lens' slices cut out of its dataset")
    def shape(self, info: Info) -> List[int]:
        """The lens' shape."""
        return self.shape_list

    @kante.django_field(
        description="The edge from this lens' space back into its dataset's intrinsic pixel space. A crop is a translation of the slice starts; a stepped lens also rescales. Without this edge an ROI drawn on a cropped lens has no defined path back to its dataset. Null for an unsliced lens: its space IS the intrinsic space, and there is no shift to record",
    )
    def to_parent(self, info: Info) -> Transformation | None:
        """The stored lens-to-parent edge."""
        return self.to_parent

    @kante.django_field(description="Which axis of the data source maps to screen x, y, z, time and intensity. Derived from the axis types: spatial axes are in array order, so the last is x")
    def render_axes(self, info: Info) -> "RenderAxes":
        """The renderer's axis mapping, derived from the axis types."""
        return coords_logic.resolve_render_axes(self.axis_specs)

    @kante.django_field()
    def slices(self, info: Info) -> List[Slice]:
        return self.slices_list

    @kante.django_field()
    def active_anchors(self, info: Info) -> List[CoordinateAnchor]:
        return self.active_anchors

    @kante.django_field(
        description="Everything needed to reduce one axis of this lens to a phasor: the bin count and width, the period the transform runs over, the laser rate, the instrument-response correction and the persisted distribution. Null when the lens has no MICROTIME or SPECTRUM axis. Derived -- none of it is stored on the lens, and a phasor render node references it rather than copying it, so two layers over one dataset cannot disagree about the instrument"
    )
    def phasor(self, info: Info, axis: str | None = None, harmonic: int = 1) -> "PhasorContext | None":
        """The phasor context of one axis of this lens, at one harmonic."""
        return resolve_phasor_context(self, axis_name=axis, harmonic=harmonic)


@kante.type(description="Which axis of a data source maps to screen x, y, z, time and intensity. Derived from the axis types, never stored")
class RenderAxes:
    """Which axis of a data source maps to screen x, y, z, time and intensity."""

    x: str = strawberry.field(description="The axis mapped to screen x: the last (fastest-varying) spatial axis")
    y: str = strawberry.field(description="The axis mapped to screen y: the second-to-last spatial axis")
    z: str | None = strawberry.field(description="The axis mapped to screen z: the third-to-last spatial axis, if the data is volumetric")
    t: str | None = strawberry.field(description="The time axis, if the data has one")
    intensity: str | None = strawberry.field(description="The channel axis, if the data has one")
    phasor: str | None = strawberry.field(description="The axis a phasor may be taken over -- a MICROTIME (FLIM arrival time) or SPECTRUM (wavelength) axis -- if the data has one")


@kante.type(
    description="Everything needed to reduce one axis of a lens to a phasor, at one harmonic. Derived from the dataset's calibration, its lightpath and its phasor spokes; nothing here is stored on the lens. A phasor render node states *which* axis and harmonic to reduce, and reads the rest from here -- the instrument is an acquisition fact, so two layers over one dataset cannot disagree about it"
)
class PhasorContext:
    """Everything needed to reduce one axis of a lens to a phasor, at one harmonic."""

    axis: str = strawberry.field(description="The axis the phasor is taken over")
    axis_type: enums.AxisType = strawberry.field(description="What that axis samples: MICROTIME (so the phase reads as a fluorescence lifetime) or SPECTRUM (so it reads as a spectral centre of mass)")
    bins: int = strawberry.field(description="The number of bins along that axis on this lens: the N of the transform")
    harmonic: int = strawberry.field(description="The harmonic this context was resolved for. It selects the calibration and the distribution below, which are both harmonic-specific")
    bin_width: kanne_scalars.GenericQuantity | None = strawberry.field(
        description="The physical width of one bin, from the axis' PHYSICAL calibration: a duration ('0.098 ns') for a microtime axis, a wavelength step ('5 nm') for a spectrum axis. Null when the dataset has no calibration -- the phasor is then computable only in bin units"
    )
    window: kanne_scalars.GenericQuantity | None = strawberry.field(
        description="The period the transform actually runs over on THIS lens: bin_width x bins. It is the frequency to transform at, and the only one available over a spectrum axis. For an uncropped FLIM axis it should agree with laserFrequency -- but a lens that slices its phasor axis narrows it, and then it deliberately does not: the window follows the data, while the laser does not. Null when there is no calibration"
    )
    laser_frequency: kanne_scalars.Frequency | None = strawberry.field(
        description="The repetition rate of the pulsed source, read from the lightpath graph anchored to this data: the clock a FLIM phasor runs on, and what makes a phase an absolute lifetime. Prefer it over `window` for a lifetime, and note the two diverge on a lens that crops its microtime axis. Null for a spectrum axis, or when no lightpath states a rate"
    )
    calibration: "PhasorCalibration | None" = strawberry.field(
        description="The instrument-response correction at this axis and harmonic. Null means the phasor is uncalibrated -- which still renders, its hue is just not traceable to an absolute lifetime"
    )
    phasor_histogram: "PhasorHistogram | None" = strawberry.field(description="The persisted (g, s) density at this axis and harmonic, so a client can range the overlay's colormap without reading the cube. Null until a task has computed one")


def resolve_phasor_context(lens: "models.Lens", axis_name: str | None, harmonic: int) -> "PhasorContext | None":
    """Assemble the phasor context of one axis of a lens.

    The three acquisition facts a phasor needs live in three different places -- the bin width
    in a calibration edge, the laser rate in a lightpath spoke, the correction in a calibration
    spoke -- and none of them is a property of the lens. Gathering them is this function's whole
    job; a client gets them in the same query as the render node, without a second round trip
    and without a copy on the node that could drift from the instrument.
    """
    axis_specs = lens.axis_specs

    if axis_name:
        axis = next((spec for spec in axis_specs if spec.name == axis_name), None)
        if axis is None or not coords_logic.is_phasor_axis(axis.type):
            return None
    else:
        axis = phasor_logic.phasor_axis(axis_specs)
        if axis is None:
            return None

    dataset = lens.dataset
    axis_index = [spec.name for spec in axis_specs].index(axis.name)

    bin_width = _resolve_bin_width(dataset, axis_index, len(axis_specs))
    bins = lens.get_size_of_axis(axis.name)

    return PhasorContext(
        axis=axis.name,
        axis_type=enums.AxisType(axis.type),
        bins=bins,
        harmonic=harmonic,
        bin_width=bin_width,
        # The *lens'* bin count, not the dataset's: a lens that slices the axis narrows the
        # window the transform runs over, and saying otherwise would claim a period the data
        # does not cover.
        window=_scaled_quantity(bin_width, bins),
        laser_frequency=_resolve_laser_frequency(dataset),
        calibration=dataset.phasor_calibrations_at(axis.name, harmonic),
        phasor_histogram=dataset.phasor_histogram_at(axis.name, harmonic),
    )


def _resolve_bin_width(dataset: "models.ADataset", axis_index: int, axis_count: int) -> str | None:
    """The physical width of one bin along an axis, from the dataset's first calibration that scales it."""
    intrinsic = dataset.intrinsic_coordinate_system
    if intrinsic is None:
        return None

    for system in dataset.calibrations.all():
        edge = models.Transformation.objects.filter(input=intrinsic, output=system).first()
        if edge is None:
            continue

        children = [(child.kind, child.params) for child in edge.children.order_by("order")]
        scale = phasor_logic.axis_scale(phasor_logic.flatten_edge(edge.kind, edge.params, children), axis_index, axis_count)
        if scale is None:
            continue

        unit = next((axis.unit for axis in system.axes.all() if axis.order == axis_index), None)
        if unit:
            return phasor_logic.quantity(scale, unit)

    return None


def _scaled_quantity(quantity: str | None, factor: int) -> str | None:
    """Multiply a "magnitude unit" string by a factor, keeping the unit."""
    if quantity is None:
        return None
    magnitude, _, unit = quantity.partition(" ")
    return phasor_logic.quantity(float(magnitude) * factor, unit)


def _resolve_laser_frequency(dataset: "models.ADataset") -> int | None:
    """The pulsed source's repetition rate, from any lightpath anchored to this dataset."""
    for light_path in models.LightPath.objects.filter(anchor__dataset=dataset):
        frequency = phasor_logic.laser_frequency(light_path.graph or {})
        if frequency is not None:
            return frequency
    return None


@kante.django_interface(
    models.Layer,
    description="A layer placed in a scene and alpha-blended over the layers below it. It carries view state only: registration is a scene-level transformation edge, not a property of the view. The concrete kind (ImageLayer, ShapeLayer, PointLayer, TrackLayer, MeshLayer) carries its own data source and render settings.",
)
class Layer:
    """A layer placed in a scene, carrying the shared placement and compositing settings. No spatial fields."""

    id: auto
    kind: enums.LayerKind
    scene: Scene
    blending: enums.Blending
    opacity: float
    visible: bool
    order: int

    @classmethod
    def get_queryset(cls, queryset, info, **kwargs):
        """Select the relations the placement logic reads in Python.

        The optimizer prefetches what the *selection set* names, and a client asking for
        `pathToWorld` names none of these -- but the resolver walks all of them. Without
        this, every layer costs a handful of round trips for relations the row could have
        carried along.
        """
        return queryset.select_related(*scene_graph.LAYER_PLACEMENT_RELATIONS)

    @kante.django_field(
        description="The path of transformation edges from this layer's source coordinate system to its scene's WORLD system. A layer belongs to exactly one scene, so this is the one 'to world' question with a single right answer -- the path uses the layer's dataset facts plus this scene's membership edges, never another scene's registration. Null when the layer is unregistered or has no source system; empty when the source already is the world system. The server returns the edges; composing them (inverting flagged steps) stays the client's job",
    )
    def path_to_world(self, info: Info) -> List[PlacementStep] | None:
        """The layer's placement path, as (edge, inverted) steps."""
        steps = scene_graph.for_request(info, self.scene).placement_path(self)
        if steps is None:
            return None
        return [PlacementStep(transformation=edge, inverted=inverted) for edge, inverted in steps]

    @kante.django_field(
        description="Whether this layer has a place in its scene's world, and if not, why not. A null `pathToWorld` means two different things -- nobody has registered this data yet, or its geometry did not survive the operation that produced it and it can never be placed -- and a client should not have to guess which. UNREGISTERED is a gap to close; UNMAPPABLE is a fact to badge. Derived, never stored",
    )
    def placement(self, info: Info) -> enums.PlacementState:
        """PLACED, UNREGISTERED or UNMAPPABLE."""
        return enums.PlacementState(scene_graph.for_request(info, self.scene).placement_state(self))

    @kante.django_field(
        description="How much this layer's placement is actually known: the weakest edge on its path to world. UNKNOWN while the placement rests on an assumed registration (or none); MANUAL once someone authored the registration; VALIDATED once it was checked. Derived, never stored -- and distinct from a single edge's `validity`: this is the minimum over the whole path",
    )
    def placement_validity(self, info: Info) -> enums.PlacementValidity:
        """The weakest validity on the layer's placement path."""
        return enums.PlacementValidity(scene_graph.for_request(info, self.scene).placement_validity(self))


@kante.django_type(
    models.Layer,
    filters=filters.LayerFilter,
    ordering=order.LayerOrder,
    pagination=True,
    description="A layer that renders array (lens) data as an alpha-blended image. Its rendering is described entirely by the composable render graph; its placement, entirely by the coordinate graph.",
)
class ImageLayer(Layer):
    """A layer that renders array (lens) data. All rendering lives in the render graph; all placement lives in the coordinate graph."""

    id: auto
    lens: Lens

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        return obj.kind == enums.LayerKind.IMAGE.value

    @kante.django_field(description="The composable in-layer render graph, if this layer defines one")
    def render_graph(self, info: Info) -> LayerRenderGraph | None:
        if not self.render_graph:
            return None
        return LayerRenderGraphModel(**self.render_graph)

    @kante.django_field(
        description="Per pyramid level, the path from that level's voxel grid to this scene's WORLD system. What a multiscale renderer consumes directly: pick a level by zoom and use its path -- every level stars into the same intrinsic system, so the registration tail is shared. A level's path is null when the dataset is not registered into the scene",
    )
    def level_paths(self, info: Info) -> List["LevelPlacement"]:
        """One placement per pyramid level, each anchored at that level's ARRAY system."""
        return [
            LevelPlacement(
                data_array=array,
                path=None if steps is None else [PlacementStep(transformation=edge, inverted=inverted) for edge, inverted in steps],
            )
            for array, steps in scene_graph.for_request(info, self.scene).level_placements(self)
        ]


@kante.type(description="The placement of one pyramid level in a layer's scene: the level and its path to the WORLD system")
class LevelPlacement:
    """The placement of one pyramid level in a layer's scene."""

    data_array: "DataArray" = strawberry.field(description="The pyramid level being placed")
    path: List[PlacementStep] | None = strawberry.field(description="The path from this level's voxel grid to the scene's WORLD system, or null when the dataset is not registered into the scene")


@kante.type(description="A discrete coordinate an ROI is pinned to, e.g. a timepoint or a channel")
class RoiSelector:
    """A discrete coordinate an ROI is pinned to, e.g. a timepoint or a channel."""

    axis: str = strawberry.field(description="The name of the discrete axis, e.g. 't' or 'c'")
    index: int = strawberry.field(description="The coordinate along that axis")


@kante.type(description="An axis-aligned bounding box, as a min and a max corner")
class BoundingBox:
    """An axis-aligned bounding box, as a min and a max corner."""

    min: list[float] = strawberry.field(description="The lower corner, in the axis order of the coordinate system")
    max: list[float] = strawberry.field(description="The upper corner, in the axis order of the coordinate system")


@kante.django_type(
    models.DataRoi,
    filters=filters.DataRoiFilter,
    ordering=order.DataRoiOrder,
    pagination=True,
    description="A region of interest drawn in a coordinate system. It belongs to that system, not to a scene: delete the scene and the ROI survives",
)
class DataRoi:
    """A region of interest drawn in a coordinate system, described by its vectors and the discrete coordinates it is pinned to."""

    id: auto
    coordinate_system: CoordinateSystem
    name: auto
    description: str | None
    kind: enums.RoiKind
    vectors: list[list[float]]
    created_with_transforms: int
    provenance_entries: List["ProvenanceEntry"] = kante.django_field(description="Provenance entries for this data ROI")

    @kante.django_field(description="The discrete coordinates this ROI is pinned to. An axis the ROI does not pin is one it spans")
    def selectors(self, info: Info) -> list[RoiSelector]:
        """The ROI's discrete pins, unpacked from the stored axis-name-keyed dict."""
        return [RoiSelector(axis=axis, index=index) for axis, index in (self.selectors or {}).items()]

    @kante.django_field(
        description="The ROI's bounding box in its dataset's intrinsic space, derived from every corner of its geometry (an affine-transformed box is not a box: min/max alone gives a strictly too-small answer under rotation or shear). Intrinsic, not world: world is scene-owned, and one dataset can sit in two scenes under two registrations"
    )
    def intrinsic_bbox(self, info: Info) -> BoundingBox | None:
        """The ROI's bounding box in its dataset's intrinsic space."""
        if not self.intrinsic_bbox:
            return None
        return BoundingBox(min=self.intrinsic_bbox["min"], max=self.intrinsic_bbox["max"])


@kante.django_type(
    models.Layer,
    filters=filters.LayerFilter,
    ordering=order.LayerOrder,
    pagination=True,
    description="A layer that renders the vector geometry of a data ROI (polygons, boxes, ellipses, lines, paths), placed and styled in a scene.",
)
class ShapeLayer(Layer):
    """A layer that renders the vector geometry of a data ROI, placed and styled in a scene."""

    id: auto
    data_roi: DataRoi
    stroke_color: list[int] | None
    fill_color: list[int] | None
    stroke_width: float | None
    filled: bool

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        return obj.kind == enums.LayerKind.SHAPE.value


def _coordinate_column_named(layer: "models.Layer", axis_name: str) -> str | None:
    """The table dataset column whose axis is named `axis_name` (x/y/z/t), or None.

    Name-based, deliberately: placement matches coordinate axes to the world by name, so
    a layer's screen mapping must too -- deriving x from array *position* would silently
    swap the columns of a table that declared them (x, y, z) rather than (z, y, x).
    """
    dataset = layer.table_dataset
    for col in dataset.columns_by_role(enums.TableColumnRoleChoices.COORDINATE.value):
        if col.name == axis_name:
            return col.name
    return None


def _role_column(layer: "models.Layer", role: str) -> str | None:
    """The name of the table dataset's column of a given role, or None."""
    columns = layer.table_dataset.columns_by_role(role)
    return columns[0].name if columns else None


@kante.django_type(
    models.Layer,
    filters=filters.LayerFilter,
    ordering=order.LayerOrder,
    pagination=True,
    description="A layer that renders a point cloud (e.g. SMLM localisations, centroids) from a table dataset or a legacy table.",
)
class PointLayer(Layer):
    """A layer that renders a point cloud from table columns, placed and styled in a scene."""

    id: auto
    table: Annotated["Table", strawberry.lazy("core.types.image")] | None
    table_dataset: Annotated["TableDataset", strawberry.lazy("core.types.table_dataset")] | None = kante.django_field(
        description="The table dataset the points are drawn from, when the layer uses one. Its declared coordinate columns provide the coordinates and its own system provides the placement"
    )
    coordinate_system: CoordinateSystem | None = kante.django_field(
        description="(legacy table) The coordinate system the table's coordinate columns are expressed in. Null for a table dataset layer, whose space is the dataset's own system"
    )
    size_column: str | None
    color_column: str | None
    point_size: float | None
    colormap: enums.ColorMap | None

    @kante.django_field(description="The column mapped to the x coordinate. For a table dataset layer, the coordinate column whose axis is named 'x'")
    def x_column(self, info: Info) -> str | None:
        """The x-coordinate column."""
        return _coordinate_column_named(self, "x") if self.table_dataset_id else self.x_column

    @kante.django_field(description="The column mapped to the y coordinate")
    def y_column(self, info: Info) -> str | None:
        """The y-coordinate column."""
        return _coordinate_column_named(self, "y") if self.table_dataset_id else self.y_column

    @kante.django_field(description="The column mapped to the z coordinate, if any")
    def z_column(self, info: Info) -> str | None:
        """The z-coordinate column."""
        return _coordinate_column_named(self, "z") if self.table_dataset_id else self.z_column

    @kante.django_field(description="The column mapped to the time coordinate, if any")
    def t_column(self, info: Info) -> str | None:
        """The time-coordinate column."""
        return _coordinate_column_named(self, "t") if self.table_dataset_id else self.t_column

    @kante.django_field(description="The column identifying each point, if any")
    def id_column(self, info: Info) -> str | None:
        """The point-id column."""
        return _role_column(self, enums.TableColumnRoleChoices.ID.value) if self.table_dataset_id else self.id_column

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        return obj.kind == enums.LayerKind.POINT.value


@kante.django_type(
    models.Layer,
    filters=filters.LayerFilter,
    ordering=order.LayerOrder,
    pagination=True,
    description="A layer that renders trajectories (e.g. particle/cell tracks) from a table dataset or a legacy table, grouped by a track id.",
)
class TrackLayer(Layer):
    """A layer that renders trajectories from table columns, placed and styled in a scene."""

    id: auto
    table: Annotated["Table", strawberry.lazy("core.types.image")] | None
    table_dataset: Annotated["TableDataset", strawberry.lazy("core.types.table_dataset")] | None = kante.django_field(
        description="The table dataset the tracks are drawn from, when the layer uses one. Its coordinate and TRACK_ID columns provide the trajectories"
    )
    coordinate_system: CoordinateSystem | None = kante.django_field(
        description="(legacy table) The coordinate system the table's coordinate columns are expressed in. Null for a table dataset layer, whose space is the dataset's own system"
    )
    color_by_column: str | None
    line_width: float | None
    colormap: enums.ColorMap | None

    @kante.django_field(description="The column that groups rows into tracks. For a table dataset layer, its TRACK_ID column")
    def track_id_column(self, info: Info) -> str | None:
        """The track-id column."""
        return _role_column(self, enums.TableColumnRoleChoices.TRACK_ID.value) if self.table_dataset_id else self.track_id_column

    @kante.django_field(description="The column mapped to the x coordinate")
    def x_column(self, info: Info) -> str | None:
        """The x-coordinate column."""
        return _coordinate_column_named(self, "x") if self.table_dataset_id else self.x_column

    @kante.django_field(description="The column mapped to the y coordinate")
    def y_column(self, info: Info) -> str | None:
        """The y-coordinate column."""
        return _coordinate_column_named(self, "y") if self.table_dataset_id else self.y_column

    @kante.django_field(description="The column mapped to the z coordinate, if any")
    def z_column(self, info: Info) -> str | None:
        """The z-coordinate column."""
        return _coordinate_column_named(self, "z") if self.table_dataset_id else self.z_column

    @kante.django_field(description="The column mapped to the time coordinate, if any")
    def t_column(self, info: Info) -> str | None:
        """The time-coordinate column."""
        return _coordinate_column_named(self, "t") if self.table_dataset_id else self.t_column

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        return obj.kind == enums.LayerKind.TRACK.value


@kante.django_type(
    models.Layer,
    filters=filters.LayerFilter,
    ordering=order.LayerOrder,
    pagination=True,
    description="A layer that renders a 3D mesh (surface reconstruction / isosurface) placed and styled in a scene.",
)
class MeshLayer(Layer):
    """A layer that renders a 3D mesh, placed and styled in a scene."""

    id: auto
    mesh: Mesh | None
    collection: MeshCollection | None = kante.django_field(
        field_name="mesh_collection",
        description="The versioned, coordinate-system-anchored mesh collection this layer renders. Its geometry is fetched from the collection's Parquet catalog, not through this API",
    )
    material_color: list[int] | None
    wireframe: bool

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        return obj.kind == enums.LayerKind.MESH.value
