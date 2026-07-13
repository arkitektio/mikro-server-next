"""GraphQL types for the RFC-5 coordinate system graph.

The API ships transformations as **edges** -- ``(input, output, params)`` -- and
leaves the walking to the client. There is deliberately no ``toWorld`` field and
no server-side path composition: the same dataset can sit in two scenes under two
different registrations, so any single answer the server gave would be wrong in
one of them. Composing is the client's job, and it has the whole graph.

``Transformation`` is one Django model discriminated by ``kind``, exposed as an
interface whose concrete types unpack ``params`` into typed fields -- the same
shape as ``Layer``. Subtypes reachable only through the interface are *not*
auto-discovered by strawberry and vanish from the SDL without an error, so they
are registered in :data:`transformation_types` and threaded into the schema's
``types=[...]``.
"""

from typing import List

from strawberry import auto

import kante
from kante.types import Info

from kanne_server import scalars as kanne_scalars
from datalayer.types import ParquetStore

from core import enums, filters, models, order, scalars


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
    # whoever tries to convert with it.
    unit: kanne_scalars.Unit | None
    discrete: bool
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

    @kante.django_field(description="The per-axis scale factors, in the axis order of the input system. Absolute, not relative to another level")
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

    # disable_optimization: with a discriminated single-table interface the Django
    # query optimizer evaluates the queryset synchronously during async type
    # resolution, which raises SynchronousOnlyOperation. Scene.layers carries the
    # same workaround for the same reason.
    transformations: List[Transformation] = kante.django_field(
        field_name="children",
        disable_optimization=True,
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
        disable_optimization=True,
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
        disable_optimization=True,
        description="The forward transformation (order 0) and its inverse (order 1)",
    )


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
