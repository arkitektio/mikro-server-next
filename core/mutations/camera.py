from kante.types import Info
import strawberry
from core import types, models, scalars


@strawberry.input
class CameraInput:
    serial_number: str
    name: str | None = None
    model: str | None = None
    bit_depth: int | None = None
    sensor_size_x: int | None = None
    sensor_size_y: int | None = None
    pixel_size_x: scalars.Micrometers | None = None
    pixel_size_y: scalars.Micrometers | None = None
    manufacturer: str | None = None


def create_camera(
    info: Info,
    input: CameraInput,
) -> types.Camera:
    view = models.Camera.objects.create(
        serial_number=input.serial_number,
        name=input.name,
        model=input.model,
        bit_depth=input.bit_depth,
        sensor_size_x=input.sensor_size_x,
        sensor_size_y=input.sensor_size_y,
        pixel_size_x=input.pixel_size_x,
        pixel_size_y=input.pixel_size_y,
        manufacturer=input.manufacturer,
    )
    return view


def ensure_camera(
    info: Info,
    input: CameraInput,
) -> types.Camera:
    view, _ = models.Camera.objects.get_or_create(
        serial_number=input.serial_number,
        defaults=dict(
            name=input.name,
            model=input.model,
            bit_depth=input.bit_depth,
            sensor_size_x=input.sensor_size_x,
            sensor_size_y=input.sensor_size_y,
            pixel_size_x=input.pixel_size_x,
            pixel_size_y=input.pixel_size_y,
            manufacturer=input.manufacturer,
        ),
    )
    return view
