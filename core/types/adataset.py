from strawberry import auto
from typing import List
from core import models, scalars, filters, enums
from kante.types import Info
from lightpath.objects.types import LightpathGraph
from lightpath.objects.models import LightpathGraphModel
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
    layers: List["Layer"] = kante.django_field(description="The layers placed in this scene")
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


@kante.django_type(
    models.Layer,
    filters=filters.LayerFilter,
    ordering=order.LayerOrder,
    pagination=True,
    description="The placement of a lens in a scene, including rendering settings such as colormap, contrast limits and an affine transformation matrix",
)
class Layer:
    """The placement of a lens in a scene, including rendering settings such as colormap, contrast limits and an affine transformation matrix"""

    id: auto
    lens: Lens
    scene: Scene
    status: auto
    affine_matrix: scalars.FourByFourMatrix | None
    clim_min: float | None
    clim_max: float | None
    color: list[int] | None
    colormap: enums.ColorMap | None
    x_dim: str
    y_dim: str
    intensity_dim: str
    z_dim: str | None
    t_dim: str | None


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
