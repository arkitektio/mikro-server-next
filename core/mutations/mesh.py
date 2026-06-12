from kante.types import Info
import strawberry
from core import types, models, scalars
from core.scoping import get_for_org
from core.mutations._generic import make_delete, make_pin


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


pin_mesh = make_pin(models.Mesh, PinMeshInput, types.Mesh)


delete_mesh = make_delete(models.Mesh, DeleteMeshInput)


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
