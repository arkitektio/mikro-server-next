from kante.types import Info
from core import scalars
import strawberry
from core import types, models
from core.scoping import get_for_org
from core.mutations._generic import make_delete


@strawberry.input
class SnapshotInput:
    file: scalars.ImageFileLike
    image: strawberry.ID
    name: str | None = None


@strawberry.input()
class DeleteSnaphotInput:
    id: strawberry.ID


@strawberry.input
class PinSnapshotInput:
    id: strawberry.ID
    pin: bool


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

    item = models.Snapshot.objects.create(name=input.name or "Snapshot", store=media_store, image_id=input.image)
    return item
