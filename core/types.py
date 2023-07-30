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
    bucket: str
    key: str


@register_model(
    models.Image, filters=filters.ImageFilter, order=filters.ImageOrder, pagination=True
)
class Image:
    id: auto
    views: List["View"]
    origins: List["Image"] = strawberry.django.field()
    dataset: Optional["Dataset"]

    @strawberry.django.field()
    def views(
        self,
        info: Info,
        filters: filters.ViewFilter | None = strawberry.UNSET,
    ) -> List["View"]:
        qs = self.views.all()

        # apply filters if defined
        if filters is not strawberry.UNSET:
            qs = strawberry_django.filters.apply(filters, qs, info)

        result = []
        for view in qs:
            if hasattr(view, "channelview"):
                result.append(view.channelview)
            if hasattr(view, "instrumentview"):
                result.append(view.instrumentview)
            if hasattr(view, "transformationview"):
                result.append(view.transformationview)

        return result

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
    history: List["HistoricalDataset"]


@register_model(models.Stage, filters=filters.StageFilter, pagination=True)
class Stage:
    id: auto
    views: List["TransformationView"]
    description: str | None
    name: str
    history: List["HistoricalDataset"]


@strawberry.enum
class HistoryType(str, Enum):
    CREATE = "+"
    UPDATE = "~"
    DELETE = "-"


@register_model(AppHistoryModel)
class HistoricalDataset:
    id: strawberry.ID
    name: str
    assignation_id: str | None
    history_date: datetime.datetime
    history_user: User | None
    history_type: HistoryType
    history_id: strawberry.ID
    app: App | None


OtherItem = Annotated[Union[Dataset, Image], strawberry.union("OtherItem")]


@register_model(models.Camera, fields="__all__")
class Camera:
    id: auto


@register_model(models.Channel, fields="__all__")
class Channel:
    id: auto
    views: List["ChannelView"]


@register_model(models.Instrument, fields="__all__")
class Instrument:
    id: auto
    views: List["InstrumentView"]


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
    images: List["Image"]
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
    channel: Channel


@register_model(models.InstrumentView)
class InstrumentView(View):
    instrument: Instrument


@register_model(models.TransformationView)
class TransformationView(View):
    stage: Stage
    matrix: scalars.Matrix


@strawberry_django.interface(models.ROI)
class ROI:
    id: auto
    vectors: scalars.Vector


@register_model(models.ROI)
class RectangleROI(ROI):
    width: int
    height: int
    depth: int


@register_model(models.ROI)
class PathROI(ROI):
    pathLength: int
