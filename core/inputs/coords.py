"""Input types for the coordinate system graph.

These live here rather than in ``core.mutations`` so the service layer in
``core.logic`` can reference them without importing a mutation module.

Two axis inputs, deliberately: a dataset's own axes are *structural* -- a name
and a semantic type, no unit, because the dataset's intrinsic space is its pixel
grid. Units only exist on unit-carrying spaces (a dataset's physical space, a
shared world), whose axes are supplied through :class:`PhysicalAxisInput`.
"""

import dataclasses
from typing import Annotated, Literal

import strawberry
from pydantic import BaseModel, ConfigDict, Field

import kante
from kanne_server import scalars as kanne_scalars

from core import enums
from core.input_unions import parse_union_member, union_memberships


class AxisInputModel(BaseModel):
    """One structural axis of a dataset's pixel grid, as supplied at ingest."""

    name: str
    type: enums.AxisType
    long_name: str | None = None
    description: str | None = None


@kante.pydantic_input(AxisInputModel, description="Input type for one structural axis of a dataset's pixel grid: its name and its semantic kind. Units and spacings do not belong here -- they belong to a physical space, a separate coordinate system plus one edge")
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


# --------------------------------------------------------------------------------------
# The transform input union.
#
# One edge of the coordinate graph arrives as the flat, discriminator-carrying
# ``TransformInput``: `kind` plus the union
# of every kind's parameter fields. The per-kind member models below are the strict
# truth about which fields each kind reads -- they forbid the rest, so a parameter that
# contradicts the kind is an error, never a silent drop -- and their input mirrors are
# published in the SDL under ``@unionElementOf`` so a generated client can rebuild the
# tagged union. IDENTITY has a member model but no SDL mirror: it has no fields, and
# GraphQL forbids an empty input object.


@dataclasses.dataclass(frozen=True)
class LoweredTransform:
    """A transform member flattened to the shape the graph writers take.

    ``kind`` is the value string; the rest are exactly the keyword arguments of
    :func:`core.logic.graph.build_registration_edge` and ``write_relation_edge``, so a
    resolver lowers once and passes through. ``field`` stays an unresolved ID: the
    resolver is the request-scoped place to fetch the system.
    """

    kind: str
    scale: list[float] | None = None
    translation: list[float] | None = None
    affine: list[list[float]] | None = None
    input_axes: list[str] | None = None
    output_axes: list[str] | None = None
    field: str | None = None
    reason: str | None = None


IDENTITY_TRANSFORM = LoweredTransform(kind=enums.TransformKind.IDENTITY.value)


class IdentityTransformInputModel(BaseModel):
    """The identity map: no parameters. No SDL mirror -- GraphQL forbids an empty input."""

    kind: Literal["IDENTITY"] = "IDENTITY"
    model_config = ConfigDict(extra="forbid")

    def lower(self) -> LoweredTransform:
        """Flatten to the shape the graph writers take."""
        return LoweredTransform(kind=self.kind)


class ScaleTransformInputModel(BaseModel):
    """A per-axis multiplication: `scale` has one entry per input axis."""

    kind: Literal["SCALE"] = "SCALE"
    scale: list[float]
    model_config = ConfigDict(extra="forbid")

    def lower(self) -> LoweredTransform:
        """Flatten to the shape the graph writers take."""
        return LoweredTransform(kind=self.kind, scale=self.scale)


class TranslationTransformInputModel(BaseModel):
    """A per-axis offset: `translation` has one entry per input axis."""

    kind: Literal["TRANSLATION"] = "TRANSLATION"
    translation: list[float]
    model_config = ConfigDict(extra="forbid")

    def lower(self) -> LoweredTransform:
        """Flatten to the shape the graph writers take."""
        return LoweredTransform(kind=self.kind, translation=self.translation)


class AffineTransformInputModel(BaseModel):
    """A general affine map: `affine` is M x (N+1), rows outermost."""

    kind: Literal["AFFINE"] = "AFFINE"
    affine: list[list[float]]
    model_config = ConfigDict(extra="forbid")

    def lower(self) -> LoweredTransform:
        """Flatten to the shape the graph writers take."""
        return LoweredTransform(kind=self.kind, affine=self.affine)


class RotationTransformInputModel(BaseModel):
    """A rotation: `affine` is the orthonormal matrix, in an AFFINE's layout."""

    kind: Literal["ROTATION"] = "ROTATION"
    affine: list[list[float]]
    model_config = ConfigDict(extra="forbid")

    def lower(self) -> LoweredTransform:
        """Flatten to the shape the graph writers take."""
        return LoweredTransform(kind=self.kind, affine=self.affine)


class MapAxisTransformInputModel(BaseModel):
    """A pure permutation of axes; the two lists are the whole map."""

    kind: Literal["MAP_AXIS"] = "MAP_AXIS"
    input_axes: list[str]
    output_axes: list[str]
    model_config = ConfigDict(extra="forbid")

    def lower(self) -> LoweredTransform:
        """Flatten to the shape the graph writers take."""
        return LoweredTransform(kind=self.kind, input_axes=self.input_axes, output_axes=self.output_axes)


class ByDimensionTransformInputModel(BaseModel):
    """A map over a named subset of axes, optionally with parameters over that subset."""

    kind: Literal["BY_DIMENSION"] = "BY_DIMENSION"
    input_axes: list[str]
    output_axes: list[str]
    scale: list[float] | None = None
    translation: list[float] | None = None
    affine: list[list[float]] | None = None
    model_config = ConfigDict(extra="forbid")

    def lower(self) -> LoweredTransform:
        """Flatten to the shape the graph writers take."""
        return LoweredTransform(
            kind=self.kind,
            input_axes=self.input_axes,
            output_axes=self.output_axes,
            scale=self.scale,
            translation=self.translation,
            affine=self.affine,
        )


class FieldTransformInputModel(BaseModel):
    """An array-valued map: `field` names the array's coordinate system."""

    kind: Literal["FIELD"] = "FIELD"
    field: str
    input_axes: list[str]
    output_axes: list[str]
    model_config = ConfigDict(extra="forbid")

    def lower(self) -> LoweredTransform:
        """Flatten to the shape the graph writers take."""
        return LoweredTransform(kind=self.kind, field=self.field, input_axes=self.input_axes, output_axes=self.output_axes)


class UnmappableTransformInputModel(BaseModel):
    """A declared non-correspondence, with an optional reason."""

    kind: Literal["UNMAPPABLE"] = "UNMAPPABLE"
    reason: str | None = None
    model_config = ConfigDict(extra="forbid")

    def lower(self) -> LoweredTransform:
        """Flatten to the shape the graph writers take."""
        return LoweredTransform(kind=self.kind, reason=self.reason)


#: Every directly-creatable kind, keyed by discriminator value: the one union every
#: authored edge -- registration or derivation -- arrives through.
TRANSFORM_MEMBERS: dict[str, type[BaseModel]] = {
    "IDENTITY": IdentityTransformInputModel,
    "SCALE": ScaleTransformInputModel,
    "TRANSLATION": TranslationTransformInputModel,
    "AFFINE": AffineTransformInputModel,
    "ROTATION": RotationTransformInputModel,
    "MAP_AXIS": MapAxisTransformInputModel,
    "BY_DIMENSION": ByDimensionTransformInputModel,
    "FIELD": FieldTransformInputModel,
    "UNMAPPABLE": UnmappableTransformInputModel,
}

@kante.pydantic_input(
    ScaleTransformInputModel,
    directives=union_memberships("TransformInput", key="SCALE"),
    description="The fields a SCALE member of TransformInput reads. Published for codegen; the wire type is the flat TransformInput",
)
class ScaleTransformInput:
    """The SCALE member of the transform input union."""

    scale: list[float] = strawberry.field(description="The per-axis scale factors, in the axis order of the input system")


@kante.pydantic_input(
    TranslationTransformInputModel,
    directives=union_memberships("TransformInput", key="TRANSLATION"),
    description="The fields a TRANSLATION member of TransformInput reads. Published for codegen; the wire type is the flat TransformInput",
)
class TranslationTransformInput:
    """The TRANSLATION member of the transform input union."""

    translation: list[float] = strawberry.field(description="The per-axis offsets, in the axis order of the input system")


@kante.pydantic_input(
    AffineTransformInputModel,
    directives=union_memberships("TransformInput", key="AFFINE"),
    description="The fields an AFFINE member of TransformInput reads. Published for codegen; the wire type is the flat TransformInput",
)
class AffineTransformInput:
    """The AFFINE member of the transform input union."""

    affine: list[list[float]] = strawberry.field(description="The matrix, M x (N+1), rows outermost. The last column is the translation")


@kante.pydantic_input(
    RotationTransformInputModel,
    directives=union_memberships("TransformInput", key="ROTATION"),
    description="The fields a ROTATION member of TransformInput reads. Published for codegen; the wire type is the flat TransformInput",
)
class RotationTransformInput:
    """The ROTATION member of the transform input union."""

    affine: list[list[float]] = strawberry.field(description="The orthonormal rotation matrix, in the same M x (N+1) layout an AFFINE uses")


@kante.pydantic_input(
    MapAxisTransformInputModel,
    directives=union_memberships("TransformInput", key="MAP_AXIS"),
    description="The fields a MAP_AXIS member of TransformInput reads. Published for codegen; the wire type is the flat TransformInput",
)
class MapAxisTransformInput:
    """The MAP_AXIS member of the transform input union."""

    input_axes: list[str] = strawberry.field(description="The names of the input axes, e.g. ['z', 'y', 'x']")
    output_axes: list[str] = strawberry.field(description="The names of the output axes they map onto, position by position. The matrix is synthesized from the two lists")


@kante.pydantic_input(
    ByDimensionTransformInputModel,
    directives=union_memberships("TransformInput", key="BY_DIMENSION"),
    description="The fields a BY_DIMENSION member of TransformInput reads. Published for codegen; the wire type is the flat TransformInput",
)
class ByDimensionTransformInput:
    """The BY_DIMENSION member of the transform input union."""

    input_axes: list[str] = strawberry.field(description="The names of the input axes this edge acts on, e.g. ['y', 'x'] for a (c,y,x) dataset placed into a (t,z,y,x) world. The axes it does not name it says nothing about")
    output_axes: list[str] = strawberry.field(description="The names of the output axes they map onto")
    scale: list[float] | None = strawberry.field(default=None, description="Optional per-axis scale factors over the named axes, in the order they are named")
    translation: list[float] | None = strawberry.field(default=None, description="Optional per-axis offsets over the named axes")
    affine: list[list[float]] | None = strawberry.field(default=None, description="Optional matrix over the named axes, M x (N+1), rows outermost")


@kante.pydantic_input(
    FieldTransformInputModel,
    directives=union_memberships("TransformInput", key="FIELD"),
    description="The fields a FIELD member of TransformInput reads. Published for codegen; the wire type is the flat TransformInput",
)
class FieldTransformInput:
    """The FIELD member of the transform input union."""

    field: strawberry.ID = strawberry.field(
        description="The coordinate system of the array whose values are the map. Its value axis says what they mean -- COORDINATE for absolute positions, DISPLACEMENT for offsets, none at all for a scalar array whose one value is a position. Pass the input's own system when the array's pixels are themselves the map, as for a label mask keying a table of objects. A FIELD has no closed-form inverse, so a placement path only ever walks it forwards"
    )
    input_axes: list[str] = strawberry.field(description="The input axes the lookup consumes, e.g. ['y', 'x'] for a label mask -- the ones it does not name pass through")
    output_axes: list[str] = strawberry.field(description="The output axes the field's values produce, e.g. ['i']")


@kante.pydantic_input(
    UnmappableTransformInputModel,
    directives=union_memberships("TransformInput", key="UNMAPPABLE"),
    description="The fields an UNMAPPABLE member of TransformInput reads. Published for codegen; the wire type is the flat TransformInput",
)
class UnmappableTransformInput:
    """The UNMAPPABLE member of the transform input union."""

    reason: str | None = strawberry.field(default=None, description="Why nothing corresponds, e.g. 'one row per segmented object'. Purely descriptive: the kind is what the graph acts on")


#: The member inputs published to the SDL, for the schema's ``types=[...]``. IDENTITY is
#: absent: it has no fields, and GraphQL forbids an empty input object.
transform_union_types: list[type] = [
    ScaleTransformInput,
    TranslationTransformInput,
    AffineTransformInput,
    RotationTransformInput,
    MapAxisTransformInput,
    ByDimensionTransformInput,
    FieldTransformInput,
    UnmappableTransformInput,
]


#: The union the pydantic side carries: a `transform` field holds one *member* model, so
#: a resolver never sees the flat wire shape at all. The wire lie -- GraphQL has no input
#: unions, so the SDL type is flat -- is corrected exactly once, in the strawberry
#: inputs' hand-written ``to_pydantic`` below.
TransformSpec = Annotated[
    IdentityTransformInputModel
    | ScaleTransformInputModel
    | TranslationTransformInputModel
    | AffineTransformInputModel
    | RotationTransformInputModel
    | MapAxisTransformInputModel
    | ByDimensionTransformInputModel
    | FieldTransformInputModel
    | UnmappableTransformInputModel,
    Field(discriminator="kind"),
]

@strawberry.input(
    description="One edge of the coordinate graph, as a discriminated union: `kind` selects a member, and only that member's fields are read -- any other supplied field is rejected, never dropped. The member inputs annotated `@unionElementOf(union: \"TransformInput\")` say which fields each kind reads. Direction is always forward, input -> output",
)
class TransformInput:
    """One authored edge of the coordinate graph, discriminated by `kind`.

    Deliberately not pydantic-backed: the wire type is flat because GraphQL has no
    input unions, and ``to_pydantic`` is where that flatness is corrected into the
    strict member model -- so the pydantic layer only ever holds the union.
    """

    kind: enums.CreatableTransformKind = strawberry.field(description="The kind of transformation, which fixes which of the fields below are read. Any field outside the chosen kind's member is rejected")
    scale: list[float] | None = strawberry.field(default=None, description="(SCALE, BY_DIMENSION) The per-axis scale factors")
    translation: list[float] | None = strawberry.field(default=None, description="(TRANSLATION, BY_DIMENSION) The per-axis offsets")
    affine: list[list[float]] | None = strawberry.field(default=None, description="(AFFINE, ROTATION, BY_DIMENSION) The matrix, M x (N+1), rows outermost")
    input_axes: list[str] | None = strawberry.field(default=None, description="(MAP_AXIS, BY_DIMENSION, FIELD) The names of the input axes the edge acts on")
    output_axes: list[str] | None = strawberry.field(default=None, description="(MAP_AXIS, BY_DIMENSION, FIELD) The names of the output axes they map onto")
    field: strawberry.ID | None = strawberry.field(default=None, description="(FIELD) The coordinate system of the array whose values are the map")
    reason: str | None = strawberry.field(default=None, description="(UNMAPPABLE) Why nothing corresponds. Purely descriptive")

    def to_pydantic(self) -> BaseModel:
        """Match the flat wire fields to the member model `kind` selects, strictly."""
        supplied = {
            "kind": self.kind,
            "scale": self.scale,
            "translation": self.translation,
            "affine": self.affine,
            "input_axes": self.input_axes,
            "output_axes": self.output_axes,
            "field": self.field,
            "reason": self.reason,
        }
        data = {name: value for name, value in supplied.items() if value is not None}
        return parse_union_member(TRANSFORM_MEMBERS, data, noun="transformation")


class DerivationInputModel(BaseModel):
    """How a collection's own coordinate system relates to the space it was derived from."""

    transform: TransformSpec | None = None


@kante.pydantic_input(
    DerivationInputModel,
    description="How a collection's own coordinate system relates to the space it was derived from. The same edge, the same kinds, and the same rank check, that a derived dataset's `derivedFrom` writes",
)
class DerivationInput:
    """How a collection's space relates to the space it was derived from."""

    transform: TransformInput | None = strawberry.field(
        default=None,
        description="The edge back into the source space -- any creatable kind; the rank check holds you to it. Omit for an IDENTITY -- the data is in that space as-is. UNMAPPABLE when the geometry does not survive at all, which is the case for a table of per-object measurements, whose rows are not anywhere. A FIELD's `field` must name a pre-existing coordinate system -- the collection's own system is created by this same call, so a self-field is stated afterwards with createTransformation",
    )


class PhysicalAxisInputModel(BaseModel):
    """One axis of a unit-carrying coordinate system (a physical space, a shared world)."""

    name: str
    type: enums.AxisType
    unit: str
    long_name: str | None = None
    description: str | None = None


@kante.pydantic_input(PhysicalAxisInputModel, description="Input type for one axis of a unit-carrying coordinate system: its name, its semantic kind and its physical unit")
class PhysicalAxisInput:
    """Input for one axis of a unit-carrying coordinate system."""

    name: str = strawberry.field(description="The name of the axis, e.g. 'z' or 't'. Free-form")
    type: enums.AxisType = strawberry.field(description="The semantic kind of the axis. Must match the pixel axis at the same position when the space reinterprets a dataset's grid")
    unit: kanne_scalars.Unit = strawberry.field(description="The physical unit of the axis, e.g. 'micrometer' or 'millisecond'. A pint unit, validated on the way in; 'a.u.' for arbitrary units")
    long_name: str | None = strawberry.field(default=None, description="A human-readable name for the axis")
    description: str | None = strawberry.field(default=None, description="A free-form description of what the axis measures, e.g. 'distance from the coverslip'")


class RegistrationPathInputModel(BaseModel):
    """A source to register into a shared coordinate system, plus the edge that places it.

    Exactly one source (a dataset, a table dataset, a mesh collection, or a bare coordinate
    system) is resolved to its own coordinate system; ``transform`` is the same edge,
    and the same rank check, that ``createTransformation`` writes -- direction is always
    source -> space.
    """

    dataset: str | None = None
    table_dataset: str | None = None
    mesh_collection: str | None = None
    annotation_collection: str | None = None
    coordinate_system: str | None = None
    transform: TransformSpec | None = None
    name: str | None = None
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
    transform: TransformInput | None = strawberry.field(
        default=None,
        description="The edge from the source into the shared space. Omit for an IDENTITY -- the source's coordinates are the space's coordinates as-is. Direction is always forward -- if your registration library gave you the inverse, invert it first",
    )
    name: str | None = strawberry.field(default=None, description="Optional name for the registration edge")
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
