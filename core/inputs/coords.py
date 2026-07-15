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


class DerivationInputModel(BaseModel):
    """How a collection's own coordinate system relates to the space it was derived from."""

    kind: enums.TransformKind = enums.TransformKind.IDENTITY
    scale: list[float] | None = None
    translation: list[float] | None = None
    affine: list[list[float]] | None = None
    input_axes: list[str] | None = None
    output_axes: list[str] | None = None
    reason: str | None = None


@kante.pydantic_input(
    DerivationInputModel,
    description="How a collection's own coordinate system relates to the space it was derived from. The same edge, and the same rank check, that a derived dataset's `derivedFrom` writes",
)
class DerivationInput:
    """How a collection's space relates to the space it was derived from."""

    kind: enums.TransformKind = strawberry.field(
        default=enums.TransformKind.IDENTITY,
        description="IDENTITY when the data is in that space as-is, SCALE when it was computed on a downsampled grid, UNMAPPABLE when the geometry does not survive at all -- which is the case for a table of per-object measurements, whose rows are not anywhere",
    )
    scale: list[float] | None = strawberry.field(default=None, description="(SCALE) The per-axis factors, in the collection's axis order")
    translation: list[float] | None = strawberry.field(default=None, description="(TRANSLATION) The per-axis offsets, in the collection's axis order")
    affine: list[list[float]] | None = strawberry.field(default=None, description="(AFFINE / ROTATION) The matrix, M x (N+1)")
    input_axes: list[str] | None = strawberry.field(default=None, description="(BY_DIMENSION) The axes of the collection's own system the map acts on")
    output_axes: list[str] | None = strawberry.field(default=None, description="(BY_DIMENSION) The axes of the source system they map onto")
    reason: str | None = strawberry.field(default=None, description="(UNMAPPABLE) Why nothing corresponds, e.g. 'one row per segmented object'. Purely descriptive -- the kind is what the graph acts on")


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
