from kante.types import Info
import kante
import strawberry
from pydantic import BaseModel, Field
from core import types, models
from kanne_server import scalars as kanne_scalars
from kanne_server import quantities
from core.mutations._generic import make_delete, make_pin


class CameraInputModel(BaseModel):
    serial_number: str = Field(description="The unique serial number of the camera")
    name: str | None = Field(default=None, description="The name of the camera")
    model: str | None = Field(default=None, description="The model of the camera")
    bit_depth: int | None = Field(default=None, description="The bit depth of the camera sensor")
    sensor_size_x: int | None = Field(default=None, description="The sensor size in x direction (pixels)")
    sensor_size_y: int | None = Field(default=None, description="The sensor size in y direction (pixels)")
    pixel_size_x: quantities.Length | None = Field(default=None, description="The physical pixel size in x direction (e.g. '6.5 µm')")
    pixel_size_y: quantities.Length | None = Field(default=None, description="The physical pixel size in y direction (e.g. '6.5 µm')")
    manufacturer: str | None = Field(default=None, description="The manufacturer of the camera")


@kante.pydantic_input(CameraInputModel, description="Input for creating or ensuring a camera")
class CameraInput:
    """Input for creating or ensuring a camera"""

    serial_number: str = strawberry.field(description="The unique serial number of the camera")
    name: str | None = strawberry.field(default=None, description="The name of the camera")
    model: str | None = strawberry.field(default=None, description="The model of the camera")
    bit_depth: int | None = strawberry.field(default=None, description="The bit depth of the camera sensor")
    sensor_size_x: int | None = strawberry.field(default=None, description="The sensor size in x direction (pixels)")
    sensor_size_y: int | None = strawberry.field(default=None, description="The sensor size in y direction (pixels)")
    pixel_size_x: kanne_scalars.Length | None = strawberry.field(default=None, description="The physical pixel size in x direction (e.g. '6.5 µm')")
    pixel_size_y: kanne_scalars.Length | None = strawberry.field(default=None, description="The physical pixel size in y direction (e.g. '6.5 µm')")
    manufacturer: str | None = strawberry.field(default=None, description="The manufacturer of the camera")


class PinCameraInputModel(BaseModel):
    id: str = Field(description="The ID of the camera to pin or unpin")
    pin: bool = Field(description="True to pin, false to unpin")


@kante.pydantic_input(PinCameraInputModel, description="Input for pinning or unpinning a camera for quick access")
class PinCameraInput:
    """Input for pinning or unpinning a camera for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the camera to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


pin_camera = make_pin(models.Camera, PinCameraInput, types.Camera)


class DeleteCameraInputModel(BaseModel):
    id: str = Field(description="The ID of the camera to delete")


@kante.pydantic_input(DeleteCameraInputModel, description="Input for deleting a camera by ID")
class DeleteCameraInput:
    """Input for deleting a camera by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the camera to delete")


def create_camera(
    info: Info,
    input: CameraInput,
) -> types.Camera:
    parsed = input.to_pydantic()
    view = models.Camera.objects.create(
        organization=info.context.request.organization,
        serial_number=parsed.serial_number,
        name=parsed.name,
        model=parsed.model,
        bit_depth=parsed.bit_depth,
        sensor_size_x=parsed.sensor_size_x,
        sensor_size_y=parsed.sensor_size_y,
        pixel_size_x=parsed.pixel_size_x,
        pixel_size_y=parsed.pixel_size_y,
        manufacturer=parsed.manufacturer,
    )
    return view


delete_camera = make_delete(models.Camera, DeleteCameraInput)


def ensure_camera(
    info: Info,
    input: CameraInput,
) -> types.Camera:
    parsed = input.to_pydantic()
    view, _ = models.Camera.objects.get_or_create(
        serial_number=parsed.serial_number,
        organization=info.context.request.organization,
        defaults=dict(
            name=parsed.name,
            model=parsed.model,
            bit_depth=parsed.bit_depth,
            sensor_size_x=parsed.sensor_size_x,
            sensor_size_y=parsed.sensor_size_y,
            pixel_size_x=parsed.pixel_size_x,
            pixel_size_y=parsed.pixel_size_y,
            manufacturer=parsed.manufacturer,
        ),
    )
    return view
