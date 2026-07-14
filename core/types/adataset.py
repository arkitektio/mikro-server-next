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
from core.types.coords import CoordinateSystem, MeshCollection, Transformation
import kante
from datalayer.types import ZarrStore

from core import order, base_models
from core.logic import coords as coords_logic
from core.logic import graph as graph_logic

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

    @kante.django_field(description="Whether this dataset carries a resolution pyramid. Derived: true when it has more than one level")
    def multiscale(self, info: Info) -> bool:
        """Whether the dataset has more than one pyramid level."""
        return self.multiscale

    @kante.django_field(description="The dataset's dimension names, in array order. Derived from the axes of its intrinsic coordinate system")
    def dims(self, info: Info) -> List[str]:
        """The dataset's dimension names."""
        return self.dims_list

    @kante.django_field(description="The dataset's shape: that of its level-0 array")
    def shape(self, info: Info) -> List[int]:
        """The dataset's shape."""
        return self.shape_list


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
    coordinate_system: CoordinateSystem | None = kante.django_field(description="This level's ARRAY (voxel index) coordinate system")

    @kante.django_field(
        disable_optimization=True,
        description="The edge from this level's voxel space into the dataset's intrinsic space. Its scale is absolute -- derived from the actual shapes, not from a nominal 2**level -- so a pyramid whose axes do not halve cleanly is described correctly",
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
    models.CoordinateAnchor,
    filters=filters.CoordinateAnchorFilter,
    pagination=True,
    description="The axis-agnostic hub that pins metadata spokes (microscope state, OME metadata, value histograms, channel labels, light paths) to specific coordinates of a dataset",
)
class CoordinateAnchor:
    """The axis-agnostic hub that pins metadata spokes (microscope state, OME metadata, value histograms, channel labels, light paths) to specific coordinates of a dataset"""

    id: auto
    # The reverse accessor from OptikitState.anchor is `microscope`, not `optikit_state`.
    microscope: OptikitState | None = kante.django_field(description="The microscope state recorded at this coordinate")
    value_histogram: ValueHistogram | None
    channel_label: ChannelLabel | None
    light_graph: LightPath | None

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
        # Disable the query optimizer for this interface list: with a discriminated
        # single-table interface it otherwise evaluates the queryset synchronously
        # during async type resolution ("cannot call this from an async context").
        disable_optimization=True,
        description="The layers placed in this scene (a heterogeneous list of layer kinds)",
    )
    world_coordinate_system: CoordinateSystem | None = kante.django_field(description="The scene's shared WORLD coordinate system, into which each of its layers is registered")
    coordinate_transformations: List[Transformation] = kante.django_field(
        # Same reason as `layers` above: a discriminated single-table interface.
        disable_optimization=True,
        description="The transformation edges belonging to this scene, e.g. the registrations placing each layer's dataset into the world system. Compose them client-side: the server does not resolve paths, because the same dataset can sit in two scenes under two different registrations",
    )

    @kante.django_field(description="Every coordinate system reachable in this scene: its world system plus those its transformation edges touch")
    def coordinate_systems(self, info: Info) -> List[CoordinateSystem]:
        """The coordinate systems reachable from this scene's edges."""
        return graph_logic.reachable_coordinate_systems(self)

    @kante.django_field(description="The ROIs drawn in a coordinate system this scene can reach. Reachability, not containment: an ROI belongs to a coordinate system, and survives the scene's deletion")
    def rois(self, info: Info) -> List["DataRoi"]:
        """The ROIs whose coordinate system is reachable in this scene's graph."""
        return models.DataRoi.objects.filter(coordinate_system__in=graph_logic.reachable_coordinate_systems(self))


@kante.pydantic_type(base_models.SliceModel, description="A slice along a named dimension, with optional start, stop and step")
class Slice:
    """A slice along a named dimension, with optional start, stop and step"""

    dim: str
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
    """A selection over a dataset. Its shape and dims are derived from the dataset and the slices."""

    id: auto
    dataset: ADataset
    dim_count: int
    size: int
    coordinate_system: CoordinateSystem | None = kante.django_field(description="The lens' own coordinate system: the space its slices cut out")

    @kante.django_field(description="The lens' dimension names, in array order. A selection never drops or reorders an axis")
    def dims(self, info: Info) -> List[str]:
        """The lens' dimension names."""
        return self.dims_list

    @kante.django_field(description="The shape this lens' slices cut out of its dataset")
    def shape(self, info: Info) -> List[int]:
        """The lens' shape."""
        return self.shape_list

    @kante.django_field(
        disable_optimization=True,
        description="The edge from this lens' space back into its dataset's level-0 voxel space. A crop is a translation of the slice starts; a stepped lens also rescales. Without this edge an ROI drawn on a cropped lens has no defined path back to its dataset",
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


@kante.type(description="Which axis of a data source maps to screen x, y, z, time and intensity. Derived from the axis types, never stored")
class RenderAxes:
    """Which axis of a data source maps to screen x, y, z, time and intensity."""

    x: str = strawberry.field(description="The axis mapped to screen x: the last (fastest-varying) spatial axis")
    y: str = strawberry.field(description="The axis mapped to screen y: the second-to-last spatial axis")
    z: str | None = strawberry.field(description="The axis mapped to screen z: the third-to-last spatial axis, if the data is volumetric")
    t: str | None = strawberry.field(description="The time axis, if the data has one")
    intensity: str | None = strawberry.field(description="The channel axis, if the data has one")


@kante.django_interface(
    models.Layer,
    description="A layer placed in a scene and alpha-blended over the layers below it. It carries view state only: registration is a scene-level transformation edge, not a property of the view. The concrete kind (ImageLayer, ShapeLayer, PointLayer, TrackLayer, MeshLayer) carries its own data source and render settings.",
)
class Layer:
    """A layer placed in a scene, carrying the shared placement and compositing settings. No spatial fields."""

    id: auto
    kind: enums.LayerKind
    scene: Scene
    status: auto
    blending: enums.Blending
    opacity: float
    visible: bool
    order: int


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


@kante.django_type(
    models.Layer,
    filters=filters.LayerFilter,
    ordering=order.LayerOrder,
    pagination=True,
    description="A layer that renders a point cloud (e.g. SMLM localisations, centroids) from columns of a table.",
)
class PointLayer(Layer):
    """A layer that renders a point cloud from table columns, placed and styled in a scene."""

    id: auto
    table: Annotated["Table", strawberry.lazy("core.types.image")]
    coordinate_system: CoordinateSystem | None = kante.django_field(
        description="The coordinate system the table's coordinate columns are expressed in. Registering the points elsewhere is a transformation edge from this system, like every other spatial fact"
    )
    x_column: str | None
    y_column: str | None
    z_column: str | None
    t_column: str | None
    size_column: str | None
    color_column: str | None
    id_column: str | None
    point_size: float | None
    colormap: enums.ColorMap | None

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        return obj.kind == enums.LayerKind.POINT.value


@kante.django_type(
    models.Layer,
    filters=filters.LayerFilter,
    ordering=order.LayerOrder,
    pagination=True,
    description="A layer that renders trajectories (e.g. particle/cell tracks) from columns of a table, grouped by a track id.",
)
class TrackLayer(Layer):
    """A layer that renders trajectories from table columns, placed and styled in a scene."""

    id: auto
    table: Annotated["Table", strawberry.lazy("core.types.image")]
    coordinate_system: CoordinateSystem | None = kante.django_field(
        description="The coordinate system the table's coordinate columns are expressed in. Registering the tracks elsewhere is a transformation edge from this system, like every other spatial fact"
    )
    track_id_column: str | None
    x_column: str | None
    y_column: str | None
    z_column: str | None
    t_column: str | None
    color_by_column: str | None
    line_width: float | None
    colormap: enums.ColorMap | None

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
