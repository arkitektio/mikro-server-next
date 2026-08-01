import datetime

from kante.types import Info
import strawberry

from core import types, models

import kante
from pydantic import BaseModel, Field
from core import enums
from core.creation import CreationContext
from core.inputs.coords import (
    PhysicalAxisInput,
    PhysicalAxisInputModel,
    ScenePolicyInput,
    ScenePolicyInputModel,
)
from core.logic import scene as scene_logic
from core.mutations._generic import make_delete
from core.scoping import get_for_org


class CreateSceneInputModel(BaseModel):
    name: str
    blending: enums.Blending | None = None
    preferred_view: enums.PreferredView | None = None
    background_color: list[float] | None = None
    axes: list[PhysicalAxisInputModel] | None = None
    epoch: datetime.datetime | None = None
    coordinate_system: str | None = None


@kante.pydantic_input(CreateSceneInputModel, description="Input type for creating a scene over a world coordinate system: an adopted existing system (a shared space, a dataset's intrinsic grid, a physical space), or one created for it")
class CreateSceneInput:
    """Input for creating a scene."""

    name: str = strawberry.field(description="The name of the scene")
    blending: enums.Blending | None = strawberry.field(default=None, description="Optional blending mode to use for the scene, e.g. 'additive', 'alpha', etc. If not provided, a default blending mode will be used.")
    preferred_view: enums.PreferredView | None = strawberry.field(default=None, description="How a viewer should open this scene: flat, volumetric, or its own choice. Defaults to AUTO. Changeable afterwards with `updateScene`")
    background_color: list[float] | None = strawberry.field(default=None, description="The viewer background, as RGBA. Omit to let the viewer use its own")
    axes: list[PhysicalAxisInput] | None = strawberry.field(
        default=None,
        description="The axes of the scene's world coordinate system, with their physical units. The scene has no units of its own -- they are per-axis. Defaults to a spatio-temporal world: a second-valued t, then an isotropic micrometre z, y, x. Pass an explicit list for a purely spatial scene. Mutually exclusive with `coordinateSystem`",
    )
    epoch: datetime.datetime | None = strawberry.field(
        default=None,
        description="Optional wall-clock instant the world's time axis has its origin at, so `wall_clock = epoch + t * unit`. Leave null when the acquisition time is unknown: the time axis composes either way. Mutually exclusive with `coordinateSystem`",
    )
    coordinate_system: strawberry.ID | None = strawberry.field(
        default=None,
        description="An existing coordinate system to adopt as this scene's world instead of creating one: a shared space, a dataset's intrinsic pixel grid, a physical space, or a collection's space -- anything except a derived pixel grid (a pyramid level, a sliced lens) (a slice of a grid). The scene composes over the space as it is -- axes and epoch come from it, so `axes` and `epoch` must not be passed alongside. The space is never owned by the scene: many scenes can share it, it survives their deletion, and while a scene is rooted in it the space (and its container) cannot be deleted. Over an owned space only that container's own data tree composes; foreign data needs a shared space",
    )


def create_scene(
    info: Info,
    input: CreateSceneInput,
) -> types.Scene:
    """Create a scene over a world coordinate system: an adopted existing system or one created for it."""
    model = input.to_pydantic()
    ctx = CreationContext.from_info(info)

    world = get_for_org(models.CoordinateSystem, info, id=model.coordinate_system) if model.coordinate_system else None
    return scene_logic.create_scene(
        name=model.name,
        axes=model.axes,
        blending=model.blending,
        preferred_view=model.preferred_view,
        background_color=model.background_color,
        epoch=model.epoch,
        world=world,
        ctx=ctx,
    )


class CreateSceneFromCoordinateSystemInputModel(BaseModel):
    coordinate_system: str
    name: str | None = None
    policy: ScenePolicyInputModel = ScenePolicyInputModel()


@kante.pydantic_input(
    CreateSceneFromCoordinateSystemInputModel,
    description="Bootstrap a renderable scene over an existing coordinate system. Over an ownerless SHARED space the sources already registered into it become layers, up to the policy's nchildren -- each source's path to world is the one registration createCoordinateSystem authored. Over an owned system (a dataset's intrinsic pixels, a physical space, a collection's space) the container's own data becomes the layer: it is in its own space by construction, so no edge exists or is authored. Rerunning makes another scene over the same space, which outlives them all",
)
class CreateSceneFromCoordinateSystemInput:
    """Input for bootstrapping a scene over an existing coordinate system."""

    coordinate_system: strawberry.ID = strawberry.field(description="The coordinate system to build the scene over: a shared space (its registered sources become the layers) or an owned system such as a dataset's intrinsic grid or physical space (its container's data becomes the layer). It becomes the scene's world as it is. Derived pixel grids are refused")
    name: str | None = strawberry.field(default=None, description="The name of the scene. Defaults to the coordinate system's name")
    policy: ScenePolicyInput = strawberry.field(default_factory=ScenePolicyInput, description="How the scene is materialized: at most nchildren layers, filtered by kind (transform_tables, include_meshes)")


def create_scene_from_coordinate_system(info: Info, input: CreateSceneFromCoordinateSystemInput) -> types.Scene:
    """Bootstrap a scene over an existing coordinate system and the sources registered into it.

    The scene adopts the system as its world; each source registered one hop into it
    becomes a layer, in registration order, up to policy.nchildren, its registration
    joining the scene's composition. No edge is authored: this materializes layers over
    facts createCoordinateSystem wrote, it never fabricates a placement.
    """
    model = input.to_pydantic()

    system = get_for_org(models.CoordinateSystem, info, id=model.coordinate_system)
    ctx = CreationContext.from_info(info)

    return scene_logic.bootstrap_scene_from_system(system, model.policy, ctx, name=model.name)


class UpdateSceneInputModel(BaseModel):
    id: str = Field(description="The ID of the scene to update")
    preferred_view: enums.PreferredView | None = None
    background_color: list[float] | None = None


@kante.pydantic_input(UpdateSceneInputModel, description="Input for setting a scene's viewer preferences. Every field is optional and an omitted one is left alone, so a client may set one preference without restating the others")
class UpdateSceneInput:
    """Input for setting a scene's viewer preferences."""

    id: strawberry.ID = strawberry.field(description="The ID of the scene to update")
    preferred_view: enums.PreferredView | None = strawberry.field(default=None, description="How a viewer should open this scene. Omit to leave it as it is")
    background_color: list[float] | None = strawberry.field(default=None, description="The viewer background, as RGBA. Omit to leave it as it is")


def update_scene(info: Info, input: UpdateSceneInput) -> types.Scene:
    """Set a scene's viewer preferences.

    Narrow by design: what a viewer should *do* with a scene, not what the scene is. Its
    world, its layers and its name are facts about the composition and are not editable
    here -- a scene's world in particular is load-bearing (RESTRICT, and the space may be
    shared), so moving it is not an "update".

    No `owner=` guard, and that is deliberate: `Scene` has no `creator` column, so
    `self_owner` would raise AttributeError for exactly the non-admin callers a guard
    exists to check, and `creator_owner` has nothing to read. `delete_scene` is
    org-scoped only for the same reason -- `get_for_org` is the whole gate here.
    """
    parsed = input.to_pydantic()
    scene = get_for_org(models.Scene, info, id=parsed.id)

    # An omitted field means "leave it", never "clear it": a client setting the
    # background must not silently reset the view preference to null.
    updated: list[str] = []
    if parsed.preferred_view is not None:
        scene.preferred_view = parsed.preferred_view.value
        updated.append("preferred_view")
    if parsed.background_color is not None:
        scene.background_color = parsed.background_color
        updated.append("background_color")

    if updated:
        scene.save(update_fields=updated)
    return scene


class ClearSceneInputModel(BaseModel):
    id: str = Field(description="The ID of the scene to clear")


@kante.pydantic_input(ClearSceneInputModel, description="Input for clearing a scene: delete every layer, keep the scene and everything it composes over")
class ClearSceneInput:
    """Input for clearing a scene of its layers."""

    id: strawberry.ID = strawberry.field(description="The ID of the scene to clear")


def clear_scene(info: Info, input: ClearSceneInput) -> types.Scene:
    """Delete every layer of a scene, leaving the scene itself standing.

    A pure view-state reset: layers are how a scene shows data, not where data sits, so
    clearing touches no coordinate system, no registration edge and no dataset -- the
    scene's world and every placement fact survive, and other scenes over the same space
    never notice. Repopulating is the ordinary layer mutations (or nothing: an empty
    scene is valid).

    No `owner=` guard, for `update_scene`'s reason: `Scene` has no `creator` column, so
    `get_for_org` is the whole gate here, exactly as it is for `delete_scene`.
    """
    parsed = input.to_pydantic()
    scene = get_for_org(models.Scene, info, id=parsed.id)
    models.Layer.objects.filter(scene=scene).delete()
    return scene


class DeleteSceneInputModel(BaseModel):
    id: str = Field(description="The ID of the scene to delete")


@kante.pydantic_input(DeleteSceneInputModel, description="Input for deleting a scene by ID")
class DeleteSceneInput:
    """Input for deleting a scene by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the scene to delete")


delete_scene = make_delete(models.Scene, DeleteSceneInput)
