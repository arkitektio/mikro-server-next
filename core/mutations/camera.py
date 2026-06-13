from kante.types import Info
import strawberry
from core import types, models, scalars
from core.mutations._generic import make_delete, make_pin


@strawberry.input(description="Input for creating or ensuring a camera")
class CameraInput:
    """Input for creating or ensuring a camera"""

    serial_number: str = strawberry.field(description="The unique serial number of the camera")
    name: str | None = strawberry.field(default=None, description="The name of the camera")
    model: str | None = strawberry.field(default=None, description="The model of the camera")
    bit_depth: int | None = strawberry.field(default=None, description="The bit depth of the camera sensor")
    sensor_size_x: int | None = strawberry.field(default=None, description="The sensor size in x direction (pixels)")
    sensor_size_y: int | None = strawberry.field(default=None, description="The sensor size in y direction (pixels)")
    pixel_size_x: scalars.Micrometers | None = strawberry.field(default=None, description="The physical pixel size in x direction (micrometers)")
    pixel_size_y: scalars.Micrometers | None = strawberry.field(default=None, description="The physical pixel size in y direction (micrometers)")
    manufacturer: str | None = strawberry.field(default=None, description="The manufacturer of the camera")


@strawberry.input(description="Input for pinning or unpinning a camera for quick access")
class PinCameraInput:
    """Input for pinning or unpinning a camera for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the camera to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


pin_camera = make_pin(models.Camera, PinCameraInput, types.Camera)


@strawberry.input(description="Input for deleting a camera by ID")
class DeleteCameraInput:
    """Input for deleting a camera by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the camera to delete")


def create_camera(
    info: Info,
    input: CameraInput,
) -> types.Camera:
    view = models.Camera.objects.create(
        organization=info.context.request.organization,
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


delete_camera = make_delete(models.Camera, DeleteCameraInput)


def ensure_camera(
    info: Info,
    input: CameraInput,
) -> types.Camera:
    view, _ = models.Camera.objects.get_or_create(
        serial_number=input.serial_number,
        organization=info.context.request.organization,
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
