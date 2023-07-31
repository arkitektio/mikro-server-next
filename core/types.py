import strawberry
import strawberry.django
from strawberry import auto
from typing import List, Optional, Annotated, Union
import strawberry_django
from kante import register_model
from core import models, scalars, filters, enums
from django.contrib.auth import get_user_model
from typing import Optional
from koherent.models import AppHistoryModel
from authentikate.types import App
from kante.types import Info
import datetime

from itertools import chain
from enum import Enum


@register_model(get_user_model())
class User:
    id: auto
    username: str
    email: str
    password: str


@strawberry.type()
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


@strawberry.type()
class AccessCredentials:
    """Temporary Credentials for a a file upload."""
    access_key: str
    secret_key: str
    session_token: str
    bucket: str
    key: str
    path: str




@register_model(
    models.ViewCollection,
    filters=filters.ImageFilter,
    order=filters.ImageOrder,
    pagination=True,
)
class ViewCollection:
    id: auto
    name: auto
    views: List["View"]
    history: List["History"]
    transformation_views: List["TransformationView"]
    label_views: List["LabelView"]
    channel_views: List["ChannelView"]


@strawberry.enum
class ViewKind(str, Enum):
    CHANNEL = "channel_views"
    LABEL = "label_views"
    TRANSFORMATION = "transformation_views"
    TIMEPOINT = "timepoint_views"
    OPTICS = "optics_views"

@register_model(models.ZarrStore)
class ZarrStore:
    id: auto
    path: str
    shape: List[int] | None
    dtype: str | None
    bucket: str
    key: str
    chunks: List[int] | None
    populated: bool


@register_model(models.ParquetStore)
class ParquetStore:
    id: auto
    path: str
    bucket: str
    key: str




@register_model(models.BigFileStore)
class BigFileStore:
    id: auto
    path: str
    bucket: str
    key: str


    @strawberry.field()
    def presigned_url(self, info: Info) -> str:
        return self.get_presigned_url(info)
    
@register_model(models.MediaStore)
class MediaStore:
    id: auto
    path: str
    bucket: str
    key: str


    @strawberry.field()
    def presigned_url(self, info: Info, host: str | None = None) -> str:
        return self.get_presigned_url(info, host=host)




@register_model(
    models.Thumbnail,  pagination=True
)
class Thumbnail:
    id: auto
    name: auto
    origins: List["Image"] = strawberry.django.field()
    store: MediaStore


@register_model(
    models.Table,  pagination=True
)
class Table:
    id: auto
    name: auto
    origins: List["Image"] = strawberry.django.field()
    store: ParquetStore




@register_model(
    models.File,  pagination=True
)
class File:
    id: auto
    name: auto
    origins: List["Image"] = strawberry.django.field()
    store: BigFileStore





@register_model(
    models.Image, filters=filters.ImageFilter, order=filters.ImageOrder, pagination=True
)
class Image:
    id: auto
    name: auto
    store: ZarrStore
    views: List["View"]
    origins: List["Image"] = strawberry.django.field()
    dataset: Optional["Dataset"]
    history: List["History"]
    transformation_views: List["TransformationView"]
    label_views: List["LabelView"]
    channel_views: List["ChannelView"]
    timepoint_views: List["TimepointView"]
    optics_views: List["OpticsView"]

    @strawberry.django.field()
    def views(
        self,
        info: Info,
        filters: filters.ViewFilter | None = strawberry.UNSET,
        types: List[ViewKind] | None = strawberry.UNSET,
    ) -> List["View"]:
        if types is strawberry.UNSET:
            view_relations = [
                "transformation_views",
                "channel_views",
                "timepoint_views",
                "optics_views",
                "label_views",
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
    ) -> List["View"]:
        qs = self.rois.all()

        # apply filters if defined
        if filters is not strawberry.UNSET:
            qs = strawberry_django.filters.apply(filters, qs, info)

        return qs


@register_model(models.Dataset, filters=filters.DatasetFilter, pagination=True)
class Dataset:
    id: auto
    images: List["Image"]
    description: str | None
    name: str
    history: List["History"]


@register_model(models.Stage, filters=filters.StageFilter, pagination=True)
class Stage:
    id: auto
    views: List["TransformationView"]
    description: str | None
    name: str
    history: List["History"]


@register_model(models.Era, filters=filters.EraFilter, pagination=True)
class Era:
    id: auto
    begin: auto
    views: List["TimepointView"]
    name: str
    history: List["History"]


@register_model(models.Fluorophore, filters=filters.FluorophoreFilter, pagination=True)
class Fluorophore:
    id: auto
    name: str
    views: List["LabelView"]
    emission_wavelength: scalars.Micrometers | None
    excitation_wavelength: scalars.Micrometers | None
    history: List["History"]


@register_model(models.Antibody, filters=filters.AntibodyFilter, pagination=True)
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


@register_model(AppHistoryModel)
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
    def during(self, info: Info) -> str:
        return self.assignation_id

    @strawberry.django.field()
    def id(self, info: Info) -> strawberry.ID:
        return self.history_id


OtherItem = Annotated[Union[Dataset, Image], strawberry.union("OtherItem")]


@register_model(models.Camera, fields="__all__")
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


@register_model(models.Objective, fields="__all__")
class Objective:
    id: auto
    name: auto
    serial_number: auto
    na: float | None
    magnification: float | None
    immersion: auto
    views: List["OpticsView"]


@register_model(models.Channel, fields="__all__")
class Channel:
    id: auto
    views: List["ChannelView"]


@register_model(models.Instrument, fields="__all__")
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


@register_model(models.ChannelView)
class ChannelView(View):
    id: auto
    channel: Channel


@register_model(models.LabelView)
class LabelView(View):
    id: auto
    fluorophore: Fluorophore
    primary_antibody: Antibody | None
    secondary_antibody: Antibody | None
    acquisition_mode: str


@register_model(models.OpticsView, filters=filters.OpticsViewFilter, pagination=True)
class OpticsView(View):
    id: auto
    instrument: Instrument | None
    camera: Camera | None
    objective: Objective | None


@register_model(
    models.TimepointView, filters=filters.TimepointViewFilter, pagination=True
)
class TimepointView(View):
    id: auto
    era: Era
    ms_since_start: scalars.Milliseconds | None
    index_since_start: int | None


@register_model(
    models.TransformationView, filters=filters.TransformationViewFilter, pagination=True
)
class TransformationView(View):
    id: auto
    stage: Stage
    kind: strawberry.auto
    matrix: scalars.FourByFourMatrix

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
    vectors: scalars.FiveDVector


@register_model(models.ROI)
class RectangleROI(ROI):
    width: int
    height: int
    depth: int


@register_model(models.ROI)
class PathROI(ROI):
    pathLength: int
