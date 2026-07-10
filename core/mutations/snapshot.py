from kante.types import Info
from core import scalars
import strawberry
import kante
from pydantic import BaseModel, Field
from core import types, models
from core.creation import CreationContext
from core.scoping import get_for_org
from core.mutations._generic import make_delete, make_pin, self_owner


class SnapshotInputModel(BaseModel):
    file: str = Field(description="The uploaded media file store containing the rendered snapshot")
    image: str = Field(description="The ID of the image this snapshot belongs to")
    name: str | None = Field(default=None, description="The name of the snapshot")


@kante.pydantic_input(SnapshotInputModel, description="Input for creating a snapshot (pre-rendered thumbnail) of an image from an uploaded media file")
class SnapshotInput:
    """Input for creating a snapshot (pre-rendered thumbnail) of an image from an uploaded media file"""

    file: scalars.ImageFileLike = strawberry.field(description="The uploaded media file store containing the rendered snapshot")
    image: strawberry.ID = strawberry.field(description="The ID of the image this snapshot belongs to")
    name: str | None = strawberry.field(default=None, description="The name of the snapshot")


class DeleteSnaphotInputModel(BaseModel):
    id: str = Field(description="The ID of the snapshot to delete")


@kante.pydantic_input(DeleteSnaphotInputModel, description="Input for deleting a snapshot by ID")
class DeleteSnaphotInput:
    """Input for deleting a snapshot by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the snapshot to delete")


class PinSnapshotInputModel(BaseModel):
    id: str = Field(description="The ID of the snapshot to pin or unpin")
    pin: bool = Field(description="True to pin, false to unpin")


@kante.pydantic_input(PinSnapshotInputModel, description="Input for pinning or unpinning a snapshot for quick access")
class PinSnapshotInput:
    """Input for pinning or unpinning a snapshot for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the snapshot to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


pin_snapshot = make_pin(models.Snapshot, PinSnapshotInput, types.Snapshot)


delete_snapshot = make_delete(models.Snapshot, DeleteSnaphotInput, owner=self_owner)


def create_snapshot(
    info: Info,
    input: SnapshotInput,
) -> types.Snapshot:
    parsed = input.to_pydantic()
    media_store = get_for_org(models.MediaStore, info, id=parsed.file)

    media_store.check()

    ctx = CreationContext.from_info(info)
    item = models.Snapshot.objects.create(
        name=parsed.name or "Snapshot",
        store=media_store,
        image_id=parsed.image,
        **ctx.provenance_kwargs(),
    )
    return item
