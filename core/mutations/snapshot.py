from kante.types import Info
from core import scalars
import strawberry
from core import types, models
from core.creation import CreationContext
from core.scoping import get_for_org
from core.mutations._generic import make_delete


@strawberry.input(description="Input for creating a snapshot (pre-rendered thumbnail) of an image from an uploaded media file")
class SnapshotInput:
    """Input for creating a snapshot (pre-rendered thumbnail) of an image from an uploaded media file"""

    file: scalars.ImageFileLike = strawberry.field(description="The uploaded media file store containing the rendered snapshot")
    image: strawberry.ID = strawberry.field(description="The ID of the image this snapshot belongs to")
    name: str | None = strawberry.field(default=None, description="The name of the snapshot")


@strawberry.input(description="Input for deleting a snapshot by ID")
class DeleteSnaphotInput:
    """Input for deleting a snapshot by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the snapshot to delete")


@strawberry.input(description="Input for pinning or unpinning a snapshot for quick access")
class PinSnapshotInput:
    """Input for pinning or unpinning a snapshot for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the snapshot to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


def pin_snapshot(
    info: Info,
    input: PinSnapshotInput,
) -> types.Snapshot:
    raise NotImplementedError("TODO")


delete_snapshot = make_delete(models.Snapshot, DeleteSnaphotInput)


def create_snapshot(
    info: Info,
    input: SnapshotInput,
) -> types.Snapshot:
    media_store = get_for_org(models.MediaStore, info, id=input.file)

    media_store.check()

    ctx = CreationContext.from_info(info)
    item = models.Snapshot.objects.create(
        name=input.name or "Snapshot",
        store=media_store,
        image_id=input.image,
        **ctx.provenance_kwargs(),
    )
    return item
