import strawberry
import strawberry.django
from strawberry import auto
from typing import List, Optional, Annotated, Union, cast
import strawberry_django
from core import models, scalars, filters, enums
from django.contrib.auth import get_user_model
from koherent.models import AppHistoryModel
from authentikate.models import App as AppModel
from kante.types import Info
import datetime

from itertools import chain
from enum import Enum

from core.datalayer import get_current_datalayer


@strawberry_django.type(AppModel, description="An app.")
class App:
    id: auto
    name: str
    client_id: str

@strawberry_django.type(get_user_model(), description="A user.")
class User:
    id: auto
    sub: str
    username: str
    email: str
    password: str


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
    """ A colletion of views.
    
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
    history: List["History"]
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


@strawberry_django.type(models.ParquetStore)
class ParquetStore:
    id: auto
    path: str
    bucket: str
    key: str


@strawberry.django.type(models.BigFileStore)
class BigFileStore:
    id: auto
    path: str
    bucket: str
    key: str

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

    @strawberry.field()
    def presigned_url(self, info: Info, host: str | None = None) -> str:
        datalayer = get_current_datalayer()
        return cast(models.MediaStore, self).get_presigned_url(info, datalayer=datalayer, host=host)


@strawberry_django.interface(models.Render)
class Render:
    created_at: datetime.datetime
    creator: User | None


@strawberry_django.type(
    models.Snapshot, filters=filters.SnapshotFilter, pagination=True
)
class Snapshot(Render):
    id: auto
    store: MediaStore
    name: str


@strawberry_django.type(models.Video, pagination=True)
class Video(Render):
    id: auto
    store: MediaStore
    thumbnail: MediaStore


@strawberry_django.interface(models.ImageMetric)
class ImageMetric:
    image: "Image"
    created_at: datetime.datetime
    creator: User | None


@strawberry_django.interface(models.IntMetric)
class IntMetric:
    value: int


@strawberry_django.type(models.ImageIntMetric, pagination=True)
class ImageIntMetric(ImageMetric, IntMetric):
    id: auto


@strawberry_django.type(models.Table, pagination=True)
class Table:
    id: auto
    name: auto
    origins: List["Image"] = strawberry.django.field()
    store: ParquetStore


@strawberry_django.type(models.File, filters=filters.FileFilter, pagination=True)
class File:
    id: auto
    name: auto
    origins: List["Image"] = strawberry.django.field()
    store: BigFileStore


@strawberry_django.type(
    models.Image, filters=filters.ImageFilter, order=filters.ImageOrder, pagination=True
)
class Image:
    """ An image.
    
    
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
    name: auto
    store: ZarrStore = strawberry_django.field(description="The store where the image data is stored.")
    views: List["View"] = strawberry_django.field(description="The views of the image. (e.g. channel views, label views, etc.)")
    snapshots: List["Snapshot"]
    videos: List["Video"]
    origins: List["Image"] = strawberry.django.field()
    file_origins: List["File"] = strawberry.django.field()
    roi_origins: List["ROI"] = strawberry.django.field()
    dataset: Optional["Dataset"]
    history: List["History"]
    affine_transformation_views: List["AffineTransformationView"] = strawberry_django.field(description="The affine transformation views of the image.")
    label_views: List["LabelView"]
    channel_views: List["ChannelView"]
    timepoint_views: List["TimepointView"]
    optics_views: List["OpticsView"]
    int_metrics: List["ImageIntMetric"]
    created_at: datetime.datetime
    creator: User | None

    @strawberry.django.field()
    def latest_snapshot(self, info: Info) -> Optional["Snapshot"]:
        return cast(models.Image, self).snapshots.order_by("-created_at").first()

    @strawberry.django.field()
    def pinned(self, info: Info) -> bool:
        return (
            cast(models.Image, self)
            .pinned_by.filter(id=info.context.request.user.id)
            .exists()
        )

    @strawberry.django.field()
    def tags(self, info: Info) -> list[str]:
        return cast(models.Image, self).tags.slugs()

    @strawberry.django.field()
    def metrics(
        self,
        info: Info,
        filters: filters.ViewFilter | None = strawberry.UNSET,
        types: List[RenderKind] | None = strawberry.UNSET,
    ) -> List["ImageMetric"]:
        if types is strawberry.UNSET:
            view_relations = ["int_metrics"]
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

    @strawberry.django.field()
    def views(
        self,
        info: Info,
        filters: filters.ViewFilter | None = strawberry.UNSET,
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

    @strawberry.django.field()
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

    @strawberry.django.field()
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
    children: List["Dataset"]
    description: str | None
    name: str
    history: List["History"]
    is_default: bool
    created_at: datetime.datetime
    creator: User | None

    @strawberry.django.field()
    def pinned(self, info: Info) -> bool:
        return (
            cast(models.Dataset, self)
            .pinned_by.filter(id=info.context.request.user.id)
            .exists()
        )

    @strawberry.django.field()
    def tags(self, info: Info) -> list[str]:
        return cast(models.Image, self).tags.slugs()


@strawberry_django.type(models.Stage, filters=filters.StageFilter, pagination=True)
class Stage:
    id: auto
    affine_views: List["AffineTransformationView"]
    description: str | None
    name: str
    history: List["History"]

    @strawberry.django.field()
    def pinned(self, info: Info) -> bool:
        return (
            cast(models.Image, self)
            .pinned_by.filter(id=info.context.request.user.id)
            .exists()
        )


@strawberry_django.type(models.Era, filters=filters.EraFilter, pagination=True)
class Era:
    id: auto
    begin: auto
    views: List["TimepointView"]
    name: str
    history: List["History"]


@strawberry_django.type(
    models.Fluorophore, filters=filters.FluorophoreFilter, pagination=True
)
class Fluorophore:
    id: auto
    name: str
    views: List["LabelView"]
    emission_wavelength: scalars.Micrometers | None
    excitation_wavelength: scalars.Micrometers | None
    history: List["History"]


@strawberry_django.type(
    models.Antibody, filters=filters.AntibodyFilter, pagination=True
)
class Antibody:
    id: auto
    name: str
    epitope: str | None
    primary_views: List["LabelView"]
    secondary_views: List["LabelView"]
    history: List["History"]


@strawberry.enum
class HistoryKind(str, Enum):
    CREATE = "+"
    UPDATE = "~"
    DELETE = "-"


@strawberry.type()
class ModelChange:
    field: str
    old_value: str
    new_value: str


@strawberry_django.type(AppHistoryModel, pagination=True)
class History:
    app: App | None

    @strawberry.django.field()
    def user(self, info: Info) -> User | None:
        return self.history_user

    @strawberry.django.field()
    def kind(self, info: Info) -> HistoryKind:
        return self.history_type

    @strawberry.django.field()
    def date(self, info: Info) -> datetime.datetime:
        return self.history_date

    @strawberry.django.field()
    def during(self, info: Info) -> str | None:
        return self.assignation_id

    @strawberry.django.field()
    def id(self, info: Info) -> strawberry.ID:
        return self.history_id

    @strawberry.django.field()
    def effective_changes(self, info: Info) -> list[ModelChange]:
        new_record, old_record = self, self.prev_record

        changes = []
        if old_record is None:
            return changes

        delta = new_record.diff_against(old_record)
        for change in delta.changes:
            changes.append(
                ModelChange(
                    field=change.field, old_value=change.old, new_value=change.new
                )
            )

        return changes


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
    history: List["History"]


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


@strawberry_django.type(models.MultiWellPlate, filters=filters.MultiWellPlateFilter, pagination=True, fields="__all__")
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

    @strawberry.django.field(description="The accessor")
    def accessor(self) -> List[str]:
        z_accessor = min_max_to_accessor(self.z_min, self.z_max)
        t_accessor = min_max_to_accessor(self.t_min, self.t_max)
        c_accessor = min_max_to_accessor(self.c_min, self.c_max)
        x_accessor = min_max_to_accessor(self.x_min, self.x_max)
        y_accessor = min_max_to_accessor(self.y_min, self.y_max)

        return [c_accessor, t_accessor, z_accessor, x_accessor, y_accessor]


@strawberry_django.type(models.ChannelView)
class ChannelView(View):
    id: auto
    channel: Channel


@strawberry_django.type(
    models.RGBRenderContext, filters=filters.RGBContextFilter, pagination=True
)
class RGBContext:
    id: auto
    name: str
    views: List["RGBView"]

    @strawberry.django.field()
    def pinned(self, info: Info) -> bool:
        return (
            cast(models.RGBContext, self)
            .pinned_by.filter(id=info.context.request.user.id)
            .exists()
        )


@strawberry_django.type(models.RGBView)
class RGBView(View):
    id: auto
    context: RGBContext
    r_scale: float
    g_scale: float
    b_scale: float

    @strawberry.django.field()
    def full_colour(
        self, info: Info, format: enums.ColorFormat | None = enums.ColorFormat.RGB
    ) -> str:
        if format is None:
            format = enums.ColorFormat.RGB

        if format == enums.ColorFormat.RGB:
            return (
                f"rgb({self.r_scale * 255},{self.g_scale * 255},{self.b_scale * 255})"
            )

        return ""


@strawberry_django.type(models.LabelView)
class LabelView(View):
    id: auto
    fluorophore: Fluorophore | None
    primary_antibody: Antibody | None
    secondary_antibody: Antibody | None
    acquisition_mode: str | None


@strawberry_django.type(models.AcquisitionView)
class AcquisitionView(View):
    id: auto
    description: str | None
    acquired_at: datetime.datetime | None
    operator: User | None



@strawberry_django.type(
    models.OpticsView, filters=filters.OpticsViewFilter, pagination=True
)
class OpticsView(View):
    id: auto
    instrument: Instrument | None
    camera: Camera | None
    objective: Objective | None


@strawberry_django.type(
    models.WellPositionView, filters=filters.WellPositionViewFilter, pagination=True
)
class WellPositionView(View):
    id: auto
    well: MultiWellPlate | None
    row: int | None
    column: int | None


@strawberry_django.type(
    models.ContinousScanView, filters=filters.ContinousScanViewFilter, pagination=True
)
class ContinousScanView(View):
    id: auto
    direction: enums.ScanDirection


@strawberry_django.type(
    models.TimepointView, filters=filters.TimepointViewFilter, pagination=True
)
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

    @strawberry.django.field()
    def pixel_size(self, info: Info) -> scalars.ThreeDVector:
        if self.kind == "AFFINE":
            return [self.matrix[0][0], self.matrix[1][1], self.matrix[2][2]]
        raise NotImplementedError("Only affine transformations are supported")

    @strawberry.django.field()
    def pixel_size_x(self, info: Info) -> scalars.Micrometers:
        if self.kind == "AFFINE":
            return self.matrix[0][0]
        raise NotImplementedError("Only affine transformations are supported")

    @strawberry.django.field()
    def pixel_size_y(self, info: Info) -> scalars.Micrometers:
        if self.kind == "AFFINE":
            return self.matrix[1][1]
        raise NotImplementedError("Only affine transformations are supported")

    @strawberry.django.field()
    def position(self, info: Info) -> scalars.ThreeDVector:
        if self.kind == "AFFINE":
            return [self.matrix[0][3], self.matrix[1][3], self.matrix[2][3]]
        raise NotImplementedError("Only affine transformations are supported")


@strawberry_django.interface(models.ROI)
class ROI:
    id: auto
    image: "Image"
    vectors: scalars.FiveDVector


@strawberry_django.type(models.ROI)
class RectangleROI(ROI):
    width: int
    height: int
    depth: int


@strawberry_django.type(models.ROI)
class PathROI(ROI):
    pathLength: int
