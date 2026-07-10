from kante.types import Info
import kante
import strawberry
from pydantic import BaseModel, Field
from core import types, models, scalars
from core.scoping import get_for_org
from core.mutations._generic import make_delete, make_pin


class MeshInputModel(BaseModel):
    mesh: str = Field(description="The uploaded mesh file store to create the mesh from")
    name: str = Field(description="The name of the mesh")


@kante.pydantic_input(MeshInputModel, description="Input for creating a 3D mesh from an uploaded mesh file")
class MeshInput:
    """Input for creating a 3D mesh from an uploaded mesh file"""

    mesh: scalars.MeshLike = strawberry.field(description="The uploaded mesh file store to create the mesh from")
    name: str = strawberry.field(description="The name of the mesh")


class DeleteMeshInputModel(BaseModel):
    id: str = Field(description="The ID of the mesh to delete")


@kante.pydantic_input(DeleteMeshInputModel, description="Input for deleting a mesh by ID")
class DeleteMeshInput:
    """Input for deleting a mesh by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the mesh to delete")


class PinMeshInputModel(BaseModel):
    id: str = Field(description="The ID of the mesh to pin or unpin")
    pin: bool = Field(description="True to pin, false to unpin")


@kante.pydantic_input(PinMeshInputModel, description="Input for pinning or unpinning a mesh for quick access")
class PinMeshInput:
    """Input for pinning or unpinning a mesh for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the mesh to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


pin_mesh = make_pin(models.Mesh, PinMeshInput, types.Mesh)


delete_mesh = make_delete(models.Mesh, DeleteMeshInput)


def create_mesh(
    info: Info,
    input: MeshInput,
) -> types.Mesh:
    parsed = input.to_pydantic()
    media_store = get_for_org(models.MediaStore, info, id=parsed.mesh)

    item = models.Mesh.objects.create(
        name=parsed.name,
        store=media_store,
        organization=info.context.request.organization,
    )

    return item
