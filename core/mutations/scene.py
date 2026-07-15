import datetime

from kante.types import Info
import strawberry

from core import types, models

import kante
from pydantic import BaseModel, Field
from core import enums
from core.creation import CreationContext
from core.inputs.coords import CalibratedAxisInput, CalibratedAxisInputModel
from core.logic import scene as scene_logic
from core.mutations._generic import make_delete
from core.scoping import get_for_org


class CreateSceneInputModel(BaseModel):
    name: str
    blending: enums.Blending | None = None
    axes: list[CalibratedAxisInputModel] | None = None
    epoch: datetime.datetime | None = None


@kante.pydantic_input(CreateSceneInputModel, description="Input type for creating a scene and the WORLD coordinate system its layers are registered into")
class CreateSceneInput:
    """Input for creating a scene."""

    name: str = strawberry.field(description="The name of the scene")
    blending: enums.Blending | None = strawberry.field(default=None, description="Optional blending mode to use for the scene, e.g. 'additive', 'alpha', etc. If not provided, a default blending mode will be used.")
    axes: list[CalibratedAxisInput] | None = strawberry.field(
        default=None,
        description="The axes of the scene's WORLD coordinate system, with their physical units. The scene has no units of its own -- they are per-axis. Defaults to a spatio-temporal world: a second-valued t, then an isotropic micrometre z, y, x. Pass an explicit list for a purely spatial scene",
    )
    epoch: datetime.datetime | None = strawberry.field(
        default=None,
        description="Optional wall-clock instant the world's time axis has its origin at, so `wall_clock = epoch + t * unit`. Leave null when the acquisition time is unknown: the time axis composes either way",
    )


def create_scene(
    info: Info,
    input: CreateSceneInput,
) -> types.Scene:
    """Create a scene and the WORLD coordinate system its layers register into."""
    model = input.to_pydantic()
    ctx = CreationContext.from_info(info)

    return scene_logic.create_scene(
        name=model.name,
        axes=model.axes,
        blending=model.blending,
        epoch=model.epoch,
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


class DeleteSceneInputModel(BaseModel):
    id: str = Field(description="The ID of the scene to delete")


@kante.pydantic_input(DeleteSceneInputModel, description="Input for deleting a scene by ID")
class DeleteSceneInput:
    """Input for deleting a scene by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the scene to delete")


delete_scene = make_delete(models.Scene, DeleteSceneInput)
