"""Input types for the coordinate system graph.

These live here rather than in ``core.mutations`` so the service layer in
``core.logic`` can reference them without importing a mutation module.

Two axis inputs, deliberately: a dataset's own axes are *structural* -- a name
and a semantic type, no unit, because the dataset's intrinsic space is its pixel
grid. Units only exist on calibrated spaces (PHYSICAL / SHARED), whose axes are
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
    description: str | None = None


@kante.pydantic_input(AxisInputModel, description="Input type for one structural axis of a dataset's pixel grid: its name and its semantic kind. Units and spacings do not belong here -- they are a calibration, a separate coordinate system plus one edge")
class AxisInput:
    """Input for one structural axis of a dataset's pixel grid."""

    name: str = strawberry.field(description="The name of the axis, e.g. 'z', 'c' or 'tau'. Free-form")
    type: enums.AxisType = strawberry.field(description="The semantic kind of the axis. Axes must be ordered by this: time first, then channel and custom types, then space")
    long_name: str | None = strawberry.field(default=None, description="A human-readable name for the axis")
    description: str | None = strawberry.field(default=None, description="A free-form description of what the axis measures, e.g. 'distance from the coverslip'")


class CoordinateInputModel(BaseModel):
    """One discrete coordinate pin: a coordinate name and the value along it."""

    name: str
    value: int


@kante.pydantic_input(CoordinateInputModel, description="A discrete coordinate an annotation is pinned to, e.g. a timepoint or a channel")
class CoordinateInput:
    """Input for pinning to a value along one named coordinate."""

    name: str = strawberry.field(description="The name of the coordinate, e.g. 't' or 'c'")
    value: int = strawberry.field(description="The value along that coordinate")


class BoundingBoxInputModel(BaseModel):
    """An axis-aligned box as a min and a max corner."""

    min: list[float]
    max: list[float]


@kante.pydantic_input(BoundingBoxInputModel, description="An axis-aligned box as a min and a max corner, in the coordinate order of the frame it is asked in")
class BoundingBoxInput:
    """Input for an axis-aligned bounding box."""

    min: list[float] = strawberry.field(description="The lower corner, in the frame's coordinate order")
    max: list[float] = strawberry.field(description="The upper corner, in the frame's coordinate order")


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
    description: str | None = None


@kante.pydantic_input(CalibratedAxisInputModel, description="Input type for one axis of a calibrated coordinate system: its name, its semantic kind and its physical unit")
class CalibratedAxisInput:
    """Input for one axis of a calibrated coordinate system."""

    name: str = strawberry.field(description="The name of the axis, e.g. 'z' or 't'. Free-form")
    type: enums.AxisType = strawberry.field(description="The semantic kind of the axis. Must match the pixel axis at the same position when used in a calibration")
    unit: kanne_scalars.Unit = strawberry.field(description="The physical unit of the axis, e.g. 'micrometer' or 'millisecond'. A pint unit, validated on the way in; 'a.u.' for arbitrary units")
    long_name: str | None = strawberry.field(default=None, description="A human-readable name for the axis")
    description: str | None = strawberry.field(default=None, description="A free-form description of what the axis measures, e.g. 'distance from the coverslip'")


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


class RegistrationPathInputModel(BaseModel):
    """A source to register into a shared coordinate system, plus the edge that places it.

    Exactly one source (a dataset, a table dataset, a mesh collection, or a bare coordinate
    system) is resolved to its own coordinate system; the transform fields are the same edge,
    and the same rank check, that ``createTransformation`` writes -- direction is always
    source -> space.
    """

    dataset: str | None = None
    table_dataset: str | None = None
    mesh_collection: str | None = None
    annotation_collection: str | None = None
    coordinate_system: str | None = None
    kind: enums.TransformKind = enums.TransformKind.IDENTITY
    name: str | None = None
    scale: list[float] | None = None
    translation: list[float] | None = None
    affine: list[list[float]] | None = None
    input_axes: list[str] | None = None
    output_axes: list[str] | None = None
    field: str | None = None
    reason: str | None = None
    validity: enums.PlacementValidity | None = None


@kante.pydantic_input(
    RegistrationPathInputModel,
    description="A source (dataset, table dataset, mesh collection, or coordinate system) to register into a shared space, plus the edge that places it. The edge points from the source's own coordinate system to the shared space; the transform is validated exactly as createTransformation validates one",
)
class RegistrationPathInput:
    """One source registered into a shared coordinate system, and the edge placing it."""

    dataset: strawberry.ID | None = strawberry.field(default=None, description="Register this dataset, through its intrinsic (pixel) coordinate system. Provide exactly one source")
    table_dataset: strawberry.ID | None = strawberry.field(default=None, description="Register this table dataset, through its own coordinate system (its declared coordinate columns). Provide exactly one source")
    mesh_collection: strawberry.ID | None = strawberry.field(default=None, description="Register this mesh collection, through its own vertex coordinate system. Provide exactly one source")
    annotation_collection: strawberry.ID | None = strawberry.field(default=None, description="Register this annotation collection, through its own drawing coordinate system. Provide exactly one source")
    coordinate_system: strawberry.ID | None = strawberry.field(default=None, description="Register this coordinate system directly. Provide exactly one source")
    kind: enums.TransformKind = strawberry.field(default=enums.TransformKind.IDENTITY, description="The kind of edge from the source into the shared space, which fixes which parameter fields are read. Direction is always forward -- if your registration library gave you the inverse, invert it first")
    name: str | None = strawberry.field(default=None, description="Optional name for the registration edge")
    scale: list[float] | None = strawberry.field(default=None, description="(SCALE) The per-axis scale factors, in the source system's axis order")
    translation: list[float] | None = strawberry.field(default=None, description="(TRANSLATION) The per-axis offsets, in the source system's axis order")
    affine: list[list[float]] | None = strawberry.field(default=None, description="(AFFINE / ROTATION) The matrix, M x (N+1), rows outermost. The last column is the translation")
    input_axes: list[str] | None = strawberry.field(default=None, description="(BY_DIMENSION / MAP_AXIS) The names of the source axes this edge acts on, e.g. ['y', 'x']")
    output_axes: list[str] | None = strawberry.field(default=None, description="(BY_DIMENSION / MAP_AXIS) The names of the target space's axes it maps onto")
    field: strawberry.ID | None = strawberry.field(default=None, description="(FIELD) The coordinate system of the array whose values are the map. Its value axis says whether they are positions (COORDINATE) or offsets (DISPLACEMENT); none at all means scalar positions")
    reason: str | None = strawberry.field(default=None, description="(UNMAPPABLE) Why nothing corresponds. Purely descriptive")
    validity: enums.PlacementValidity | None = strawberry.field(default=None, description="How much this map is actually known. Defaults to MANUAL -- someone authored it")


class ScenePolicyInputModel(BaseModel):
    """The policy a scene-from-coordinate-system build follows: how many, and which kinds."""

    nchildren: int = 8
    transform_tables: bool = False
    include_meshes: bool = True


@kante.pydantic_input(
    ScenePolicyInputModel,
    description="The policy createSceneFromCoordinateSystem follows: at most `nchildren` layers, materialized from the sources already registered into the space, filtered by kind",
)
class ScenePolicyInput:
    """How a scene is materialized from the sources registered into a shared space."""

    nchildren: int = strawberry.field(default=8, description="The maximum number of layers to materialize, in registration (pk) order. A flat cap on the scene's size, not a tree of sub-scenes")
    transform_tables: bool = strawberry.field(default=False, description="Whether to turn registered table datasets into point/track layers. Off by default: a table is often a per-object measurement with no place in a scene")
    include_meshes: bool = strawberry.field(default=True, description="Whether to turn registered mesh collections into mesh layers")
