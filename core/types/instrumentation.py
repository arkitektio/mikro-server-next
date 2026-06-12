import strawberry
from strawberry import auto
from typing import TYPE_CHECKING, List, Annotated
from core import models, scalars, filters
import kante

from core import order

from core.types.auth import ProvenanceEntry

if TYPE_CHECKING:
    from core.types.image import OpticsView


@kante.django_type(models.Camera, fields="__all__", filters=filters.CameraFilter, ordering=order.CameraOrder, pagination=True)
class Camera:
    id: auto
    name: auto
    serial_number: auto
    views: List[Annotated["OpticsView", strawberry.lazy("core.types.image")]]
    model: auto
    bit_depth: auto
    pixel_size_x: scalars.Micrometers | None
    pixel_size_y: scalars.Micrometers | None
    sensor_size_x: int | None
    sensor_size_y: int | None
    manufacturer: str | None
    provenance_entries: List["ProvenanceEntry"] = kante.django_field(description="Provenance entries for this camera")


@kante.django_type(models.Objective, fields="__all__", filters=filters.ObjectiveFilter, ordering=order.ObjectiveOrder, pagination=True)
class Objective:
    id: auto
    name: auto
    serial_number: auto
    na: float | None
    magnification: float | None
    immersion: auto
    views: List[Annotated["OpticsView", strawberry.lazy("core.types.image")]]


@kante.django_type(models.Instrument, fields="__all__", filters=filters.InstrumentFilter, ordering=order.InstrumentOrder, pagination=True)
class Instrument:
    id: auto
    name: auto
    model: auto
    serial_number: auto
    views: List[Annotated["OpticsView", strawberry.lazy("core.types.image")]]
