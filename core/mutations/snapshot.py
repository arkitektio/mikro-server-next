from kante.types import Info
from core import scalars
import strawberry
from core import types, models
from django.conf import settings
from core.datalayer import get_current_datalayer


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


def delete_snapshot(
    info: Info,
    input: DeleteSnaphotInput,
) -> strawberry.ID:
    item = models.Snapshot.objects.get(id=input.id)
    item.delete()
    return input.id


def create_snapshot(
    info: Info,
    input: SnapshotInput,
) -> types.Snapshot:
    media_store = models.MediaStore.objects.get(id=input.file)

    media_store.check()

    item = models.Snapshot.objects.create(name=input.name or f"Snapshot", store=media_store, image_id=input.image)
    return item
