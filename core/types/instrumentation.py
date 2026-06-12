import strawberry
from strawberry import auto
from typing import TYPE_CHECKING, List, Annotated
from core import models, scalars, filters
import kante

from core import order

from core.types.auth import ProvenanceEntry

if TYPE_CHECKING:
    from core.types.image import OpticsView


@kante.django_type(
    models.Camera,
    fields="__all__",
    filters=filters.CameraFilter,
    ordering=order.CameraOrder,
    pagination=True,
    description="A camera (detector) on a microscope, described by its sensor dimensions, pixel sizes and bit depth. Clients use it through optics views to record which detector acquired an image.",
)
class Camera:
    """A camera (detector) on a microscope, described by its sensor dimensions, pixel sizes and bit depth. Clients use it through optics views to record which detector acquired an image."""

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


@kante.django_type(
    models.Objective,
    fields="__all__",
    filters=filters.ObjectiveFilter,
    ordering=order.ObjectiveOrder,
    pagination=True,
    description="A microscope objective, described by its magnification, numerical aperture and immersion medium. Clients use it through optics views to record which objective an image was acquired with.",
)
class Objective:
    """A microscope objective, described by its magnification, numerical aperture and immersion medium. Clients use it through optics views to record which objective an image was acquired with."""

    id: auto
    name: auto
    serial_number: auto
    na: float | None
    magnification: float | None
    immersion: auto
    views: List[Annotated["OpticsView", strawberry.lazy("core.types.image")]]


@kante.django_type(
    models.Instrument,
    fields="__all__",
    filters=filters.InstrumentFilter,
    ordering=order.InstrumentOrder,
    pagination=True,
    description="A microscope or other instrument, identified by its manufacturer, model and serial number. Clients use it through optics views to record which instrument acquired an image.",
)
class Instrument:
    """A microscope or other instrument, identified by its manufacturer, model and serial number. Clients use it through optics views to record which instrument acquired an image."""

    id: auto
    name: auto
    model: auto
    serial_number: auto
    views: List[Annotated["OpticsView", strawberry.lazy("core.types.image")]]
