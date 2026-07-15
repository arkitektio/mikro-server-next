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
    axes: list[CalibratedAxisInputModel] | None = None
    epoch: datetime.datetime | None = None
    coordinate_system: str | None = None


@kante.pydantic_input(CreateSceneInputModel, description="Input type for creating a scene over a world coordinate system: an adopted existing hub, or one minted for the scene")
class CreateSceneInput:
    """Input for creating a scene."""

    name: str = strawberry.field(description="The name of the scene")
    blending: enums.Blending | None = strawberry.field(default=None, description="Optional blending mode to use for the scene, e.g. 'additive', 'alpha', etc. If not provided, a default blending mode will be used.")
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
        description="An existing hub coordinate system to adopt as this scene's world instead of minting one. The scene composes over the space as it is -- axes and epoch come from it, so `axes` and `epoch` must not be passed alongside. The hub is not owned by the scene: many scenes can share it, and it survives their deletion",
    )


def create_scene(
    info: Info,
    input: CreateSceneInput,
) -> types.Scene:
    """Create a scene over a world coordinate system: an adopted hub or one minted for it."""
    model = input.to_pydantic()
    ctx = CreationContext.from_info(info)

    world = get_for_org(models.CoordinateSystem, info, id=model.coordinate_system) if model.coordinate_system else None
    return scene_logic.create_scene(
        name=model.name,
        axes=model.axes,
        blending=model.blending,
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
    description="Bootstrap a renderable scene over a hub coordinate system (an ownerless SHARED space): the scene adopts the hub as its world, then materializes the sources already registered into the hub as layers, up to the policy's nchildren. It authors no edges -- every registration composed into the scene was authored by createCoordinateSystem, and each source's path to world is that one edge. The hub is shared, not owned: rerunning makes another scene over the same space, and the hub outlives them all",
)
class CreateSceneFromCoordinateSystemInput:
    """Input for bootstrapping a scene over a hub coordinate system."""

    coordinate_system: strawberry.ID = strawberry.field(description="The hub coordinate system to build the scene over. It becomes the scene's world as it is; the sources registered into it become the layers")
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


class DeleteSceneInputModel(BaseModel):
    id: str = Field(description="The ID of the scene to delete")


@kante.pydantic_input(DeleteSceneInputModel, description="Input for deleting a scene by ID")
class DeleteSceneInput:
    """Input for deleting a scene by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the scene to delete")


delete_scene = make_delete(models.Scene, DeleteSceneInput)
