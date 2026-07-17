import datetime

from kante.types import Info
import strawberry

from core import types, models

import kante
from pydantic import BaseModel, Field
from core import enums
from core.creation import CreationContext
from core.inputs.coords import (
    CalibratedAxisInput,
    CalibratedAxisInputModel,
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
    axes: list[CalibratedAxisInputModel] | None = None
    epoch: datetime.datetime | None = None
    coordinate_system: str | None = None


@kante.pydantic_input(CreateSceneInputModel, description="Input type for creating a scene over a world coordinate system: an adopted existing system (a hub, a dataset's intrinsic grid, a calibration), or one minted for the scene")
class CreateSceneInput:
    """Input for creating a scene."""

    name: str = strawberry.field(description="The name of the scene")
    blending: enums.Blending | None = strawberry.field(default=None, description="Optional blending mode to use for the scene, e.g. 'additive', 'alpha', etc. If not provided, a default blending mode will be used.")
    preferred_view: enums.PreferredView | None = strawberry.field(default=None, description="How a viewer should open this scene: flat, volumetric, or its own choice. Defaults to AUTO. Changeable afterwards with `updateScene`")
    background_color: list[float] | None = strawberry.field(default=None, description="The viewer background, as RGBA. Omit to let the viewer use its own")
    axes: list[CalibratedAxisInput] | None = strawberry.field(
        default=None,
        description="The axes of the scene's world coordinate system, with their physical units. The scene has no units of its own -- they are per-axis. Defaults to a spatio-temporal world: a second-valued t, then an isotropic micrometre z, y, x. Pass an explicit list for a purely spatial scene. Mutually exclusive with `coordinateSystem`",
    )
    epoch: datetime.datetime | None = strawberry.field(
        default=None,
        description="Optional wall-clock instant the world's time axis has its origin at, so `wall_clock = epoch + t * unit`. Leave null when the acquisition time is unknown: the time axis composes either way. Mutually exclusive with `coordinateSystem`",
    )
    coordinate_system: strawberry.ID | None = strawberry.field(
        default=None,
        description="An existing coordinate system to adopt as this scene's world instead of minting one: a hub, a dataset's INTRINSIC pixel grid, a PHYSICAL calibration, or a collection's space -- anything except an ARRAY system (a slice of a grid) or another scene's minted world (it cascades with that scene). The scene composes over the space as it is -- axes and epoch come from it, so `axes` and `epoch` must not be passed alongside. The space is not owned by the scene: many scenes can share it, it survives their deletion, and while a scene is rooted in it the space (and its container) cannot be deleted. Over an owned space only that container's own data tree composes; foreign data needs a hub",
    )


def create_scene(
    info: Info,
    input: CreateSceneInput,
) -> types.Scene:
    """Create a scene over a world coordinate system: an adopted existing system or one minted for it."""
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


class CreateSceneFromDatasetInputModel(BaseModel):
    dataset: str
    name: str | None = None
    kind: enums.BootstrapLayerKind | None = None


@kante.pydantic_input(
    CreateSceneFromDatasetInputModel,
    description="Input for bootstrapping a renderable scene for a dataset: a world mirroring its calibration, a full lens, and one default image layer. Sugar over createScene + createLens + a layer mutation -- everything it creates is ordinary and separately editable",
)
class CreateSceneFromDatasetInput:
    """Input for bootstrapping a renderable scene for a dataset."""

    dataset: strawberry.ID = strawberry.field(description="The dataset to stage. Works for any existing dataset, not only a fresh one -- rerunning it simply makes another ordinary scene")
    name: str | None = strawberry.field(default=None, description="The name of the scene. Defaults to the dataset's name")
    kind: enums.BootstrapLayerKind | None = strawberry.field(
        default=None,
        description="The render recipe for the default layer. Omit to infer it from the dataset's axes: a z axis with depth makes a volume, exactly three channels on flat data make an RGB composite, anything else one colormapped source per channel. LABEL is never inferred, only chosen",
    )


def create_scene_from_dataset(info: Info, input: CreateSceneFromDatasetInput) -> types.Scene:
    """Bootstrap a renderable scene for a dataset: world, placement, lens and a default layer, in one call.

    The world's axes mirror the dataset's calibration when it has one, so the data
    renders at physical scale; without one they mirror its time/space axes under
    default units. Exactly one registration is authored, for the staged dataset itself:
    VALIDATED when it mirrors a calibration (an identity by construction), UNKNOWN when
    it mirrors bare pixels. This is the only mutation that writes a placement edge --
    layer mutations reject an unplaced source instead of fabricating one.
    """
    model = input.to_pydantic()

    dataset = get_for_org(models.ADataset, info, id=model.dataset)
    ctx = CreationContext.from_info(info)

    return scene_logic.bootstrap_scene(dataset, ctx, name=model.name, kind=model.kind)


class CreateSceneFromCoordinateSystemInputModel(BaseModel):
    coordinate_system: str
    name: str | None = None
    policy: ScenePolicyInputModel = ScenePolicyInputModel()


@kante.pydantic_input(
    CreateSceneFromCoordinateSystemInputModel,
    description="Bootstrap a renderable scene over an existing coordinate system. Over a hub (an ownerless SHARED space) the sources already registered into it become layers, up to the policy's nchildren -- each source's path to world is the one registration createCoordinateSystem authored. Over an owned system (a dataset's INTRINSIC pixels, a PHYSICAL calibration, a collection's space) the container's own data becomes the layer: it is in its own space by construction, so no edge exists or is authored. Rerunning makes another scene over the same space, which outlives them all",
)
class CreateSceneFromCoordinateSystemInput:
    """Input for bootstrapping a scene over an existing coordinate system."""

    coordinate_system: strawberry.ID = strawberry.field(description="The coordinate system to build the scene over: a hub (its registered sources become the layers) or an owned system such as a dataset's intrinsic grid or calibration (its container's data becomes the layer). It becomes the scene's world as it is. ARRAY systems and other scenes' minted worlds are refused")
    name: str | None = strawberry.field(default=None, description="The name of the scene. Defaults to the hub's name")
    policy: ScenePolicyInput = strawberry.field(default_factory=ScenePolicyInput, description="How the scene is materialized: at most nchildren layers, filtered by kind (transform_tables, include_meshes)")


def create_scene_from_coordinate_system(info: Info, input: CreateSceneFromCoordinateSystemInput) -> types.Scene:
    """Bootstrap a scene over a hub coordinate system and the sources registered into it.

    The scene adopts the hub as its world; each source registered one hop into the hub
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


class DeleteSceneInputModel(BaseModel):
    id: str = Field(description="The ID of the scene to delete")


@kante.pydantic_input(DeleteSceneInputModel, description="Input for deleting a scene by ID")
class DeleteSceneInput:
    """Input for deleting a scene by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the scene to delete")


delete_scene = make_delete(models.Scene, DeleteSceneInput)
