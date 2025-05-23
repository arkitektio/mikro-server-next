from pydantic import BaseModel
import strawberry
import strawberry_django
from strawberry import auto
from typing import List, Optional, Annotated, Union, cast
import strawberry_django
from core import models, scalars, filters, enums
from django.contrib.auth import get_user_model
from kante.types import Info
import datetime
from asgiref.sync import sync_to_async
from itertools import chain
from enum import Enum
from core.datalayer import get_current_datalayer
from core.render.objects import models as rmodels
from strawberry.experimental import pydantic
from typing import Union
from strawberry import LazyType
from core.duck import get_current_duck
from authentikate.strawberry.types import Client, User
from koherent.strawberry.types import ProvenanceEntry


@strawberry.type(description="Temporary Credentials for a file upload that can be used by a Client (e.g. in a python datalayer)")
class Credentials:
    """Temporary Credentials for a a file upload."""

    status: str
    access_key: str
    secret_key: str
    session_token: str
    datalayer: str
    bucket: str
    key: str
    store: str


@strawberry.type(description="Temporary Credentials for a file upload that can be used by a Client (e.g. in a python datalayer)")
class PresignedPostCredentials:
    """Temporary Credentials for a a file upload."""

    key: str
    x_amz_algorithm: str
    x_amz_credential: str
    x_amz_date: str
    x_amz_signature: str
    policy: str
    datalayer: str
    bucket: str
    store: str


@strawberry.type(description="Temporary Credentials for a file download that can be used by a Client (e.g. in a python datalayer)")
class AccessCredentials:
    """Temporary Credentials for a a file upload."""

    access_key: str
    secret_key: str
    session_token: str
    bucket: str
    key: str
    path: str


@strawberry_django.type(
    models.ViewCollection,
    filters=filters.ImageFilter,
    order=filters.ImageOrder,
    pagination=True,
)
class ViewCollection:
    """A colletion of views.

    View collections are use to provide overarching views on your data,
    that are not bound to a specific image. For example, you can create
    a view collection that includes all middle z views of all images with
    a certain tag.

    View collections are a pure metadata construct and will not map to
    oredering of binary data.


    """

    id: auto
    name: auto
    views: List["View"]
    provenance_entries: List["ProvenanceEntry"] = strawberry_django.field(description="Provenance entries for this camera")
    affine_transformation_views: List["AffineTransformationView"]
    label_views: List["LabelView"]
    channel_views: List["ChannelView"]


@strawberry.enum
class ViewKind(str, Enum):
    """The kind of view.

    Views can be of different kinds. For example, a view can be a label view
    that will map a labeleling agent (e.g. an antibody) to a specific image channel.

    Depending on the kind of view, different fields will be available.

    """

    CHANNEL = "channel_views"
    LABEL = "label_views"
    AFFINE_TRANSFORMATION = "affine_transformation_views"
    TIMEPOINT = "timepoint_views"
    OPTICS = "optics_views"
    HISTOGRAM = "histogram_views"


@strawberry.enum
class AccessorKind(str, Enum):
    """The kind of accessors.

    Accessors can be of different kinds. For example, an accessor can be a label accessor
    that will map a labeleling agent (e.g. an antibody) to a specific image channel.

    """

    LABEL = "label_accessors"
    IMAGE = "image_accessors"


@strawberry.enum
class RenderKind(str, Enum):
    """The kind of render.

    Renders can be of different kinds. For example, a render can be a snapshot
    that will map a specific image to a specific timepoint. Or a render can be
    a video that will render a 5D image to a 4D video.
    """

    VIDEO = "videos"
    SNAPSHOT = "snapshot"


@strawberry_django.type(models.ZarrStore)
class ZarrStore:
    """Zarr Store.

    A ZarrStore is a store that contains a Zarr dataset on a connected
    S3 compatible storage backend. The store will contain the path to the
    dataset in the corresponding bucket.

    Importantly to retrieve the data, you will need to ask this API for
    temporary credentials to access the data. This is an additional step
    and is required to ensure that the data is only accessible to authorized
    users.

    """

    id: auto
    path: str | None = strawberry.field(description="The path to the data. Relative to the bucket.")
    shape: List[int] | None = strawberry.field(description="The shape of the data.")
    dtype: str | None = strawberry.field(description="The dtype of the data.")
    bucket: str = strawberry.field(description="The bucket where the data is stored.")
    key: str = strawberry.field(description="The key where the data is stored.")
    chunks: List[int] | None = strawberry.field(description="The chunks of the data.")
    populated: bool = strawberry.field(description="Whether the zarr store was populated (e.g. was a dataset created).")
    version: str = strawberry.field(description="The version of the zarr store (e.g. the version of the dataset).")


@strawberry_django.type(models.ParquetStore)
class ParquetStore:
    id: auto
    path: str
    bucket: str
    key: str


@strawberry_django.type(models.BigFileStore)
class BigFileStore:
    id: auto
    path: str
    bucket: str
    key: str
    filename: str

    @strawberry.field()
    def presigned_url(self, info: Info) -> str:
        datalayer = get_current_datalayer()
        return cast(models.BigFileStore, self).get_presigned_url(info, datalayer=datalayer)


@strawberry_django.type(models.MediaStore)
class MediaStore:
    id: auto
    path: str
    bucket: str
    key: str

    @strawberry_django.field()
    def presigned_url(self, info: Info, host: str | None = None) -> str:
        datalayer = get_current_datalayer()
        return cast(models.MediaStore, self).get_presigned_url(info, datalayer=datalayer, host=host)


@strawberry_django.type(models.MeshStore)
class MeshStore:
    id: auto
    path: str
    bucket: str
    key: str

    @strawberry_django.field()
    def presigned_url(self, info: Info, host: str | None = None) -> str:
        datalayer = get_current_datalayer()
        return cast(models.MeshStore, self).get_presigned_url(info, datalayer=datalayer, host=host)


@strawberry_django.interface(models.Render)
class Render:
    created_at: datetime.datetime
    creator: User | None


@strawberry_django.type(models.Snapshot, filters=filters.SnapshotFilter, pagination=True)
class Snapshot(Render):
    id: auto
    store: MediaStore
    name: str


@strawberry_django.type(models.Video, pagination=True)
class Video(Render):
    id: auto
    store: MediaStore
    thumbnail: MediaStore


@strawberry_django.type(models.Experiment, filters=filters.ExperimentFilter, pagination=True)
class Experiment:
    id: auto
    name: str
    description: str | None
    provenance_entries: List["ProvenanceEntry"] = strawberry_django.field(description="Provenance entries for this camera")
    created_at: datetime.datetime
    creator: User | None


@strawberry.type(description="A cell of a table")
class TableCell:
    id: strawberry.ID
    table: "Table"
    row_id: int
    column_id: int
    value: scalars.Any

    @strawberry_django.field()
    def column(self, info: Info) -> "TableColumn":
        return self.table.columns(info)[self.column_id]

    @strawberry_django.field()
    def name(self, info: Info) -> str:
        return self.table.columns(info)[self.column_id].name


@strawberry.type(description="A cell of a table")
class TableRow:
    id: strawberry.ID
    table: "Table"
    row_id: int

    @strawberry_django.field()
    def columns(self, info: Info) -> List["TableColumn"]:
        return self.table.columns(info)

    @strawberry_django.field()
    def values(self, info: Info) -> List[scalars.Any]:
        return self.table.rows(info, self.row_id)

    @strawberry_django.field()
    def name(self, info: Info) -> str:
        return f"Row {self.row_id}"


@strawberry.type(description="A column descriptor")
class TableColumn:
    _duckdb_column: strawberry.Private[list[str]]
    _table_id: strawberry.Private[str]

    @strawberry.field()
    def name(self) -> str:
        return self._duckdb_column[0]

    @strawberry.field()
    def type(self) -> enums.DuckDBDataType:
        return self._duckdb_column[1]

    @strawberry.field()
    def nullable(self) -> bool:
        return self._duckdb_column[2] == "YES"

    @strawberry.field()
    def key(self) -> str | None:
        return self._duckdb_column[3]

    @strawberry.field()
    def default(self) -> str | None:
        return self._duckdb_column[4]

    @strawberry_django.field()
    def accessors(
        self,
        info: Info,
        filters: filters.AccessorFilter | None = strawberry.UNSET,
        types: List[AccessorKind] | None = strawberry.UNSET,
    ) -> List["Accessor"]:
        if types is strawberry.UNSET:
            view_relations = [
                "label_accessors",
                "image_accessors",
            ]
        else:
            view_relations = [kind.value for kind in types]

        results = []

        base = models.Table.objects.get(id=self._table_id)

        for relation in view_relations:
            qs = getattr(base, relation).filter(keys__contains=[self._duckdb_column[0]]).all()

            # apply filters if defined
            if filters is not strawberry.UNSET:
                qs = strawberry_django.filters.apply(filters, qs, info)

            results.append(qs)

        return list(chain(*results))


@strawberry_django.type(models.Table, filters=filters.TableFilter, pagination=True)
class Table:
    id: auto
    name: auto
    origins: List["Image"] = strawberry_django.field()
    store: ParquetStore

    @strawberry_django.field()
    def columns(self, info: Info) -> List[TableColumn]:
        x = get_current_duck()

        sql = f"""
            DESCRIBE SELECT * FROM read_parquet('s3://{self.store.bucket}/{self.store.key}');
            """

        result = x.connection.sql(sql)

        return [TableColumn(_duckdb_column=x, _table_id=str(self.id)) for x in result.fetchall()]

    @strawberry_django.field()
    def rows(self, info: Info) -> List[scalars.MetricMap]:
        x = get_current_duck()

        sql = f"""
            SELECT * FROM {self.store.duckdb_string};
            """

        result = x.connection.sql(sql)

        return result.fetchall()

    @strawberry_django.field()
    def accessors(
        self,
        info: Info,
        filters: filters.AccessorFilter | None = strawberry.UNSET,
        types: List[AccessorKind] | None = strawberry.UNSET,
    ) -> List["Accessor"]:
        if types is strawberry.UNSET:
            view_relations = [
                "label_accessors",
                "image_accessors",
            ]
        else:
            view_relations = [kind.value for kind in types]

        results = []

        for relation in view_relations:
            qs = getattr(self, relation).all()

            # apply filters if defined
            if filters is not strawberry.UNSET:
                qs = strawberry_django.filters.apply(filters, qs, info)

            results.append(qs)

        return list(chain(*results))


@strawberry.type(description="A channel descriptor")
class ChannelInfo:
    _image: strawberry.Private[models.Image]
    _channel: strawberry.Private[int]

    @strawberry_django.field()
    def label(self, with_color_name: bool = False) -> str:
        name = f"Channel {self._channel}"

        if with_color_name:
            for i in self._image.rgb_views.filter(c_max__gt=self._channel, c_min__lte=self._channel).all():
                name += f" ({i.colormap_name})"

        return name


@strawberry.type(description="A channel descriptor")
class FrameInfo:
    _image: strawberry.Private[models.Image]
    _frame: strawberry.Private[int]

    @strawberry.field()
    def label(self) -> str:
        return f"Frame {self._frame}"


@strawberry.type(description="A channel descriptor")
class PlaneInfo:
    _image: strawberry.Private[models.Image]
    _plane: strawberry.Private[int]

    @strawberry.field()
    def label(self) -> str:
        return f"Plane {self._plane}"


@strawberry_django.type(models.File, filters=filters.FileFilter, pagination=True)
class File:
    id: auto
    name: auto
    origins: List["Image"] = strawberry_django.field()
    store: BigFileStore
    views: List["FileView"] = strawberry_django.field()
    provenance_entries: List["ProvenanceEntry"] = strawberry_django.field(description="Provenance entries for this camera")


@strawberry_django.type(models.Image, filters=filters.ImageFilter, order=filters.ImageOrder, pagination=True)
class Image:
    """An image.


    Images are the central data type in mikro. They represent a single 5D bioimage, which
    binary data is stored in a ZarrStore. Images can be annotated with views, which are
    subsets of the image, ordered by its coordinates. Views can be of different kinds, for
    example, a label view will map a labeling agent (e.g. an antibody) to a specific image
    channel. Depending on the kind of view, different fields will be available.

    Images also represent the primary data container for other models of the mikro data model.
    For example rois, metrics, renders, and generated tables are all bound to a specific image,
    and will share the lifecycle of the image.

    """

    id: auto
    name: auto = strawberry_django.field(description="The name of the image")
    store: ZarrStore = strawberry_django.field(description="The store where the image data is stored.")
    views: List["View"] = strawberry_django.field(description="The views of the image. (e.g. channel views, label views, etc.)")
    snapshots: List["Snapshot"] = strawberry_django.field(description="Associated snapshots")
    videos: List["Video"] = strawberry_django.field(description="Associated videos")
    dataset: Optional["Dataset"] = strawberry_django.field(description="The dataset this image belongs to")
    provenance_entries: List["ProvenanceEntry"] = strawberry_django.field(description="Provenance entries for this camera")
    affine_transformation_views: List["AffineTransformationView"] = strawberry_django.field(description="The affine transformation views describing position and scale")
    label_views: List["LabelView"] = strawberry_django.field(description="Label views mapping channels to labels")
    channel_views: List["ChannelView"] = strawberry_django.field(description="Channel views relating to acquisition channels")
    timepoint_views: List["TimepointView"] = strawberry_django.field(description="Timepoint views describing temporal relationships")
    optics_views: List["OpticsView"] = strawberry_django.field(description="Optics views describing acquisition settings")
    structure_views: List["StructureView"] = strawberry_django.field(description="Structure views relating other Arkitekt types to a subsection of the image")
    scale_views: List["ScaleView"] = strawberry_django.field(description="Scale views describing physical dimensions")
    histogram_views: List["HistogramView"] = strawberry_django.field(description="Histogram views describing pixel value distribution")

    created_at: datetime.datetime = strawberry_django.field(description="When this image was created")
    creator: User | None = strawberry_django.field(description="Who created this image")
    rgb_contexts: List["RGBContext"] = strawberry_django.field(description="RGB rendering contexts")
    derived_scale_views: List["ScaleView"] = strawberry_django.field(description="Scale views derived from this image")
    derived_views: List["DerivedView"] = strawberry_django.field(description="Views derived from this image")
    roi_views: List["ROIView"] = strawberry_django.field(description="Region of interest views")
    file_views: List["FileView"] = strawberry_django.field(description="File views relating to source files")
    pixel_views: List["PixelView"] = strawberry_django.field(description="Pixel views describing pixel value semantics")
    derived_from_views: List["DerivedView"] = strawberry_django.field(description="Views this image was derived from")

    @strawberry_django.field(description="The channels of this image")
    def channels(self, info: Info) -> List["ChannelInfo"]:
        return [ChannelInfo(_image=self, _channel=i) for i in range(0, self.store.shape[0])]

    @strawberry_django.field(description="The channels of this image")
    def frames(self, info: Info) -> List["FrameInfo"]:
        return [FrameInfo(_image=self, _frame=i) for i in range(0, self.store.shape[1])]

    @strawberry_django.field(description="The channels of this image")
    def planes(self, info: Info) -> List["PlaneInfo"]:
        return [PlaneInfo(_image=self, _plane=i) for i in range(0, self.store.shape[2])]

    @strawberry_django.field(description="The latest snapshot of this image")
    def latest_snapshot(self, info: Info) -> Optional["Snapshot"]:
        return cast(models.Image, self).snapshots.order_by("-created_at").first()

    @strawberry_django.field(description="Is this image pinned by the current user")
    def pinned(self, info: Info) -> bool:
        return cast(models.Image, self).pinned_by.filter(id=info.context.request.user.id).exists()

    @strawberry_django.field(description="The tags of this image")
    def tags(self, info: Info) -> list[str]:
        return cast(models.Image, self).tags.slugs()

    @strawberry_django.field(description="All views of this image")
    def views(
        self,
        info: Info,
        filters: Annotated[
            filters.ViewFilter | None,
            strawberry.argument(description="A filter to selected the subset of views"),
        ] = strawberry.UNSET,
        types: List[ViewKind] | None = strawberry.UNSET,
    ) -> List["View"]:
        if types is strawberry.UNSET:
            view_relations = [
                "affine_transformation_views",
                "channel_views",
                "timepoint_views",
                "optics_views",
                "label_views",
                "rgb_views",
                "wellposition_views",
                "continousscan_views",
                "acquisition_views",
                "structure_views",
                "scale_views",
                "roi_views",
                "file_views",
                "derived_views",
                "histogram_views",
            ]
        else:
            view_relations = [kind.value for kind in types]

        results = []

        for relation in view_relations:
            qs = getattr(self, relation).all()

            # apply filters if defined
            if filters is not strawberry.UNSET:
                qs = strawberry_django.filters.apply(filters, qs, info)

            results.append(qs)

        return list(chain(*results))

    @strawberry_django.field()
    def renders(
        self,
        info: Info,
        filters: filters.ViewFilter | None = strawberry.UNSET,
        types: List[RenderKind] | None = strawberry.UNSET,
    ) -> List["Render"]:
        if types is strawberry.UNSET:
            view_relations = [
                "snapshots",
                "videos",
            ]
        else:
            view_relations = [kind.value for kind in types]

        results = []

        for relation in view_relations:
            qs = getattr(self, relation).all()

            # apply filters if defined
            if filters is not strawberry.UNSET:
                qs = strawberry_django.filters.apply(filters, qs, info)

            results.append(qs)

        return list(chain(*results))

    @strawberry_django.field()
    def rois(
        self,
        info: Info,
        filters: filters.ROIFilter | None = strawberry.UNSET,
    ) -> List["ROI"]:
        qs = self.rois.all()

        # apply filters if defined
        if filters is not strawberry.UNSET:
            qs = strawberry_django.filters.apply(filters, qs, info)

        return qs


@strawberry_django.type(models.Dataset, filters=filters.DatasetFilter, pagination=True)
class Dataset:
    id: auto
    images: List["Image"]
    files: List["File"]
    parent: Optional["Dataset"]
    children: List["Dataset"]
    description: str | None
    name: str
    provenance_entries: List["ProvenanceEntry"] = strawberry_django.field(description="Provenance entries for this camera")
    is_default: bool
    created_at: datetime.datetime
    creator: User | None

    @strawberry_django.field()
    def pinned(self, info: Info) -> bool:
        return cast(models.Dataset, self).pinned_by.filter(id=info.context.request.user.id).exists()

    @strawberry_django.field()
    def tags(self, info: Info) -> list[str]:
        return cast(models.Image, self).tags.slugs()


@strawberry_django.type(models.Stage, filters=filters.StageFilter, pagination=True)
class Stage:
    id: auto
    affine_views: List["AffineTransformationView"]
    description: str | None
    name: str
    provenance_entries: List["ProvenanceEntry"] = strawberry_django.field(description="Provenance entries for this camera")

    @strawberry_django.field()
    def pinned(self, info: Info) -> bool:
        return cast(models.Image, self).pinned_by.filter(id=info.context.request.user.id).exists()


@strawberry_django.type(models.Era, filters=filters.EraFilter, pagination=True)
class Era:
    id: auto
    begin: auto
    views: List["TimepointView"]
    name: str
    provenance_entries: List["ProvenanceEntry"] = strawberry_django.field(description="Provenance entries for this camera")


@strawberry_django.type(models.Mesh, filters=filters.MeshFilter, pagination=True)
class Mesh:
    id: auto
    name: str
    store: MeshStore


OtherItem = Annotated[Union[Dataset, Image], strawberry.union("OtherItem")]


@strawberry_django.type(models.Camera, fields="__all__")
class Camera:
    id: auto
    name: auto
    serial_number: auto
    views: List["OpticsView"]
    model: auto
    bit_depth: auto
    pixel_size_x: scalars.Micrometers | None
    pixel_size_y: scalars.Micrometers | None
    sensor_size_x: int | None
    sensor_size_y: int | None
    manufacturer: str | None
    provenance_entries: List["ProvenanceEntry"] = strawberry_django.field(description="Provenance entries for this camera")


@strawberry_django.type(models.Objective, fields="__all__")
class Objective:
    id: auto
    name: auto
    serial_number: auto
    na: float | None
    magnification: float | None
    immersion: auto
    views: List["OpticsView"]


@strawberry_django.type(models.Channel, fields="__all__")
class Channel:
    id: auto
    views: List["ChannelView"]


@strawberry_django.type(
    models.MultiWellPlate,
    filters=filters.MultiWellPlateFilter,
    pagination=True,
    fields="__all__",
)
class MultiWellPlate:
    id: auto
    views: List["WellPositionView"]


@strawberry_django.type(models.Instrument, fields="__all__")
class Instrument:
    id: auto
    name: auto
    model: auto
    serial_number: auto
    views: List["OpticsView"]


class Slice:
    min: int
    max: int


def min_max_to_accessor(min, max):
    if min is None:
        min = ""
    if max is None:
        max = ""
    return f"{min}:{max}"


@strawberry_django.interface(models.View)
class View:
    """A view is a subset of an image."""

    image: "Image"
    z_min: int | None = None
    z_max: int | None = None
    x_min: int | None = None
    x_max: int | None = None
    y_min: int | None = None
    y_max: int | None = None
    t_min: int | None = None
    t_max: int | None = None
    c_min: int | None = None
    c_max: int | None = None
    is_global: bool

    @strawberry_django.field(description="The accessor")
    def accessor(self) -> List[str]:
        z_accessor = min_max_to_accessor(self.z_min, self.z_max)
        t_accessor = min_max_to_accessor(self.t_min, self.t_max)
        c_accessor = min_max_to_accessor(self.c_min, self.c_max)
        x_accessor = min_max_to_accessor(self.x_min, self.x_max)
        y_accessor = min_max_to_accessor(self.y_min, self.y_max)

        return [c_accessor, t_accessor, z_accessor, x_accessor, y_accessor]

    @strawberry_django.field(description="All views of this image")
    def congruent_views(
        self,
        info: Info,
        filters: Annotated[
            filters.ViewFilter | None,
            strawberry.argument(description="A filter to selected the subset of views"),
        ] = strawberry.UNSET,
        types: List[ViewKind] | None = strawberry.UNSET,
    ) -> List["View"]:
        image = self.image

        if types is strawberry.UNSET:
            view_relations = [
                "affine_transformation_views",
                "channel_views",
                "timepoint_views",
                "optics_views",
                "label_views",
                "rgb_views",
                "wellposition_views",
                "continousscan_views",
                "acquisition_views",
                "structure_views",
                "scale_views",
                "roi_views",
                "file_views",
                "derived_views",
                "histogram_views",
            ]
        else:
            view_relations = [kind.value for kind in types]

        results = []

        for relation in view_relations:
            print("Searching for", relation, "with", self.c_min, self.c_max, self.t_min, self.t_max, self.z_min, self.z_max, self.x_min, self.x_max, self.y_min, self.y_max)
            qs = getattr(image, relation).filter(c_min=self.c_min, c_max=self.c_max, t_min=self.t_min, t_max=self.t_max, z_min=self.z_min, z_max=self.z_max, x_min=self.x_min, x_max=self.x_max, y_min=self.y_min, y_max=self.y_max).all()

            # apply filters if defined
            if filters is not strawberry.UNSET:
                qs = strawberry_django.filters.apply(filters, qs, info)

            results.append(qs)

        return list(chain(*results))


@strawberry_django.interface(models.Accessor)
class Accessor:
    id: strawberry.ID
    table: Table
    keys: list[str]
    min_index: int | None
    max_index: int | None


@strawberry_django.type(models.LabelAccessor)
class LabelAccessor(Accessor):
    id: auto
    pixel_view: "PixelView"


@strawberry_django.type(models.ImageAccessor)
class ImageAccessor(Accessor):
    id: auto
    pass


@strawberry_django.type(models.ChannelView)
class ChannelView(View):
    id: auto
    channel: Channel


@strawberry_django.type(models.RGBRenderContext, filters=filters.RGBContextFilter, pagination=True)
class RGBContext:
    id: auto
    name: str
    image: Image
    snapshots: List[Snapshot]
    views: List["RGBView"]
    blending: enums.Blending
    z: int
    t: int
    c: int

    @strawberry_django.field()
    def pinned(self, info: Info) -> bool:
        return cast(models.RGBRenderContext, self).pinned_by.filter(id=info.context.request.user.id).exists()


class OverlayModel(BaseModel):
    object: str
    identifier: str
    color: str
    x: int
    y: int


@pydantic.type(OverlayModel)
class Overlay:
    object: str
    identifier: str
    color: str
    x: int
    y: int


@strawberry_django.type(
    models.RenderTree,
    filters=filters.RenderTreeFilter,
    order=filters.RenderTreeOrder,
    pagination=True,
)
class RenderTree:
    id: auto
    name: str
    linked_contexts: list[RGBContext]


@strawberry_django.type(models.RGBView)
class RGBView(View):
    id: auto
    contexts: List[RGBContext]
    color_map: enums.ColorMap
    gamma: float | None
    contrast_limit_min: float | None
    contrast_limit_max: float | None
    rescale: bool
    active: bool
    base_color: list[int] | None

    @strawberry_django.field()
    def full_colour(self, info: Info, format: enums.ColorFormat | None = enums.ColorFormat.RGB) -> str:
        if format is None:
            format = enums.ColorFormat.RGB

        if format == enums.ColorFormat.RGB:
            if self.color_map == enums.ColorMap.RED:
                return "rgb(255,0,0)"
            if self.color_map == enums.ColorMap.GREEN:
                return "rgb(0,255,0)"
            if self.color_map == enums.ColorMap.BLUE:
                return "rgb(0,0,255)"

        return ""

    @strawberry_django.field()
    def name(self, info: Info, long: bool = False) -> str:
        if long:
            return f"{self.color_map} {self.gamma} {self.contrast_limit_min} {self.contrast_limit_max} {self.rescale}"
        return f"{self.color_map} ({self.c_min}:{self.c_max})"


@strawberry_django.type(models.LabelView)
class LabelView(View):
    """A label view.

    Label views are used to give a label to a specific image channel. For example, you can
    create a label view that maps an antibody to a specific image channel. This will allow
    you to easily identify the labeling agent in the image. However, label views can be used
    for other purposes as well. For example, you can use a label to mark a specific channel
    to be of poor quality. (e.g. "bad channel").

    """

    id: auto

    image: Image

    @strawberry_django.field()
    def label(self, info: Info) -> str:
        return self.label or "No Label"


@strawberry_django.type(models.ROIView)
class ROIView(View):
    """A label view.

    Label views are used to give a label to a specific image channel. For example, you can
    create a label view that maps an antibody to a specific image channel. This will allow
    you to easily identify the labeling agent in the image. However, label views can be used
    for other purposes as well. For example, you can use a label to mark a specific channel
    to be of poor quality. (e.g. "bad channel").

    """

    id: auto

    image: Image
    roi: "ROI"


@strawberry_django.type(models.FileView)
class FileView(View):
    """A file view.

    File view establish a relationship between an image and a file. It is used to establish
    the this view of the image was originally part of a file, and to provide a link to the
    file that was used to create the image.

    Related Concepts:
        - TableViews: Table views establish a relationship between a table and an image. (i.e. when a table is generated from an image)

    """

    id: auto
    series_identifier: str | None = None
    image: Image
    file: "File"


@strawberry_django.type(models.HistogramView)
class HistogramView(View):
    """A file view.

    File view establish a relationship between an image and a file. It is used to establish
    the this view of the image was originally part of a file, and to provide a link to the
    file that was used to create the image.

    Related Concepts:
        - TableViews: Table views establish a relationship between a table and an image. (i.e. when a table is generated from an image)

    """

    id: auto
    image: Image
    bins: list[float]
    min: float
    max: float
    histogram: list[float]


@strawberry_django.type(models.DerivedView)
class DerivedView(View):
    """A  derived view.

    Derived views establish a processing relationship between two images. Within this relationship
    it is guarenteed that the derived view is derived from the origin image and shares the same
    coordinate system. This means that images can be trivially overlayed and compared.

    Attention:
    Importantly cropped or projected images are not derived views, as they do not share the same coordinate system.
    This means that cropped images cannot be trivially overlayed and compared, for this you would need to create a
    ROIView (mapping the cropped area or projected area to the original image).


    Biological Example:
        I.e. if you have a derived view that is a segmentation of an image, you can overlay the segmentation
        on the original image and compare the two. This is useful to validate the segmentation.

    Related Concepts:
        - RoiViews: RoiViews allow to establish a relationship between a region of interest and an image. (i.e when cropping an image)


    """

    id: auto
    image: Image
    origin_image: Image
    operation: str | None = None


@strawberry_django.type(models.TableView)
class TableView(View):
    """A  table view.

    A table view established that an image was generated from a table.


    Biological Example:
        -   You have a table that describes the localisations in Single Molecule Localization Microscopy (SMLM) data.
            You can establish a backlink from the image to the table to show that the image was generated from this table





    """

    id: auto
    image: Image
    table: Table
    operation: str | None = None


@strawberry_django.type(models.ScaleView)
class ScaleView(View):
    id: auto
    parent: "Image"
    scale_x: float
    scale_y: float
    scale_z: float
    scale_t: float
    scale_c: float


@strawberry_django.type(models.AcquisitionView)
class AcquisitionView(View):
    id: auto
    description: str | None
    acquired_at: datetime.datetime | None
    operator: User | None


@strawberry_django.type(models.OpticsView, filters=filters.OpticsViewFilter, pagination=True)
class OpticsView(View):
    """An optics view.

    Optics views describe the optics that were used to acquire the image. This includes
    the camera, the objective, and the instrument that were used to acquire the image.
    Often optics views are used to describe the acquisition settings of the image.

    """

    id: auto
    instrument: Instrument | None
    camera: Camera | None
    objective: Objective | None


@strawberry_django.type(models.StructureView, filters=filters.StructureViewFilter, pagination=True)
class StructureView(View):
    """A specimen view.

    Specimen Views describe what specific entity is portrayed. E.g. this could be
    a specific cell, a specific tissue, or a specific organism. Specimen views are
    used to give context to the image data and to provide a link to the biological
    entity that is portrayed in the image.

    """

    id: auto
    structure: scalars.StructureString


@strawberry_django.type(models.PixelView, filters=filters.PixelViewFilter, pagination=True)
class PixelView(View):
    """A pixel view.

    Pixel views give meaning to the **values** of the pixels in the image. Within a
    pixel view, you can map the pixel values through pixel labels. Importantly
    pixel values are only guarenteed to be unique within a pixel view. This means
    that the same pixel value can be mapped to different entities in different
    pixel views.

    E.g. if you are not tracking cells between different frames of an image (t) you
    and you want to map the pixel values to a specific cell, you will need to create
    a pixel view for each frame. This will allow you to map the pixel values to the
    correct cell in each frame.
    """

    id: auto
    labels: list["PixelLabel"]
    label_accessors: list["LabelAccessor"]


@strawberry_django.type(models.PixelLabel, filters=filters.PixelLabelFilter, pagination=True)
class PixelLabel:
    """A pixel label.

    Pixel labels are used to give meaning to the pixel values in the image. For example,
    you can create a pixel label that maps the pixel values to a specific entity (e.g.
    all values between 0 and 10 are mapped to a specific entitry (e.g. Cell 0 , Cell 1, etc.).
    or it can be used to map the pixel value to a specific expression (e.g. all 0 values are
    considered to be "background").

    Pixel labels only are true for a specific pixel view of an image. See PixelView for more
    information.

    """

    id: auto
    view: PixelView
    value: int


@strawberry_django.type(models.WellPositionView, filters=filters.WellPositionViewFilter, pagination=True)
class WellPositionView(View):
    """A well position view.

    Well position views are used to map the well position of a multi well plate to the
    image. This is useful if you are using a multi well plate to acquire images and you
    want to map the well position to the image data. This can be useful to track the
    position of the image data in the multi well plate.




    """

    id: auto
    well: MultiWellPlate | None
    row: int | None
    column: int | None


@strawberry_django.type(models.ContinousScanView, filters=filters.ContinousScanViewFilter, pagination=True)
class ContinousScanView(View):
    id: auto
    direction: enums.ScanDirection


@strawberry_django.type(models.TimepointView, filters=filters.TimepointViewFilter, pagination=True)
class TimepointView(View):
    id: auto
    era: Era
    ms_since_start: scalars.Milliseconds | None
    index_since_start: int | None


@strawberry_django.type(
    models.AffineTransformationView,
    filters=filters.AffineTransformationViewFilter,
    pagination=True,
)
class AffineTransformationView(View):
    id: auto
    stage: Stage
    affine_matrix: scalars.FourByFourMatrix

    @strawberry_django.field()
    def pixel_size(self, info: Info) -> scalars.ThreeDVector:
        if self.kind == "AFFINE":
            return [self.matrix[0][0], self.matrix[1][1], self.matrix[2][2]]
        raise NotImplementedError("Only affine transformations are supported")

    @strawberry_django.field()
    def pixel_size_x(self, info: Info) -> scalars.Micrometers:
        if self.kind == "AFFINE":
            return self.matrix[0][0]
        raise NotImplementedError("Only affine transformations are supported")

    @strawberry_django.field()
    def pixel_size_y(self, info: Info) -> scalars.Micrometers:
        if self.kind == "AFFINE":
            return self.matrix[1][1]
        raise NotImplementedError("Only affine transformations are supported")

    @strawberry_django.field()
    def position(self, info: Info) -> scalars.ThreeDVector:
        if self.kind == "AFFINE":
            return [self.matrix[0][3], self.matrix[1][3], self.matrix[2][3]]
        raise NotImplementedError("Only affine transformations are supported")


@strawberry_django.type(models.ROI, filters=filters.ROIFilter, order=filters.ROIOrder, pagination=True)
class ROI:
    """A region of interest."""

    id: auto
    image: "Image"
    kind: enums.RoiKind
    vectors: list[scalars.FiveDVector]
    created_at: datetime.datetime
    creator: User | None
    provenance_entries: List["ProvenanceEntry"] = strawberry_django.field(description="Provenance entries for this camera")

    @strawberry_django.field()
    def pinned(self, info: Info) -> bool:
        return self.pinned_by.filter(id=info.context.request.user.id).exists()

    @strawberry_django.field()
    def name(self, info: Info) -> str:
        return self.kind
