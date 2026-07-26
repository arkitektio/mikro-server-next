import datetime

from django.db.models import Q
import strawberry
from strawberry import auto
from typing import Annotated, List, Optional
from core import models, scalars, filters, enums
from kante.types import Info
from lightpath.objects.types import LightpathGraph
from optikit.models import OptikitStateModel
from optikit.types import OptikitStateGraph
from lightpath.objects.models import LightpathGraphModel
from core.render.layer.types import LayerRenderGraph
from core.render.layer.models import LayerRenderGraphModel
from core.render.camera.types import CameraState
from core.render.camera.models import CameraStateModel
from core.types.coords import CoordinateSystem, MeshCollection, PlacementStep, Transformation
import kante
from datalayer.types import MediaStore, ZarrStore
from core.types._shared import build_prescoped_queryset

from kanne_server import scalars as kanne_scalars

from core import order, base_models
from core.logic import coords as coords_logic
from core.logic import graph as graph_logic
from core.logic import phasor as phasor_logic
from core.logic import scene_graph

from core.types.auth import ProvenanceEntry, Task, User


#: Key for the per-request sole-occupancy map on the context's loader store.
_SOLE_OCCUPANCY_KEY = "scenes_by_sole_dataset"

#: Key for the per-request latest-snapshot-per-scene map on the context's loader store.
_LATEST_SNAPSHOT_KEY = "latest_snapshot_by_scene"


def _latest_snapshot_map(info: Info) -> "dict[int, models.SceneSnapshot] | None":
    """The latest snapshot per scene id, organization-scoped, built once per request.

    One ``DISTINCT ON (scene_id)`` query (Postgres-specific) covers every scene the
    request can see, so a page of scenes or datasets reads its tiles from a dict
    instead of running one ``ORDER BY created_at LIMIT 1`` per row. Whole-org on
    purpose: a dataset's sole scenes are arbitrary org scenes, not rows of the page's
    queryset, and the map holds at most one snapshot per scene. If org snapshot
    volume ever makes the scan hurt, scope it to ``scene_id__in``.

    Returns None when the context carries no loader store (off-request use) --
    callers then fall back to their per-row query rather than paying a whole-org
    scan with nowhere to cache it.
    """
    loaders = getattr(info.context, "_loaders", None)
    if loaders is None:
        return None
    by_scene = loaders.get(_LATEST_SNAPSHOT_KEY)
    if by_scene is None:
        rows = (
            models.SceneSnapshot.objects.filter(organization=info.context.request.organization)
            .select_related("store")
            .order_by("scene_id", "-created_at", "-pk")
            .distinct("scene_id")
        )
        by_scene = {snap.scene_id: snap for snap in rows}
        loaders[_LATEST_SNAPSHOT_KEY] = by_scene
    return by_scene


def _latest_sole_snapshot(info: Info, dataset) -> "SceneSnapshot | None":
    """The newest picture of a scene whose only anchored dataset is this one.

    The sole-occupancy map is the same for every dataset in a request and costs two flat
    queries over the org's scenes and their worlds' registrations -- so it is built once
    and cached on the request's loader store (the per-request slot kante leaves open for
    exactly this), and every ``latestSnapshot`` on the page reads the same dict.

    The candidate scenes are organization-scoped: sole occupancy asks what else is in a
    picture, and a scene from another organization is not an answer this request may see.
    """
    loaders = info.context._loaders
    by_dataset = loaders.get(_SOLE_OCCUPANCY_KEY)
    if by_dataset is None:
        scenes = models.Scene.objects.filter(organization=info.context.request.organization).select_related("world")
        by_dataset = graph_logic.scenes_by_sole_dataset(scenes)
        loaders[_SOLE_OCCUPANCY_KEY] = by_dataset

    scenes = by_dataset.get(dataset.pk)
    if not scenes:
        return None
    by_scene = _latest_snapshot_map(info)
    if by_scene is None:
        return models.SceneSnapshot.objects.filter(scene__in=scenes).order_by("-created_at", "-pk").first()
    candidates = [snap for scene in scenes if (snap := by_scene.get(scene.pk)) is not None]
    return max(candidates, key=lambda s: (s.created_at, s.pk), default=None)


@kante.django_type(
    models.ADataset,
    filters=filters.ADatasetFilter,
    ordering=order.ADatasetOrder,
    pagination=True,
    description="A multi-dimensional array dataset. Its dimensions and their types live on the axes of its INTRINSIC (pixel grid) coordinate system; physical units live on the calibrated spaces it has edges into; its pyramid levels are DataArrays, each mapping into its grid",
)
class ADataset:
    """A multi-dimensional array dataset with named dimensions, described by its intrinsic pixel-grid coordinate system."""

    id: auto
    name: auto
    description: str | None
    # `name` and `description` are the only two fields `updateADataset` can reach, which is
    # exactly why the audit trail is worth reading: a rename is the one thing about a dataset
    # that can change, so who changed it is the one history there is to keep.
    provenance_entries: List["ProvenanceEntry"] = kante.django_field(
        description="Every change made to this dataset: who created it, and every subsequent rename or redescription, attributed to the client, user and task it happened under. Only `name` and `description` can change -- the arrays, the axes and the coordinate systems built from them are fixed at creation"
    )
    created_through: Task | None = kante.django_field(description="The task this dataset was created through, if any")
    created_through_by: User | None = kante.django_field(description="The assigner of the creating task, if any")
    data_arrays: List["DataArray"] = kante.django_field(description="The multiscale data arrays belonging to this dataset")

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

    @kante.django_field(
        description="The datasets computed from this one -- the other end of `derivedFrom`, and the way to ask what a source produced: the deconvolutions, segmentations and projections that named a space of this dataset as their parent. Derived from the same edges, never a stored back-reference that could disagree with them. Every child, not just those this dataset places: a fusion that named this source second is listed here, and so is a child whose derivation is UNMAPPABLE -- it came from here even though its geometry did not survive. The maps themselves are on each child's own `derivedFrom`"
    )
    def derived_datasets(self, info: Info) -> List["ADataset"]:
        """The datasets whose derivation edges land in one of this dataset's spaces."""
        return graph_logic.derived_datasets(self)

    @kante.django_field(description="Whether this dataset carries a resolution pyramid. Derived: true when it has more than one level")
    def multiscale(self, info: Info) -> bool:
        """Whether the dataset has more than one pyramid level."""
        return self.multiscale

    @kante.django_field(description="The dataset's axis names, in array order. Derived from the axes of its intrinsic coordinate system")
    def axis_names(self, info: Info) -> List[str]:
        """The dataset's axis names."""
        return self.axis_names

    @kante.django_field(
        description="What this dataset structurally is, materialized from the axes of its intrinsic coordinate system at creation: the one spatial spec its SPACE axis count denotes, then a modifier per acquisition axis present. A 3D timelapse is [VOLUME, TIMESERIES, MULTICHANNEL]. Presence, not size: a stack with a single plane is still a VOLUME. Empty while the intrinsic system does not exist yet"
    )
    def spec(self, info: Info) -> List[enums.ADatasetSpec]:
        """Every spec the dataset's axes satisfy."""
        return self.spec

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

    @kante.django_field(
        description="The most recent picture that shows this dataset and nothing else, for previewing it without loading the array. Snapshots are taken of scenes, not of datasets, so this only answers with a scene whose *only* anchored dataset is this one -- anchored meaning the scene's world is one of the dataset's own systems or a registration into it sets out from one, and a picture blending several datasets is a preview of none of them. Null when every scene it is anchored in also holds other data. Caveats it cannot rule out: the dataset may be anchored in that scene without any layer drawing it (the picture can be empty), a mesh or table collection may be drawn over it as an annotation, and a dataset placed only through a derived parent's registration does not count -- for or against"
    )
    def latest_snapshot(self, info: Info) -> Optional["SceneSnapshot"]:
        """The newest picture of a scene whose only anchored dataset is this one."""
        return _latest_sole_snapshot(info, self)


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
        select_related=["coordinate_system", "dataset__coordinate_system"],
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

    @kante.django_field(description="The recorded microscope state, reconstructed into its typed form: stage pose and environment as quantities, everything else as per-device named settings")
    def state(self, info: Info) -> OptikitStateGraph:
        """The recorded microscope state."""
        return OptikitStateModel(**self.state)


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
    models.Scene,
    filters=filters.SceneFilter,
    pagination=True,
    ordering=order.SceneOrder,
    description="A composition of layers over a shared world coordinate system. The scene carries no units of its own -- they are per-axis, on the axes of its world system",
)
class Scene:
    """A composition of layers over a shared world coordinate system."""

    id: auto
    name: auto
    layers: List["Layer"] = kante.django_field(
        filters=filters.LayerFilter,
        ordering=order.LayerOrder,
        pagination=True,
        description="The layers placed in this scene (a heterogeneous list of layer kinds)",
    )
    snapshots: List["SceneSnapshot"] = kante.django_field(
        filters=filters.SceneSnapshotFilter,
        ordering=order.SceneSnapshotOrder,
        pagination=True,
        description="The pre-rendered pictures of this composition, for previewing it without compositing the layers",
    )
    animations: List["Animation"] = kante.django_field(
        filters=filters.AnimationFilter,
        ordering=order.AnimationOrder,
        pagination=True,
        description="The named camera tours through this composition",
    )
    preferred_view: enums.PreferredView = kante.django_field(description="How a viewer should open this scene: flat, volumetric, or its own choice. A preference, not a constraint -- nothing server-side reads it, and a viewer that cannot render volumes is not wrong to show the slice view")
    background_color: list[float] | None = kante.django_field(description="The viewer background, as RGBA. Null lets the viewer use its own")
    @kante.django_field(description="The most recent picture of this composition -- the tile to put on the scene. Null until something snapshots it")
    def latest_snapshot(self, info: Info) -> Optional["SceneSnapshot"]:
        """The newest picture of this scene."""
        by_scene = _latest_snapshot_map(info)
        if by_scene is None:
            return self.snapshots.order_by("-created_at", "-pk").first()
        return by_scene.get(self.pk)

    world_coordinate_system: CoordinateSystem = kante.django_field(
        field_name="world",
        description="The shared space this scene composes its layers over. Never owned by the scene: many scenes can share it, it outlives each of them, and deleting a scene never deletes it",
    )
    @kante.django_field(
        description="The registrations composing this scene: every top-level edge into its world system. A property of the *space*, not of the scene (one truth per space) -- every scene over the same world shares them, each unique for its data-tree, and `layers.pathToWorld` searches exactly these plus the datasets' own facts. Composing the matrices stays the client's job"
    )
    def registrations(self, info: Info) -> List[Transformation]:
        """The registrations into this scene's world system."""
        return list(models.Transformation.objects.filter(parent__isnull=True, output=self.world_id).order_by("pk"))

    @kante.django_field(description="Every coordinate system reachable in this scene: its world system plus those its transformation edges touch")
    def coordinate_systems(self, info: Info) -> List[CoordinateSystem]:
        """The coordinate systems reachable from this scene's edges."""
        return scene_graph.for_request(info, self).reachable_systems()

    @kante.django_field(description="The annotations drawn in a space this scene can reach. Reachability, not containment: an annotation belongs to a collection, and survives the scene's deletion")
    def annotations(self, info: Info) -> List["Annotation"]:
        """The annotations whose collection's system is reachable in this scene's graph."""
        # The same closure `coordinateSystems` walks: asking a scene for both used to walk
        # it twice. Reachability is a property of the scene, not of the field asking.
        # A collection's own system hangs one edge off whatever it is drawn over, and
        # that edge is in no world universe -- so a collection also counts as reachable
        # when any of its (non-UNMAPPABLE) edges lands in a reachable system.
        reachable = scene_graph.for_request(info, self).reachable_system_ids()
        anchored = (
            models.Transformation.objects.filter(parent__isnull=True, input__annotation_collections__isnull=False, output__in=reachable)
            .exclude(kind=enums.TransformKind.UNMAPPABLE.value)
            .values_list("input_id", flat=True)
        )
        return models.Annotation.objects.filter(Q(collection__coordinate_system__in=reachable) | Q(collection__coordinate_system__in=anchored)).select_related("collection__coordinate_system")

    @kante.django_field(description="The annotation collection minted for this scene as its default drawing surface, or null before the first annotation is drawn on it. Bookkeeping, not placement: what places the collection is its registration edge into this scene's world")
    def annotation_collection(self, info: Info) -> Optional["AnnotationCollection"]:
        """The scene's minted drawing surface, if any."""
        return getattr(self, "annotation_collection", None)


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
        description="The most recent picture that shows this lens' dataset and nothing else -- the tile to put on this lens. The same picture the dataset itself reports: snapshots are taken of scenes, and sole occupancy is a fact about the dataset, so every lens over one dataset answers alike. Null when every scene it is anchored in also holds other data"
    )
    def latest_snapshot(self, info: Info) -> Optional["SceneSnapshot"]:
        """The newest picture of a scene whose only anchored dataset is this lens' dataset."""
        return _latest_sole_snapshot(info, self.dataset)

    @kante.django_field(
        select_related=["coordinate_system", "dataset__coordinate_system"],
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

    @kante.django_field(
        description="The datasets computed from this lens' selection: the direct other end of `derivedFrom`, which names a *lens* as a parent rather than a dataset. An unsliced lens reports what was derived from the whole intrinsic grid -- its space is that grid, so it can say nothing narrower. Like the forward field this reports every child, whether or not this lens is its primary parent and whether or not its geometry survived"
    )
    def derived_datasets(self, info: Info) -> List[ADataset]:
        """The datasets whose derivation edges land in this lens' space."""
        return graph_logic.lens_derived_datasets(self)

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


@kante.django_type(
    models.AnimationWaypoint,
    pagination=True,
    description="One camera pose in a tour, and how the viewer travels to it",
)
class AnimationWaypoint:
    """One camera pose in a tour, and how the viewer travels to it."""

    id: auto
    animation: "Animation" = kante.django_field(description="The tour this pose belongs to")
    order: int = kante.django_field(description="The pose's index in the tour. Written by enumeration when the tour is authored, so it always runs 0, 1, 2 ... with no gaps")
    name: str = kante.django_field(description="What this stop shows, e.g. 'the nucleus'")
    duration_ms: int = kante.django_field(description="How long the viewer takes to travel TO this pose, in milliseconds. Ignored for the first pose, which is where the tour starts")
    easing: enums.Easing = kante.django_field(description="How the viewer eases the camera along that travel")

    @kante.django_field(description="Where the camera is: a position keyed by the world's axis names, plus the flat and volumetric views of it")
    def camera(self, info: Info) -> CameraState:
        """The camera pose, rehydrated from its stored dump."""
        return CameraStateModel(**self.camera)


@kante.django_type(
    models.Animation,
    filters=filters.AnimationFilter,
    ordering=order.AnimationOrder,
    pagination=True,
    description="A named camera tour of a scene: the poses a viewer pans through, in order. A view artifact -- it cascades with the scene, no placement walk crosses it, and refining a registration moves the data but never the camera",
)
class Animation:
    """A named camera tour of a scene: the poses a viewer pans through, in order."""

    id: auto
    scene: "Scene" = kante.django_field(description="The scene this tour flies through")
    name: str
    description: str | None
    waypoints: List[AnimationWaypoint] = kante.django_field(description="The poses the viewer pans through, in tour order")
    created_at: datetime.datetime
    creator: User | None
    created_through: Task | None = kante.django_field(description="The task this tour was created through, if any")
    created_through_by: User | None = kante.django_field(description="The assigner of the creating task, if any")

    @classmethod
    def get_queryset(cls, queryset, info, **kwargs):
        """Scope the list to the request's organization.

        A bare list field returns every row in the table, across organizations -- the hole
        the legacy `snapshots` field still has.
        """
        return build_prescoped_queryset(info, queryset)


@kante.django_type(
    models.SceneSnapshot,
    filters=filters.SceneSnapshotFilter,
    ordering=order.SceneSnapshotOrder,
    pagination=True,
    description="A pre-rendered picture of a composition: every layer of the scene, blended. Clients use snapshots to preview without compositing the layers themselves. A picture of the scene, not of any one dataset in it -- though `ADataset.latestSnapshot` will offer one of these where the scene's only anchored dataset is that dataset, since then the picture shows it and nothing else",
)
class SceneSnapshot:
    """A pre-rendered picture of a composition: every layer of the scene, blended."""

    id: auto
    scene: "Scene" = kante.django_field(description="The composition this is a picture of")
    store: MediaStore = kante.django_field(description="The media store holding the rendered image. Ask it for a presignedUrl or an accessGrant to actually fetch the bytes")
    name: str
    major_color: list[float] | None = kante.django_field(description="The dominant color of the image, for tinting a placeholder while it loads")
    created_at: datetime.datetime
    creator: User | None
    created_through: Task | None = kante.django_field(description="The task this snapshot was created through, if any")
    created_through_by: User | None = kante.django_field(description="The assigner of the creating task, if any")

    @classmethod
    def get_queryset(cls, queryset, info, **kwargs):
        """Scope the list to the request's organization.

        Not inherited from anywhere: a bare list field returns every row in the table,
        across organizations. The legacy `snapshots` field has exactly that hole -- only
        its single-item resolver is scoped -- and it cannot be closed the same way there,
        because Snapshot has no organization column to filter on. This model does.
        """
        return build_prescoped_queryset(info, queryset)


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

    for system in graph_logic.calibrated_neighbours(dataset.coordinate_system) if dataset.coordinate_system else []:
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
    description=(
        "A layer placed in a scene and alpha-blended over the layers below it. It carries view state only: a spatial fact is a coordinate system or a transformation edge, never a "
        "field here, and every spatial question a layer answers -- `pathToWorld`, `placement`, `placementValidity`, `placementInvariance` -- is derived from the graph on read and "
        "stored nowhere, so refining one edge updates every layer that looks through it. Which columns hold a point layer's coordinates is likewise the table dataset's declaration, "
        "not a per-layer copy. The concrete kind (ImageLayer, AnnotationLayer, PointLayer, TrackLayer, MeshLayer) carries its own data source and render settings."
    ),
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
        description="The path of transformation edges from this layer's source coordinate system to its scene's world system. A layer belongs to exactly one scene, so this is the one 'to world' question with a single right answer -- the path uses the layer's dataset facts plus the world's registrations, which are the same for every scene over that space. Null when the layer is unregistered or has no source system; empty when the source already is the world system. The server returns the edges; composing them (inverting flagged steps) stays the client's job",
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
        description="How much this layer's placement is actually known: the weakest edge on its path to world. UNKNOWN while the path rests on an assumed edge (an uncalibrated bootstrap mirror, or none at all); MANUAL once someone authored the registration; VALIDATED once it was checked. Derived, never stored -- and distinct from a single edge's `validity`: this is the minimum over the whole path",
    )
    def placement_validity(self, info: Info) -> enums.PlacementValidity:
        """The weakest validity on the layer's placement path."""
        return enums.PlacementValidity(scene_graph.for_request(info, self.scene).placement_validity(self))

    @kante.django_field(
        description=(
            "Which geometric properties survive the whole walk from this layer's data to its scene's world: the weakest edge on its path. ISOMETRY means a distance measured in "
            "the data IS that distance in world; SIMILARITY means shapes and angles transfer and every length needs one common factor; AFFINE means only parallelism and area "
            "ratios do, so an angle or a distance read in the data means nothing in world; DIFFEOMORPHIC means nothing metric survives anywhere; NONE means there is no path at "
            "all. This is what says whether a scalar length in scene units (`pointSize`, `lineWidth`, a stroke width, a camera zoom) is well defined for this layer: it is, from "
            "SIMILARITY up. Derived, never stored -- and distinct from a single edge's `invariance`, this being the minimum over the whole path. `placement` says which of the "
            "two reasons a NONE layer has"
        ),
    )
    def placement_invariance(self, info: Info) -> enums.TransformInvariance:
        """The weakest invariance class on the layer's placement path."""
        return enums.TransformInvariance(scene_graph.for_request(info, self.scene).placement_invariance(self))


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
        description="Per pyramid level, the path from that level's voxel grid to this scene's world system. What a multiscale renderer consumes directly: pick a level by zoom and use its path -- every level stars into the same intrinsic system, so the registration tail is shared. A level's path is null when the dataset is not registered into the scene",
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


@kante.type(description="The placement of one pyramid level in a layer's scene: the level and its path to the world system")
class LevelPlacement:
    """The placement of one pyramid level in a layer's scene."""

    data_array: "DataArray" = strawberry.field(description="The pyramid level being placed")
    path: List[PlacementStep] | None = strawberry.field(description="The path from this level's voxel grid to the scene's world system, or null when the dataset is not registered into the scene")


@kante.type(description="A discrete coordinate an annotation is pinned to, e.g. a timepoint or a channel")
class Coordinate:
    """A discrete coordinate an annotation is pinned to, e.g. a timepoint or a channel."""

    name: str = strawberry.field(description="The name of the coordinate, e.g. 't' or 'c'")
    value: int = strawberry.field(description="The value along that coordinate")


@kante.type(description="An axis-aligned bounding box, as a min and a max corner")
class BoundingBox:
    """An axis-aligned bounding box, as a min and a max corner."""

    min: list[float] = strawberry.field(description="The lower corner, in the coordinate order of the coordinate system")
    max: list[float] = strawberry.field(description="The upper corner, in the coordinate order of the coordinate system")


@kante.django_type(
    models.AnnotationCollection,
    filters=filters.AnnotationCollectionFilter,
    ordering=order.AnnotationCollectionOrder,
    pagination=True,
    description="A named set of human-drawn annotations, owning the coordinate system they are drawn in. The CRUD counterpart of a table dataset's machine-produced rows: shapes a person draws and edits, sharing one drawing space and one registration story",
)
class AnnotationCollection:
    """A named set of human-drawn annotations, owning the space they are drawn in."""

    id: auto
    name: auto
    description: str | None
    scene: Optional["Scene"] = kante.django_field(description="The scene this collection was minted for as its default drawing surface, or null for a freestanding or dataset-derived collection. Bookkeeping, not placement: the registration edge is what places it")
    coordinate_system: CoordinateSystem = kante.django_field(description="The coordinate system the annotations' vectors are expressed in. The collection owns it; `derivedFrom` relates it to whatever the shapes are drawn over")
    annotations: List["Annotation"] = kante.django_field(description="The annotations in this collection")
    created_at: datetime.datetime
    creator: User | None
    provenance_entries: List["ProvenanceEntry"] = kante.django_field(description="Provenance entries for this annotation collection")

    @kante.django_field(
        description="The edge relating this collection's space to the space the shapes are drawn over -- an identity into a scene's world for a scene-minted collection, an identity into a dataset's system for one drawn over an image. Null for a freestanding collection"
    )
    def derived_from(self, info: Info) -> Transformation | None:
        """The edge relating this collection's space to the one it is drawn over."""
        system = getattr(self, "coordinate_system", None)
        return graph_logic.collection_derivation_edge(system) if system else None

    @classmethod
    def get_queryset(cls, queryset, info, **kwargs):
        """Scope the list to the request's organization.

        A bare list field returns every row in the table, across organizations -- the
        hole the old `dataRois` field had.
        """
        return build_prescoped_queryset(info, queryset)


@kante.django_type(
    models.Annotation,
    filters=filters.AnnotationFilter,
    ordering=order.AnnotationOrder,
    pagination=True,
    description="A human-drawn shape in an annotation collection's coordinate system. It belongs to the collection, not to a scene: delete the scene and the annotation survives",
)
class Annotation:
    """A human-drawn shape in its collection's coordinate system, described by its vectors and the discrete coordinates it is pinned to."""

    id: auto
    collection: AnnotationCollection = kante.django_field(description="The collection this annotation belongs to; its vectors are expressed in the collection's own coordinate system")
    name: auto
    description: str | None
    kind: enums.RoiKind
    vectors: list[list[float]]
    created_with_transforms: int
    stroke_color: list[int] | None = kante.django_field(description="The stroke (outline) color of the geometry, as RGBA")
    fill_color: list[int] | None = kante.django_field(description="The fill color of the geometry, as RGBA, or null for no fill")
    stroke_width: float = kante.django_field(description="The stroke width of the geometry, in the drawing space's units. One number for every direction, so it is a well-defined length only where that space's axes share a scale")
    filled: bool = kante.django_field(description="Whether the geometry is filled with fill_color")
    provenance_entries: List["ProvenanceEntry"] = kante.django_field(description="Provenance entries for this annotation")

    @kante.django_field(description="The coordinate system this annotation's vectors are expressed in: its collection's own system")
    def coordinate_system(self, info: Info) -> CoordinateSystem | None:
        """The collection's coordinate system, surfaced for convenience."""
        return self.collection.coordinate_system_or_none

    @kante.django_field(description="The discrete coordinates this annotation is pinned to. A coordinate the annotation does not pin is one it spans")
    def coordinates(self, info: Info) -> list[Coordinate]:
        """The annotation's discrete pins, unpacked from the stored name-keyed dict."""
        return [Coordinate(name=name, value=value) for name, value in (self.coordinates or {}).items()]

    @kante.django_field(
        description="The annotation's bounding box in the nearest intrinsic space, derived from every corner of its geometry (an affine-transformed box is not a box: min/max alone gives a strictly too-small answer under rotation or shear). Intrinsic, not world: world is scene-owned, and one collection can sit in two scenes under two registrations"
    )
    def intrinsic_bbox(self, info: Info) -> BoundingBox | None:
        """The annotation's bounding box in the nearest intrinsic space."""
        if not self.intrinsic_bbox:
            return None
        return BoundingBox(min=self.intrinsic_bbox["min"], max=self.intrinsic_bbox["max"])

    @classmethod
    def get_queryset(cls, queryset, info, **kwargs):
        """Scope the list to the request's organization, carrying the system along.

        Through the required collection FK -- the annotation carries no organization
        column of its own. A bare list field returns every row in the table, across
        organizations: the hole the old `dataRois` field had. The select_related is
        for the `coordinateSystem` resolver, which walks collection -> system per
        row and would otherwise cost two queries per annotation.
        """
        return queryset.filter(collection__organization=info.context.request.organization).select_related("collection__coordinate_system")


@kante.django_type(
    models.Layer,
    filters=filters.LayerFilter,
    ordering=order.LayerOrder,
    pagination=True,
    description="A layer that renders an annotation collection's drawn shapes (polygons, boxes, ellipses, lines, paths) in a scene. One layer per collection: per-shape styling lives on the annotations themselves.",
)
class AnnotationLayer(Layer):
    """A layer that renders an annotation collection's drawn shapes in a scene."""

    id: auto
    annotation_collection: AnnotationCollection = kante.django_field(description="The annotation collection whose shapes this layer renders. Its own coordinate system is the layer's space")

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        return obj.kind == enums.LayerKind.ANNOTATION.value


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
    description="A layer that renders a point cloud (e.g. SMLM localisations, centroids) from a table dataset.",
)
class PointLayer(Layer):
    """A layer that renders a point cloud from a table dataset, placed and styled in a scene."""

    id: auto
    table_dataset: Annotated["TableDataset", strawberry.lazy("core.types.table_dataset")] = kante.django_field(
        description="The table dataset the points are drawn from. Its declared coordinate columns provide the coordinates and its own system provides the placement -- the column fields below are derived from its schema, never stored per layer"
    )
    size_column: str | None
    color_column: str | None
    point_size: float | None
    colormap: enums.ColorMap | None

    @kante.django_field(description="The coordinate column whose axis is named 'x', from the dataset's declared schema")
    def x_column(self, info: Info) -> str | None:
        """The x-coordinate column."""
        return _coordinate_column_named(self, "x")

    @kante.django_field(description="The coordinate column whose axis is named 'y'")
    def y_column(self, info: Info) -> str | None:
        """The y-coordinate column."""
        return _coordinate_column_named(self, "y")

    @kante.django_field(description="The coordinate column whose axis is named 'z', if any")
    def z_column(self, info: Info) -> str | None:
        """The z-coordinate column."""
        return _coordinate_column_named(self, "z")

    @kante.django_field(description="The coordinate column whose axis is named 't', if any")
    def t_column(self, info: Info) -> str | None:
        """The time-coordinate column."""
        return _coordinate_column_named(self, "t")

    @kante.django_field(description="The dataset's ID-role column identifying each point, if any")
    def id_column(self, info: Info) -> str | None:
        """The point-id column."""
        return _role_column(self, enums.TableColumnRoleChoices.ID.value)

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        return obj.kind == enums.LayerKind.POINT.value


@kante.django_type(
    models.Layer,
    filters=filters.LayerFilter,
    ordering=order.LayerOrder,
    pagination=True,
    description="A layer that renders trajectories (e.g. particle/cell tracks) from a table dataset, grouped by its TRACK_ID column.",
)
class TrackLayer(Layer):
    """A layer that renders trajectories from a table dataset, placed and styled in a scene."""

    id: auto
    table_dataset: Annotated["TableDataset", strawberry.lazy("core.types.table_dataset")] = kante.django_field(
        description="The table dataset the tracks are drawn from. Its coordinate and TRACK_ID columns provide the trajectories -- the column fields below are derived from its schema, never stored per layer"
    )
    color_by_column: str | None
    line_width: float | None
    colormap: enums.ColorMap | None

    @kante.django_field(description="The dataset's TRACK_ID column, which groups rows into tracks")
    def track_id_column(self, info: Info) -> str | None:
        """The track-id column."""
        return _role_column(self, enums.TableColumnRoleChoices.TRACK_ID.value)

    @kante.django_field(description="The coordinate column whose axis is named 'x', from the dataset's declared schema")
    def x_column(self, info: Info) -> str | None:
        """The x-coordinate column."""
        return _coordinate_column_named(self, "x")

    @kante.django_field(description="The coordinate column whose axis is named 'y'")
    def y_column(self, info: Info) -> str | None:
        """The y-coordinate column."""
        return _coordinate_column_named(self, "y")

    @kante.django_field(description="The coordinate column whose axis is named 'z', if any")
    def z_column(self, info: Info) -> str | None:
        """The z-coordinate column."""
        return _coordinate_column_named(self, "z")

    @kante.django_field(description="The coordinate column whose axis is named 't', if any")
    def t_column(self, info: Info) -> str | None:
        """The time-coordinate column."""
        return _coordinate_column_named(self, "t")

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
    collection: MeshCollection | None = kante.django_field(
        field_name="mesh_collection",
        description="The versioned, coordinate-system-anchored mesh collection this layer renders. Its geometry is fetched from the collection's Parquet catalog, not through this API",
    )
    material_color: list[int] | None
    wireframe: bool

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        return obj.kind == enums.LayerKind.MESH.value
