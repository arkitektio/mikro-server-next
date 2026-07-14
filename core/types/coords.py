"""GraphQL types for the coordinate system graph (RFC-5 inspired).

The API ships transformations as **edges** -- ``(input, output, params)`` -- and
leaves the walking to the client. There is deliberately no ``toWorld`` field on
a dataset or a system and no server-side matrix composition: the same dataset
can sit in two scenes under two different registrations, so any single answer
the server gave would be wrong in one of them. The one sanctioned path query is
scene-scoped -- ``Layer.pathToWorld`` and ``ImageLayer.levelPaths`` return
ordered lists of :class:`PlacementStep` edges, because a layer belongs to
exactly one scene -- and composing them is still the client's job.

``Transformation`` is one Django model discriminated by ``kind``, exposed as an
interface whose concrete types unpack ``params`` into typed fields -- the same
shape as ``Layer``. Subtypes reachable only through the interface are *not*
auto-discovered by strawberry and vanish from the SDL without an error, so they
are registered in :data:`transformation_types` and threaded into the schema's
``types=[...]``.
"""

from typing import List

import strawberry
from strawberry import auto

import kante
from kante.types import Info

from kanne_server import scalars as kanne_scalars
from datalayer.types import ParquetStore

from core import enums, filters, models, order, scalars
from core.logic import graph as graph_logic


@kante.django_type(
    models.Axis,
    filters=filters.AxisFilter,
    pagination=True,
    description="One named, typed dimension of a coordinate system. Its `order` is its index into the array shape",
)
class Axis:
    """One named, typed dimension of a coordinate system."""

    id: auto
    order: int
    name: str
    type: enums.AxisType
    # The kanne Unit scalar, not a free-form string: a unit that pint cannot parse
    # is rejected at the API boundary rather than stored and discovered later by
    # whoever tries to convert with it. Null exactly when the axis belongs to a
    # pixel (INTRINSIC/ARRAY) system.
    unit: kanne_scalars.Unit | None
    long_name: str | None


@kante.django_type(
    models.CoordinateSystem,
    filters=filters.CoordinateSystemFilter,
    ordering=order.CoordinateSystemOrder,
    pagination=True,
    description="A named coordinate space: a node in the transformation graph. Its axes are ordered, and that order is the order of the array's dimensions",
)
class CoordinateSystem:
    """A named coordinate space: a node in the transformation graph."""

    id: auto
    name: auto
    kind: enums.CoordinateSystemKind
    axes: List[Axis] = kante.django_field(description="The system's axes, in array order (slowest-varying first). RFC-5 requires them ordered by type: time, then channel and custom types, then space")


@kante.django_interface(
    models.Transformation,
    description="A directed edge of the coordinate graph, mapping `input` to `output`. Direction is always forward. The concrete kind (Scale, Translation, Affine, Sequence, ...) carries the parameters",
)
class Transformation:
    """A directed edge of the coordinate graph, mapping `input` to `output`."""

    id: auto
    kind: enums.TransformKind
    name: str | None
    input: CoordinateSystem | None
    output: CoordinateSystem | None
    version: int

    # Optimizer *hints*, not a get_queryset override: the axis lists are derived from the
    # endpoints' axes, so those have to ride along with the edge. Passing them as hints
    # lets the optimizer merge them into the queryset it is already building; replacing
    # the queryset instead would throw away the caller's prefetch (a SEQUENCE's children
    # arrive prefetched, and re-querying them per edge is the N+1 this whole field is
    # meant to spare the client).
    @kante.django_field(
        prefetch_related=["input__axes", "output__axes", "parent__input__axes", "parent__output__axes"],
        description="The names of the input axes this edge's parameters are ordered by. `scale`, `translation` and the columns of `affine` follow this order -- which is the input system's axis order, NOT the reading layer's dims, and the two differ often enough that indexing the arrays against dims silently misplaces them. A BY_DIMENSION edge names only the subset of axes it acts on; the axes it does not name are the ones it leaves untouched",
    )
    def input_axes(self, info: Info) -> List[str]:
        """The axis order this edge's parameters are written in, on the input side."""
        return graph_logic.edge_axis_names(self, "input")

    @kante.django_field(
        prefetch_related=["input__axes", "output__axes", "parent__input__axes", "parent__output__axes"],
        description="The names of the output axes this edge produces. For a rank-changing BY_DIMENSION edge (placing a (c,y,x) dataset into a (t,z,y,x) world) this is the subset it maps onto; the world's other axes are untouched",
    )
    def output_axes(self, info: Info) -> List[str]:
        """The axis order this edge's parameters are written in, on the output side."""
        return graph_logic.edge_axis_names(self, "output")


@kante.django_type(models.Transformation, filters=filters.TransformationFilter, pagination=True, description="The identity map: input and output coordinates are the same")
class IdentityTransformation(Transformation):
    """The identity map: input and output coordinates are the same."""

    id: auto

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        """Discriminate on the model's `kind` column."""
        return obj.kind == enums.TransformKind.IDENTITY.value


@kante.django_type(models.Transformation, filters=filters.TransformationFilter, pagination=True, description="A per-axis multiplication, with one entry per input axis")
class ScaleTransformation(Transformation):
    """A per-axis multiplication, with one entry per input axis."""

    id: auto

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        """Discriminate on the model's `kind` column."""
        return obj.kind == enums.TransformKind.SCALE.value

    @kante.django_field(
        description="The per-axis scale factors, in the axis order of the input system, expressed in the units of the output system's axes (dimensionless between pixel systems, e.g. within a pyramid). Absolute, not relative to another level"
    )
    def scale(self, info: Info) -> List[float]:
        """The per-axis scale factors."""
        return self.params.get("scale", [])


@kante.django_type(models.Transformation, filters=filters.TransformationFilter, pagination=True, description="A per-axis offset, with one entry per input axis")
class TranslationTransformation(Transformation):
    """A per-axis offset, with one entry per input axis."""

    id: auto

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        """Discriminate on the model's `kind` column."""
        return obj.kind == enums.TransformKind.TRANSLATION.value

    @kante.django_field(description="The per-axis offsets, in the axis order of the input system")
    def translation(self, info: Info) -> List[float]:
        """The per-axis offsets."""
        return self.params.get("translation", [])


@kante.django_type(models.Transformation, filters=filters.TransformationFilter, pagination=True, description="A general affine map, given as an M x (N+1) matrix with rows outermost")
class AffineTransformation(Transformation):
    """A general affine map, given as an M x (N+1) matrix with rows outermost."""

    id: auto

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        """Discriminate on the model's `kind` column."""
        return obj.kind == enums.TransformKind.AFFINE.value

    @kante.django_field(description="The affine matrix, M x (N+1), rows outermost. The last column is the translation")
    def affine(self, info: Info) -> List[List[float]]:
        """The affine matrix."""
        return self.params.get("affine", [])


@kante.django_type(models.Transformation, filters=filters.TransformationFilter, pagination=True, description="A rotation, given as an orthonormal matrix")
class RotationTransformation(Transformation):
    """A rotation, given as an orthonormal matrix."""

    id: auto

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        """Discriminate on the model's `kind` column."""
        return obj.kind == enums.TransformKind.ROTATION.value

    @kante.django_field(description="The rotation matrix")
    def affine(self, info: Info) -> List[List[float]]:
        """The rotation matrix."""
        return self.params.get("affine", [])


@kante.django_type(models.Transformation, filters=filters.TransformationFilter, pagination=True, description="A permutation of axes, mapping each input axis to an output axis by name")
class MapAxisTransformation(Transformation):
    """A permutation of axes, mapping each input axis to an output axis by name."""

    id: auto

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        """Discriminate on the model's `kind` column."""
        return obj.kind == enums.TransformKind.MAP_AXIS.value

    @kante.django_field(description="The names of the input axes, positionally matched to `outputAxes`")
    def input_axes(self, info: Info) -> List[str]:
        """The input axis names."""
        return self.input_axes or []

    @kante.django_field(description="The names of the output axes, positionally matched to `inputAxes`")
    def output_axes(self, info: Info) -> List[str]:
        """The output axis names."""
        return self.output_axes or []


@kante.django_type(models.Transformation, filters=filters.TransformationFilter, pagination=True, description="An ordered composition of child transformations, applied first to last")
class SequenceTransformation(Transformation):
    """An ordered composition of child transformations, applied first to last."""

    id: auto

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        """Discriminate on the model's `kind` column."""
        return obj.kind == enums.TransformKind.SEQUENCE.value

    transformations: List[Transformation] = kante.django_field(
        field_name="children",
        description="The child transformations, applied first to last. They omit their own input and output: the sequence supplies them",
    )


@kante.django_type(models.Transformation, filters=filters.TransformationFilter, pagination=True, description="A composition of child transformations, each acting on a named subset of the axes")
class ByDimensionTransformation(Transformation):
    """A composition of child transformations, each acting on a named subset of the axes."""

    id: auto

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        """Discriminate on the model's `kind` column."""
        return obj.kind == enums.TransformKind.BY_DIMENSION.value

    transformations: List[Transformation] = kante.django_field(
        field_name="children",
        description="The child transformations. Each carries the `inputAxes` and `outputAxes` it acts on",
    )


@kante.django_type(models.Transformation, filters=filters.TransformationFilter, pagination=True, description="A non-affine map given by a displacement field stored as a Zarr array")
class DisplacementsTransformation(Transformation):
    """A non-affine map given by a displacement field stored as a Zarr array."""

    id: auto

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        """Discriminate on the model's `kind` column."""
        return obj.kind == enums.TransformKind.DISPLACEMENTS.value

    @kante.django_field(description="The id of the Zarr store holding the displacement field")
    def store_id(self, info: Info) -> str | None:
        """The displacement field's store id."""
        return self.params.get("store_id")


@kante.django_type(models.Transformation, filters=filters.TransformationFilter, pagination=True, description="A pair of child transformations giving an explicit forward and inverse map")
class BijectionTransformation(Transformation):
    """A pair of child transformations giving an explicit forward and inverse map."""

    id: auto

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        """Discriminate on the model's `kind` column."""
        return obj.kind == enums.TransformKind.BIJECTION.value

    transformations: List[Transformation] = kante.django_field(
        field_name="children",
        description="The forward transformation (order 0) and its inverse (order 1)",
    )


@kante.type(
    description="One step of a placement path: a transformation edge, plus whether it is traversed against its stored direction. The server returns the steps; composing them into a matrix is the client's job (invert the flagged ones first)"
)
class PlacementStep:
    """One step of a placement path: an edge, and the direction it is walked in."""

    transformation: Transformation = strawberry.field(description="The transformation edge this step walks along")
    inverted: bool = strawberry.field(description="True when the edge is traversed output-to-input; the client must invert it before composing")


@kante.django_type(
    models.MeshCollection,
    filters=filters.MeshCollectionFilter,
    pagination=True,
    description="An immutable, versioned collection of meshes, backed by Parquet stores. Ask the catalog store for an access grant and query the Parquet directly (e.g. with DuckDB) rather than paginating meshes through GraphQL",
)
class MeshCollection:
    """An immutable, versioned collection of meshes, backed by Parquet stores rather than rows."""

    id: auto
    version: str
    spec_version: str
    coordinate_system: CoordinateSystem
    # ParquetStore, not a URL: the store carries the datalayer access grant the
    # client needs to read it, and it is organization-scoped. A bare URL would sit
    # outside the datalayer entirely -- nothing would sign it and nothing would own it.
    catalog: ParquetStore = kante.django_field(description="The Parquet store holding the catalog. Request an access grant from it and read the Parquet directly")
    geometry: List[ParquetStore] = kante.django_field(description="The Parquet stores holding the geometry shards")

    @kante.django_field(description="The octree grid. Its `cellSize` is in voxels of the coordinate system, so the octree aligns to the label grid the meshes were extracted from")
    def grid(self, info: Info) -> scalars.Any:
        """The octree grid."""
        return self.grid

    @kante.django_field(description="The geometry encoding: how positions, normals and indices are quantized and compressed")
    def encoding(self, info: Info) -> scalars.Any:
        """The geometry encoding."""
        return self.encoding


# Subtypes reachable only through the Transformation interface are not
# auto-discovered by strawberry: without this list they are silently dropped from
# the SDL, with no error at import and no error at query time -- the field simply
# is not there. Mirrors core/types/layers.py.
transformation_types = [
    IdentityTransformation,
    ScaleTransformation,
    TranslationTransformation,
    AffineTransformation,
    RotationTransformation,
    MapAxisTransformation,
    SequenceTransformation,
    ByDimensionTransformation,
    DisplacementsTransformation,
    BijectionTransformation,
]
