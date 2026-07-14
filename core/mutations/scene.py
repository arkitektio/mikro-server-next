from kante.types import Info
import strawberry

from core import types, models

import kante
from pydantic import BaseModel, Field
from core import enums
from core.creation import CreationContext
from core.inputs.coords import CalibratedAxisInput, CalibratedAxisInputModel
from core.logic import coords as coords_logic
from core.logic import graph as graph_logic
from core.mutations._generic import make_delete


class CreateSceneInputModel(BaseModel):
    name: str
    blending: enums.Blending | None = None
    axes: list[CalibratedAxisInputModel] | None = None


@kante.pydantic_input(CreateSceneInputModel, description="Input type for creating a scene and the WORLD coordinate system its layers are registered into")
class CreateSceneInput:
    """Input for creating a scene."""

    name: str = strawberry.field(description="The name of the scene")
    blending: enums.Blending | None = strawberry.field(default=None, description="Optional blending mode to use for the scene, e.g. 'additive', 'alpha', etc. If not provided, a default blending mode will be used.")
    axes: list[CalibratedAxisInput] | None = strawberry.field(
        default=None,
        description="The axes of the scene's WORLD coordinate system, with their physical units. The scene has no units of its own -- they are per-axis. Defaults to an isotropic micrometre z, y, x space",
    )


# The scene's world space, when the caller does not author one. Micrometres, and
# z/y/x in array order so it composes with a dataset's intrinsic axes without a
# permutation.
_DEFAULT_WORLD_AXES = [
    CalibratedAxisInputModel(name="z", type=enums.AxisType.SPACE, unit="micrometer"),
    CalibratedAxisInputModel(name="y", type=enums.AxisType.SPACE, unit="micrometer"),
    CalibratedAxisInputModel(name="x", type=enums.AxisType.SPACE, unit="micrometer"),
]


def create_scene(
    info: Info,
    input: CreateSceneInput,
) -> types.Scene:
    """Create a scene and the WORLD coordinate system its layers register into."""
    model = input.to_pydantic()

    axes = model.axes or _DEFAULT_WORLD_AXES
    axis_specs = [coords_logic.AxisSpec(name=axis.name, type=axis.type.value) for axis in axes]
    coords_logic.assert_axis_type_order(axis_specs)

    ctx = CreationContext.from_info(info)

    scene = models.Scene.objects.create(
        name=model.name,
        organization=ctx.organization,
        blending=model.blending or enums.Blending.ADDITIVE,
    )

    world = models.CoordinateSystem.objects.create(
        name=f"{model.name}/world",
        kind=enums.CoordinateSystemKindChoices.WORLD.value,
        scene=scene,
        creator=ctx.user,
        organization=ctx.organization,
    )
    graph_logic.create_calibrated_axes(world, axes)

    return scene


class DeleteSceneInputModel(BaseModel):
    id: str = Field(description="The ID of the scene to delete")


@kante.pydantic_input(DeleteSceneInputModel, description="Input for deleting a scene by ID")
class DeleteSceneInput:
    """Input for deleting a scene by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the scene to delete")


delete_scene = make_delete(models.Scene, DeleteSceneInput)
