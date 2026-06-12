from kante.types import Info
import strawberry

from core import types, models

import kante
from pydantic import BaseModel
from core import enums


class CreateSceneInputModel(BaseModel):
    name: str
    blending: enums.Blending | None = None
    spatial_unit: enums.SpatialUnit | None = None
    temporal_unit: enums.TemporalUnit | None = None


@kante.pydantic_input(CreateSceneInputModel, description="Input type for creating a scene from an array-like object")
class CreateSceneInput:
    name: str = strawberry.field(description="The name of the scene")
    blending: enums.Blending | None = strawberry.field(description="Optional blending mode to use for the scene, e.g. 'additive', 'alpha', etc. If not provided, a default blending mode will be used.")
    spatial_unit: enums.SpatialUnit | None = strawberry.field(description="Optional base unit for the scene, e.g. 'micrometers'. This can be used to provide context for the affine transformations of layers and subscenes within the scene, which can be specified in terms of this base unit.")
    temporal_unit: enums.TemporalUnit | None = strawberry.field(description="Optional base unit for time dimensions in the scene, e.g. 'seconds'. This can be used to provide context for any time dimensions in the scene, which can be specified in terms of this temporal unit.")


def create_scene(
    info: Info,
    input: CreateSceneInput,
) -> types.Scene:
    model = input.to_pydantic()

    x = models.Scene.objects.create(
        name=model.name,
        blending=model.blending or enums.Blending.ADDITIVE,  # Default blending mode if not provided
        spatial_unit=model.spatial_unit or enums.SpatialUnit.UNKNOWN,  # Default to micrometers if not provided
        temporal_unit=model.temporal_unit or enums.TemporalUnit.UNKNOWN,  # Default to seconds if not provided
    )

    return x
