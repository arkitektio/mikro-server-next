from kante.types import Info
import strawberry
from core import types, models, scalars
from strawberry.file_uploads import Upload
from django.conf import settings
from datalayer.datalayer import get_current_datalayer


@strawberry.input
class MeshInput:
    mesh: scalars.MeshLike
    name: str


@strawberry.input()
class DeleteMeshInput:
    id: strawberry.ID


@strawberry.input
class PinMeshInput:
    id: strawberry.ID
    pin: bool


def pin_mesh(
    info: Info,
    input: DeleteMeshInput,
) -> types.Snapshot:
    raise NotImplementedError("TODO")


def delete_mesh(
    info: Info,
    input: DeleteMeshInput,
) -> strawberry.ID:
    item = models.Mesh.objects.get(id=input.id)
    item.delete()
    return input.id


def create_mesh(
    info: Info,
    input: MeshInput,
) -> types.Mesh:
    media_store = models.MediaStore.objects.get(id=input.mesh)

    item = models.Mesh.objects.create(name=input.name, store=media_store)

    return item
