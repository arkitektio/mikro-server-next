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
import kante
from datalayer.types import ZarrStore

from core import order, base_models

from core.types.auth import ProvenanceEntry, Task, User


@kante.pydantic_type(base_models.DimDescriptor, description="A descriptor for a single named dimension of a dataset, recording its key, size and kind")
class DimDescriptor:
    """A descriptor for a single named dimension of a dataset, recording its key, size and kind"""

    key: str
    size: int
    kind: enums.DimensionKind


@kante.django_type(
    models.ADataset,
    filters=filters.ADatasetFilter,
    ordering=order.ADatasetOrder,
    pagination=True,
    description="A multi-dimensional array dataset with named dimensions. It can have multiple scales attached to it, which are represented as DataArrays",
)
class ADataset:
    """A multi-dimensional array dataset with named dimensions. It can have multiple scales attached to it, which are represented as DataArrays"""

    id: auto
    name: auto
    description: str | None
    dims: list[str]
    created_through: Task | None = kante.django_field(description="The task this dataset was created through, if any")
    created_through_by: User | None = kante.django_field(description="The assigner of the creating task, if any")
    data_arrays: List["DataArray"] = kante.django_field(description="The multiscale data arrays belonging to this dataset")

    @kante.django_field()
    def dim_descriptors(self, info: Info) -> List[DimDescriptor]:
        return self.dim_descriptors_list


@kante.django_type(
    models.DataArray,
    filters=filters.DataArrayFilter,
    ordering=order.DataArrayOrder,
    pagination=True,
    description="A single scale of a dataset's multiscale pyramid: a zarr-backed array described by its shape, chunk shape, scale factors and pyramid level",
)
class DataArray:
    """A single scale of a dataset's multiscale pyramid: a zarr-backed array described by its shape, chunk shape, scale factors and pyramid level"""

    id: auto
    store: ZarrStore
    shape: list[int]
    chunk_shape: list[int]
    scale_factors: list[float] | None
    level: int


@kante.django_type(
    models.OptikitState,
    filters=filters.OptikitStateFilter,
    pagination=True,
    description="The hardware truth: the recorded microscope (Optikit) state pinned to a coordinate anchor",
)
class OptikitState:
    """The hardware truth: the recorded microscope (Optikit) state pinned to a coordinate anchor"""

    id: auto
    store: ZarrStore
    shape: list[int]
    chunk_shape: list[int]
    dims: list[str]


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
    store: ZarrStore
    shape: list[int]
    chunk_shape: list[int]
    dims: list[str]
    optikit_state: OptikitState | None
    value_histogram: ValueHistogram | None
    channel_label: ChannelLabel | None
    light_graph: LightPath | None


@kante.django_type(
    models.OmeMetadata,
    filters=filters.OmeMetadataFilter,
    pagination=True,
    description="The image truth: OME image metadata pinned to a coordinate anchor",
)
class OmeMetadata:
    """The image truth: OME image metadata pinned to a coordinate anchor"""

    id: auto
    store: ZarrStore
    shape: list[int]
    chunk_shape: list[int]
    dims: list[str]


@kante.django_type(
    models.OmePlaneMetadata,
    filters=filters.OmePlaneMetadataFilter,
    pagination=True,
    description="The plane truth: OME plane metadata pinned to a coordinate anchor",
)
class OmePlaneMetaData:
    """The plane truth: OME plane metadata pinned to a coordinate anchor"""

    id: auto
    store: ZarrStore
    shape: list[int]
    chunk_shape: list[int]
    dims: list[str]


@kante.django_type(
    models.Scene,
    filters=filters.SceneFilter,
    pagination=True,
    ordering=order.SceneOrder,
    description="The absolute coordinate universe in which layers are placed, with defined spatial and temporal base units",
)
class Scene:
    """The absolute coordinate universe in which layers are placed, with defined spatial and temporal base units"""

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
    spatial_unit: enums.SpatialUnit
    temporal_unit: enums.TemporalUnit


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
    """A Lens is a way of looking at a dataset: a dimensional selection (slices) over a dataset that defines a view of its data"""

    id: auto
    dataset: ADataset
    dims: list[str]
    dim_count: int
    shape: list[int]
    size: int

    @kante.django_field()
    def dim_descriptors(self, info: Info) -> List[DimDescriptor]:
        return self.dim_descriptors_list

    @kante.django_field()
    def slices(self, info: Info) -> List[Slice]:
        return self.slices_list

    @kante.django_field()
    def active_anchors(self, info: Info) -> List[CoordinateAnchor]:
        return self.active_anchors


@kante.django_interface(
    models.Layer,
    description="A layer placed in a scene and alpha-blended over the layers below it. The concrete kind (ImageLayer, ShapeLayer, PointLayer, TrackLayer, MeshLayer) carries its own data source and render settings.",
)
class Layer:
    """A layer placed in a scene, carrying the shared placement and compositing settings."""

    id: auto
    kind: enums.LayerKind
    scene: Scene
    status: auto
    affine_matrix: scalars.FourByFourMatrix | None
    blending: enums.Blending
    opacity: float
    visible: bool
    order: int


@kante.django_type(
    models.Layer,
    filters=filters.LayerFilter,
    ordering=order.LayerOrder,
    pagination=True,
    description="A layer that renders array (lens) data as an alpha-blended image. Its rendering is described entirely by the composable render graph.",
)
class ImageLayer(Layer):
    """A layer that renders array (lens) data. All rendering (colormap, contrast, gamma, per-channel blend) lives in the render graph; the layer carries only its data-source dimension mapping and placement."""

    id: auto
    lens: Lens
    x_dim: str | None
    y_dim: str | None
    intensity_dim: str | None
    z_dim: str | None
    t_dim: str | None

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        return obj.kind == enums.LayerKind.IMAGE.value

    @kante.django_field(description="The composable in-layer render graph, if this layer defines one")
    def render_graph(self, info: Info) -> LayerRenderGraph | None:
        if not self.render_graph:
            return None
        return LayerRenderGraphModel(**self.render_graph)


@kante.type(description="A constraint on a named dimension of a data ROI, with optional min, max and step")
class Constraint:
    """A constraint on a named dimension of a data ROI, with optional min, max and step"""

    dim: str
    min: int | None
    max: int | None
    step: int | None


@kante.django_type(
    models.DataRoi,
    filters=filters.DataRoiFilter,
    ordering=order.DataRoiOrder,
    pagination=True,
    description="A region of interest in a data array, described by its vectors and per-dimension constraints",
)
class DataRoi:
    """A region of interest in a data array, described by its vectors and per-dimension constraints"""

    id: auto
    dataset: ADataset
    name: auto
    description: str | None
    kind: enums.RoiKind
    x_dim: str
    y_dim: str
    z_dim: str | None
    vectors: list[list[float]]
    constraints: list[Constraint]
    provenance_entries: List["ProvenanceEntry"] = kante.django_field(description="Provenance entries for this data ROI")


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
    mesh: Mesh
    material_color: list[int] | None
    wireframe: bool

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        return obj.kind == enums.LayerKind.MESH.value
