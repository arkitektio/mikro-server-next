"""Input types for the coordinate system graph.

These live here rather than in ``core.mutations`` so the service layer in
``core.logic`` can reference them without importing a mutation module.
"""

import strawberry
from pydantic import BaseModel

import kante
from kanne_server import scalars as kanne_scalars

from core import enums


class AxisInputModel(BaseModel):
    """One axis of a coordinate system, as supplied at ingest."""

    name: str
    type: enums.AxisType
    unit: str | None = None
    spacing: float = 1.0
    discrete: bool = False
    long_name: str | None = None


@kante.pydantic_input(AxisInputModel, description="Input type for one axis: its name, its kind, its physical unit and the size of one voxel along it")
class AxisInput:
    """Input for one axis of a coordinate system."""

    name: str = strawberry.field(description="The name of the axis, e.g. 'z', 'c' or 'tau'. Free-form")
    type: enums.AxisType = strawberry.field(description="The kind of the axis. RFC-5 requires the axes to be ordered by this: time first, then channel and custom types, then space")
    unit: kanne_scalars.Unit | None = strawberry.field(
        default=None,
        description="The physical unit of the axis, e.g. 'micrometer' or 'millisecond'. A pint unit, validated on the way in -- 'a.u.' for arbitrary units, null for discrete and index axes",
    )
    spacing: float = strawberry.field(
        default=1.0,
        description="The size of one voxel along this axis at level 0, in `unit`. This base spacing is the only place physical space enters the model: every pyramid level's absolute scale is derived from it",
    )
    discrete: bool = strawberry.field(default=False, description="Whether the axis' coordinates are discrete indices rather than continuous positions. Channels and time are usually discrete, while space is usually continuous. Discrete axes are not allowed to have a unit or spacing")
    long_name: str | None = strawberry.field(default=None, description="A human-readable name for the axis")
