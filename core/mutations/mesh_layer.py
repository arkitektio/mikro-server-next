from kante.types import Info
import strawberry

from core import types, models, enums
import kante
from pydantic import BaseModel
from core.scoping import get_for_org


class CreateMeshLayerInputModel(BaseModel):
    scene: str
    mesh: str
    material_color: list[int] | None = None
    wireframe: bool | None = None
    blending: enums.Blending | None = None
    opacity: float | None = None
    visible: bool | None = None
    order: int | None = None


@kante.pydantic_input(CreateMeshLayerInputModel, description="Create a layer that renders a 3D mesh (surface reconstruction / isosurface) in a scene")
class CreateMeshLayerInput:
    scene: strawberry.ID = strawberry.field(description="The ID of the scene to place the layer in")
    mesh: strawberry.ID = strawberry.field(description="The ID of the mesh whose geometry this layer renders")
    material_color: list[int] | None = strawberry.field(default=None, description="Material (surface) color of the mesh, as RGBA (default white)")
    wireframe: bool | None = strawberry.field(default=None, description="Whether to render the mesh as a wireframe (default false)")
    blending: enums.Blending | None = strawberry.field(default=None, description="Layer-level blend mode (default 'normal', i.e. alpha-over)")
    opacity: float | None = strawberry.field(default=None, description="Layer alpha for alpha-over compositing (default 1.0)")
    visible: bool | None = strawberry.field(default=None, description="Whether the layer participates in compositing (default true)")
    order: int | None = strawberry.field(default=None, description="Explicit z-index for back-to-front compositing (default 0)")


def create_mesh_layer(info: Info, input: CreateMeshLayerInput) -> types.MeshLayer:
    model = input.to_pydantic()

    scene = get_for_org(models.Scene, info, id=model.scene)
    mesh = get_for_org(models.Mesh, info, id=model.mesh)

    return models.Layer.objects.create(
        kind=enums.LayerKind.MESH,
        scene=scene,
        mesh=mesh,
        material_color=model.material_color if model.material_color is not None else [255, 255, 255, 255],
        wireframe=model.wireframe if model.wireframe is not None else False,
        blending=model.blending or enums.Blending.NORMAL,
        opacity=model.opacity if model.opacity is not None else 1.0,
        visible=model.visible if model.visible is not None else True,
        order=model.order or 0,
    )
