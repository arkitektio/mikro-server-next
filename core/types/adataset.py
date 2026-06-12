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


@kante.pydantic_type(base_models.DimDescriptor)
class DimDescriptor:
    key: str
    size: int
    kind: enums.DimensionKind


@kante.django_type(models.ADataset, filters=filters.ADatasetFilter, ordering=order.ADatasetOrder, pagination=True)
class ADataset:
    id: auto
    name: auto
    description: str | None
    dims: list[str]
    created_through: Task | None = kante.django_field(description="The task this dataset was created through, if any")
    created_through_by: User | None = kante.django_field(description="The assigner of the creating task, if any")
    data_arrays: List["DataArray"] = kante.django_field(description="Provenance entries for this camera")

    @kante.django_field()
    def dim_descriptors(self, info: Info) -> List[DimDescriptor]:
        return self.dim_descriptors_list


@kante.django_type(models.DataArray, filters=filters.DataArrayFilter, ordering=order.DataArrayOrder, pagination=True)
class DataArray:
    id: auto
    store: ZarrStore
    shape: list[int]
    chunk_shape: list[int]
    scale_factors: list[float] | None
    level: int


@kante.django_type(models.OptikitState, filters=filters.OptikitStateFilter, pagination=True)
class OptikitState:
    id: auto
    store: ZarrStore
    shape: list[int]
    chunk_shape: list[int]
    dims: list[str]


@kante.django_type(models.ValueHistogram, filters=filters.ValueHistogramFilter, pagination=True)
class ValueHistogram:
    id: auto
    p1: float | None
    p99: float | None
    histogram: list[float]
    bins: list[float]
    min: float | None
    max: float | None


@kante.django_type(models.LightPath, filters=filters.LightPathFilter, pagination=True)
class LightPath:
    id: auto

    @kante.django_field()
    def graph(self, info: Info) -> LightpathGraph:
        return LightpathGraphModel(**self.graph)


@kante.django_type(models.ChannelLabel, filters=filters.ChannelLabelFilter, pagination=True)
class ChannelLabel:
    id: auto
    label: str


@kante.django_type(models.CoordinateAnchor, filters=filters.CoordinateAnchorFilter, pagination=True)
class CoordinateAnchor:
    id: auto
    store: ZarrStore
    shape: list[int]
    chunk_shape: list[int]
    dims: list[str]
    optikit_state: OptikitState | None
    value_histogram: ValueHistogram | None
    channel_label: ChannelLabel | None
    light_graph: LightPath | None


@kante.django_type(models.OmeMetadata, filters=filters.OmeMetadataFilter, pagination=True)
class OmeMetadata:
    id: auto
    store: ZarrStore
    shape: list[int]
    chunk_shape: list[int]
    dims: list[str]


@kante.django_type(models.OmePlaneMetadata, filters=filters.OmePlaneMetadataFilter, pagination=True)
class OmePlaneMetaData:
    id: auto
    store: ZarrStore
    shape: list[int]
    chunk_shape: list[int]
    dims: list[str]


@kante.django_type(models.Scene, filters=filters.SceneFilter, pagination=True, ordering=order.SceneOrder)
class Scene:
    id: auto
    name: auto
    layers: List["Layer"] = kante.django_field(description="Provenance entries for this camera")
    spatial_unit: enums.SpatialUnit
    temporal_unit: enums.TemporalUnit


@kante.pydantic_type(base_models.SliceModel)
class Slice:
    dim: str
    start: int | None
    stop: int | None
    step: int | None


@kante.django_type(models.Lens, filters=filters.LensFilter, ordering=order.LensOrder, pagination=True)
class Lens:
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


@kante.django_type(models.Layer, filters=filters.LayerFilter, ordering=order.LayerOrder, pagination=True)
class Layer:
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


@kante.type
class Constraint:
    dim: str
    min: int | None
    max: int | None
    step: int | None


@kante.django_type(models.DataRoi, filters=filters.DataRoiFilter, ordering=order.DataRoiOrder, pagination=True)
class DataRoi:
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
    provenance_entries: List["ProvenanceEntry"] = kante.django_field(description="Provenance entries for this camera")
