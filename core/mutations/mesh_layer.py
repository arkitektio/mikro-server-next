from kante.types import Info
import strawberry

from core import types, models, enums
import kante
from pydantic import BaseModel
from core.logic import graph as graph_logic
from core.input_unions import prose_errors
from core.inputs.validators import Alpha
from core.mutations.layer import build_mesh_color_by
from core.render.layer import inputs as layer_inputs
from core.scoping import get_for_org


class CreateMeshLayerInputModel(BaseModel):
    scene: str
    mesh_collection: str
    material_color: list[int] | None = None
    wireframe: bool | None = None
    color_by: layer_inputs.MeshColorByInputModel | None = None
    blending: enums.Blending | None = None
    opacity: Alpha | None = None
    visible: bool | None = None
    order: int | None = None


_COLOR_BY_DESCRIPTION = (
    "Color the objects by a column of a table this collection's FIELD edge keys into, instead of by the flat `materialColor`. The table must be reachable -- author the edge with "
    "`createTableDataset(keyedBy: {kind: MESH_COLLECTION})` -- and the column must exist on it, because a colorBy naming an unrelated table is not a preference to hold onto until "
    "the edge shows up, it is a join nothing can execute"
)


@prose_errors
@kante.pydantic_input(CreateMeshLayerInputModel, description="Create a layer that renders a mesh collection (surface reconstructions / isosurfaces) in a scene. The collection's own coordinate system is the layer's space, so it must already have a path to the scene's world")
class CreateMeshLayerInput:
    scene: strawberry.ID = strawberry.field(description="The ID of the scene to place the layer in")
    mesh_collection: strawberry.ID = strawberry.field(description="The ID of the mesh collection whose geometry this layer renders. Its own coordinate system is the layer's space")
    material_color: list[int] | None = strawberry.field(default=None, description="Material (surface) color of the mesh, as RGBA (default white)")
    wireframe: bool | None = strawberry.field(default=None, description="Whether to render the mesh as a wireframe (default false)")
    color_by: layer_inputs.MeshColorByInput | None = strawberry.field(default=None, description=_COLOR_BY_DESCRIPTION)
    blending: enums.Blending | None = strawberry.field(default=None, description="Layer-level blend mode (default 'normal', i.e. alpha-over)")
    opacity: float | None = strawberry.field(default=None, description="Layer alpha for alpha-over compositing, from 0 (transparent) to 1 (opaque). Default 1.0")
    visible: bool | None = strawberry.field(default=None, description="Whether the layer participates in compositing (default true)")
    order: int | None = strawberry.field(default=None, description="Explicit z-index for back-to-front compositing (default 0)")


def create_mesh_layer(info: Info, input: CreateMeshLayerInput) -> types.MeshLayer:
    model = input.to_pydantic()

    scene = get_for_org(models.Scene, info, id=model.scene)
    collection = get_for_org(models.MeshCollection, info, id=model.mesh_collection)

    graph_logic.assert_placeable_in(scene.world, getattr(collection, "coordinate_system", None), destination=f"the world of scene '{scene.name}'")

    return models.Layer.objects.create(
        kind=enums.LayerKind.MESH,
        scene=scene,
        mesh_collection=collection,
        material_color=model.material_color if model.material_color is not None else [255, 255, 255, 255],
        wireframe=model.wireframe if model.wireframe is not None else False,
        mesh_color_by=build_mesh_color_by(info, collection, model.color_by),
        blending=model.blending or enums.Blending.NORMAL,
        opacity=model.opacity if model.opacity is not None else 1.0,
        visible=model.visible if model.visible is not None else True,
        order=model.order or 0,
    )


class UpdateMeshLayerInputModel(BaseModel):
    id: str
    material_color: list[int] | None = None
    wireframe: bool | None = None
    color_by: layer_inputs.MeshColorByInputModel | None = None
    blending: enums.Blending | None = None
    opacity: Alpha | None = None
    visible: bool | None = None
    order: int | None = None


@prose_errors
@kante.pydantic_input(
    UpdateMeshLayerInputModel,
    description="Retune how a mesh layer is drawn. A patch: every field is optional and an omitted one keeps its current value, so switching the coloring cannot silently drop the material or the wireframe. The collection and the scene are not editable -- a layer renders what it was created to render",
)
class UpdateMeshLayerInput:
    id: strawberry.ID = strawberry.field(description="The ID of the mesh layer to update")
    material_color: list[int] | None = strawberry.field(default=None, description="Material (surface) color of the mesh, as RGBA")
    wireframe: bool | None = strawberry.field(default=None, description="Whether to render the mesh as a wireframe")
    # Setting a colouring works; **un**setting one does not, because a patch reads an
    # omitted field and an explicit null the same way. The same limitation
    # `updateLabelLayer`'s `colorBy` has, and it wants the same fix in both places rather
    # than an UNSET convention invented here for one field.
    color_by: layer_inputs.MeshColorByInput | None = strawberry.field(default=None, description=f"{_COLOR_BY_DESCRIPTION}. Omitting it keeps the current colouring; there is currently no way to *remove* one and fall back to `materialColor` -- recreate the layer for that")
    blending: enums.Blending | None = strawberry.field(default=None, description="Layer-level blend mode")
    opacity: float | None = strawberry.field(default=None, description="Layer alpha for alpha-over compositing, from 0 (transparent) to 1 (opaque)")
    visible: bool | None = strawberry.field(default=None, description="Whether the layer participates in compositing")
    order: int | None = strawberry.field(default=None, description="Explicit z-index for back-to-front compositing")


def update_mesh_layer(info: Info, input: UpdateMeshLayerInput) -> types.MeshLayer:
    """Patch a mesh layer's render settings, leaving the ones not named alone."""
    model = input.to_pydantic()
    layer = get_for_org(models.Layer, info, id=model.id)
    if layer.kind != enums.LayerKind.MESH.value:
        raise ValueError(f"Layer {layer.pk} is a {layer.kind} layer, not a mesh layer, so it has no material, wireframe or object coloring to set.")

    if model.color_by is not None:
        layer.mesh_color_by = build_mesh_color_by(info, layer.mesh_collection, model.color_by)
    if model.material_color is not None:
        layer.material_color = model.material_color
    if model.wireframe is not None:
        layer.wireframe = model.wireframe
    if model.blending is not None:
        layer.blending = model.blending
    if model.opacity is not None:
        layer.opacity = model.opacity
    if model.visible is not None:
        layer.visible = model.visible
    if model.order is not None:
        layer.order = model.order
    layer.save()
    return layer
