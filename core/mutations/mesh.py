from kante.types import Info
import strawberry
from core import types, models, scalars
from core.scoping import get_for_org


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
    item = get_for_org(models.Mesh, info, id=input.id)
    item.delete()
    return input.id


def create_mesh(
    info: Info,
    input: MeshInput,
) -> types.Mesh:
    media_store = get_for_org(models.MediaStore, info, id=input.mesh)

    item = models.Mesh.objects.create(
        name=input.name,
        store=media_store,
        organization=info.context.request.organization,
    )

    return item
