"""Input types for the coordinate system graph.

These live here rather than in ``core.mutations`` so the service layer in
``core.logic`` can reference them without importing a mutation module.

Two axis inputs, deliberately: a dataset's own axes are *structural* -- a name
and a semantic type, no unit, because the dataset's intrinsic space is its pixel
grid. Units only exist on calibrated spaces (PHYSICAL / WORLD), whose axes are
supplied through :class:`CalibratedAxisInput`.
"""

import strawberry
from pydantic import BaseModel

import kante
from kanne_server import scalars as kanne_scalars

from core import enums


class AxisInputModel(BaseModel):
    """One structural axis of a dataset's pixel grid, as supplied at ingest."""

    name: str
    type: enums.AxisType
    long_name: str | None = None


@kante.pydantic_input(AxisInputModel, description="Input type for one structural axis of a dataset's pixel grid: its name and its semantic kind. Units and spacings do not belong here -- they are a calibration, a separate coordinate system plus one edge")
class AxisInput:
    """Input for one structural axis of a dataset's pixel grid."""

    name: str = strawberry.field(description="The name of the axis, e.g. 'z', 'c' or 'tau'. Free-form")
    type: enums.AxisType = strawberry.field(description="The semantic kind of the axis. Axes must be ordered by this: time first, then channel and custom types, then space")
    long_name: str | None = strawberry.field(default=None, description="A human-readable name for the axis")


class CalibratedAxisInputModel(BaseModel):
    """One axis of a calibrated (physical or world) coordinate system."""

    name: str
    type: enums.AxisType
    unit: str
    long_name: str | None = None


@kante.pydantic_input(CalibratedAxisInputModel, description="Input type for one axis of a calibrated coordinate system: its name, its semantic kind and its physical unit")
class CalibratedAxisInput:
    """Input for one axis of a calibrated coordinate system."""

    name: str = strawberry.field(description="The name of the axis, e.g. 'z' or 't'. Free-form")
    type: enums.AxisType = strawberry.field(description="The semantic kind of the axis. Must match the pixel axis at the same position when used in a calibration")
    unit: kanne_scalars.Unit = strawberry.field(description="The physical unit of the axis, e.g. 'micrometer' or 'millisecond'. A pint unit, validated on the way in; 'a.u.' for arbitrary units")
    long_name: str | None = strawberry.field(default=None, description="A human-readable name for the axis")


class CalibrationSpecInputModel(BaseModel):
    """A calibration: the physical space's axes and the map from pixels into it."""

    name: str = "physical"
    axes: list[CalibratedAxisInputModel]
    scale: list[float] | None = None
    translation: list[float] | None = None
    affine: list[list[float]] | None = None


@kante.pydantic_input(
    CalibrationSpecInputModel,
    description="A calibration: a PHYSICAL coordinate system (axes carrying the units) plus the single edge mapping the dataset's intrinsic pixels into it. Supply per-axis scale (the pixel size) and optionally a translation (e.g. a stage offset), or a full affine matrix",
)
class CalibrationSpecInput:
    """Input for a calibration of a dataset's pixel grid."""

    name: str = strawberry.field(default="physical", description="The name of the calibrated space, e.g. 'physical', 'stage' or 'specimen'. Namespaced under the dataset's name")
    axes: list[CalibratedAxisInput] = strawberry.field(description="The physical space's axes, corresponding 1:1 by position to the dataset's pixel axes. Their semantic types must match; the units are theirs alone")
    scale: list[float] | None = strawberry.field(default=None, description="The per-axis pixel size, in each axis' own unit: e.g. 0.325 micrometer per pixel in x. Exclusive with `affine`")
    translation: list[float] | None = strawberry.field(default=None, description="An optional per-axis offset in physical units, e.g. the stage position of pixel (0, ..., 0). Combined with `scale` into a sequence")
    affine: list[list[float]] | None = strawberry.field(default=None, description="A full affine matrix, N x (N+1) with the translation in the last column, for calibrations that shear or rotate. Exclusive with `scale`/`translation`")
