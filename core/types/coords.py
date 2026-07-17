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

import datetime
from typing import TYPE_CHECKING, Annotated, List, Union

import strawberry
from strawberry import auto

import kante
from kante.types import Info

from kanne_server import scalars as kanne_scalars
from datalayer.types import ParquetStore

from core import enums, filters, models, order, scalars
from core.logic import graph as graph_logic
from core.types.auth import ProvenanceEntry, User

if TYPE_CHECKING:
    # Only for the lazy annotations below (`scenes`, and the owner union's members):
    # importing them at runtime would be a cycle, since both of these modules import
    # this one's CoordinateSystem.
    from core.types.adataset import ADataset, DataArray, Lens, Scene
    from core.types.table_dataset import TableDataset


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
    # whoever tries to convert with it. Null exactly when the axis holds indices
    # rather than measurements: a dataset's or level's pixel grid, a mesh's voxel
    # grid, a table's INDEX axis. Per-axis on purpose -- kind alone cannot say it,
    # since a table's INTRINSIC space is calibrated exactly when its columns were.
    unit: kanne_scalars.Unit | None
    long_name: str | None
    description: str | None


# The container a system hangs off, as one field rather than six mostly-null ones. Every
# member but MeshCollection lives in a module that imports this one, so each is annotated
# lazily -- the same treatment `CoordinateSystem.scenes` already needs. Both ADataset arms
# of the model (`intrinsic_of` and `dataset`) resolve to the same type here; which of the
# two relationships it is is exactly what `kind` says.
CoordinateSystemOwner = Annotated[
    Union[
        Annotated["ADataset", strawberry.lazy("core.types.adataset")],
        Annotated["DataArray", strawberry.lazy("core.types.adataset")],
        Annotated["Lens", strawberry.lazy("core.types.adataset")],
        Annotated["Scene", strawberry.lazy("core.types.adataset")],
        Annotated["MeshCollection", strawberry.lazy("core.types.coords")],
        Annotated["TableDataset", strawberry.lazy("core.types.table_dataset")],
    ],
    strawberry.union("CoordinateSystemOwner", description="The container that owns a coordinate system and that it cascades with. A hub has none"),
]


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
    axes: List[Axis] = kante.django_field(description="The system's axes, in array order (slowest-varying first). RFC-5 requires them ordered by type: time, then channel and custom types, then space")
    epoch: datetime.datetime | None = kante.django_field(
        description="The wall-clock instant this system's time axis has its origin at: `wall_clock = epoch + t * unit`. A property of the space, not of any composition over it. Meaningful only for a calibrated system with a TIME axis (a scene's world, a shared hub); null when the clock is unanchored -- the time axis is still a perfectly composable relative coordinate"
    )
    scenes: List[Annotated["Scene", strawberry.lazy("core.types.adataset")]] = kante.django_field(
        filters=filters.SceneFilter,
        ordering=order.SceneOrder,
        pagination=True,
        description="The scenes that compose over this system as their world. Non-empty only for a SHARED space (a world minted for one scene, or an ownerless hub): a hub lists every scene sharing it, and outlives each of them. The inverse of `Scene.worldCoordinateSystem`",
    )
    provenance_entries: List[ProvenanceEntry] = kante.django_field(description="Provenance entries for this coordinate system: who created it, and every subsequent change")
    created_at: datetime.datetime
    # Nullable: the creator FK is SET_NULL, so a system outlives the user who made it.
    creator: User | None

    # Derived, not stored: which owner FK is set already says what the system denotes,
    # and a stored label was a second copy free to contradict the cascade. The FK ids
    # are local columns on the row, so the derivation joins nothing -- the `only` hints
    # just keep them from being stripped if column narrowing is ever in play.
    @kante.django_field(
        only=["intrinsic_of", "dataset", "data_array", "lens", "scene", "mesh_collection", "table_dataset"],
        description="What this system denotes, derived from its owner: INTRINSIC for a container's own native space (a dataset's level-0 pixel grid, a mesh collection's vertex space, a table's coordinate-column space), ARRAY for a derived pixel grid (a pyramid level, a slicing lens), PHYSICAL for a calibration, SHARED for a space sources register into (a scene's world, an ownerless hub)",
    )
    def kind(self, info: Info) -> enums.CoordinateSystemKind:
        """Derived from the ownership foreign keys; see the model property."""
        return self.kind

    # The two questions `kind` cannot answer, because a scene's minted world and an ownerless
    # hub are both SHARED. Same `only` hint and same derivation as kind: the FK ids are local
    # columns, so nothing joins.
    @kante.django_field(
        only=["intrinsic_of", "dataset", "data_array", "lens", "scene", "mesh_collection", "table_dataset"],
        description="Whether this is an ownerless shared space, built to be registered into. The one kind of system created bare (`createCoordinateSystem`), and the only adoptable world that can receive registrations -- a scene's own world is SHARED too, but it is scene-owned and cascades away with its scene",
    )
    def is_hub(self, info: Info) -> bool:
        """Derived from the ownership foreign keys; see the model property."""
        return self.is_hub

    @kante.django_field(
        only=["scene", "data_array", "lens"],
        description="Whether a scene may compose over this system as its world, i.e. whether `createSceneFromCoordinateSystem` will accept it. False for an ARRAY system (a pyramid level, a lens crop -- a slice *of* a space, not a space to compose in; its container's intrinsic system is the honest root one hop away) and for another scene's minted world (which cascades with its scene and would be deleted out from under the adopter)",
    )
    def is_adoptable_world(self, info: Info) -> bool:
        """Derived from the ownership foreign keys; see the model property."""
        return self.is_adoptable_world

    # `select_related`, where `kind` above needs only an `only` hint: kind reads the FK ids,
    # which are local columns on the row, whereas this hands back the rows themselves.
    @kante.django_field(
        select_related=["intrinsic_of", "dataset", "data_array", "lens", "scene", "mesh_collection", "table_dataset"],
        description="The container this system belongs to and cascades with: the dataset whose pixel grid or calibration it is, the pyramid level or lens whose grid it is, the collection or table whose native space it is, or the scene the world was minted for. Null for a hub, which nobody owns -- `kind` tells you *what* a system denotes, this tells you *whose* it is",
    )
    def owner(self, info: Info) -> CoordinateSystemOwner | None:
        """The container whose FK is set, in the same precedence order `kind` reads them."""
        # Ownership is exclusive -- at most one of these is ever set -- but the order still
        # mirrors models.CoordinateSystem.kind, so the two fields cannot describe one row
        # differently.
        return self.intrinsic_of or self.mesh_collection or self.table_dataset or self.data_array or self.lens or self.dataset or self.scene


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
    validity: enums.PlacementValidity = kante.django_field(
        description="How much this map is actually known: VALIDATED for a map the server derived (or one someone checked), INFERRED for numbers read from metadata, MANUAL for an authored registration, UNKNOWN for one the server assumed. A layer's validity is the weakest edge on its path to world"
    )
    value_relation: enums.ValueRelation | None = kante.django_field(
        description="(derivation edges) What the operation this edge records did to the *values*, orthogonal to `kind`: IDENTICAL (a crop -- statistics transfer), TRANSFORMED (a deconvolution -- same quantity, new numbers), CATEGORIZED (a threshold -- values became labels, and a bootstrapped scene renders the data as a label map). Null when unstated, and never present on a registration -- values do not cross a claim between spaces"
    )
    # On the interface, so every concrete kind inherits it: an edge is refined in place
    # (`updateTransformation`), which makes this the *only* place the previous states of a
    # placement exist. `version` says the chain moved; these say who moved it and from what.
    provenance_entries: List[ProvenanceEntry] = kante.django_field(description="Provenance entries for this edge: who authored it, and every refinement since. A refinement rewrites the edge in place and bumps `version`, so this audit trail is where the placement's earlier states live")
    created_at: datetime.datetime
    creator: User | None

    # Optimizer *hints*, not a get_queryset override: the axis lists are derived from the
    # endpoints' axes, so those have to ride along with the edge. Passing them as hints
    # lets the optimizer merge them into the queryset it is already building; replacing
    # the queryset instead would throw away the caller's prefetch (a SEQUENCE's children
    # arrive prefetched, and re-querying them per edge is the N+1 this whole field is
    # meant to spare the client).
    @kante.django_field(
        prefetch_related=["input__axes", "output__axes", "parent__input__axes", "parent__output__axes"],
        description="The names of the input axes this edge's parameters are ordered by. `scale`, `translation` and the columns of `affine` follow this order -- which is the input system's axis order, NOT the reading layer's axis names, and the two differ often enough that indexing the arrays against them silently misplaces them. A BY_DIMENSION edge names only the subset of axes it acts on; the axes it does not name are the ones it leaves untouched",
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


@kante.django_type(models.Transformation, filters=filters.TransformationFilter, pagination=True, description="A non-affine map given by the values of an array rather than by a formula. The array is a `field`: a node of this graph, not a payload on this edge, so it keeps its own lineage and its axes say what its numbers mean. It has no closed-form inverse, so a placement path never walks it backwards")
class FieldTransformation(Transformation):
    """A non-affine map given by the values of an array, which is itself a node of the graph."""

    id: auto

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        """Discriminate on the model's `kind` column."""
        return obj.kind == enums.TransformKind.FIELD.value

    # A node, not the store this edge used to carry: the array is data before it is a map --
    # a label mask has its own lineage, provenance and placement -- and a payload can hold
    # none of that. Read its store through the system's own container.
    #
    # Resolved, not exposed raw: the column is null for a self-dereference (see the model),
    # and a client reading `field: null` on an edge whose whole purpose is its field would
    # have to know that convention to make sense of it. It answers the question instead.
    @kante.django_field(
        only=["kind", "field", "input"],
        description="The coordinate system of the array whose values are this map. Its value axis says what they mean: COORDINATE for absolute positions, DISPLACEMENT for offsets, none at all for a scalar array whose single value is a position. Equal to `input` when the array's own pixels are the map, as for a label mask keying a table of objects",
    )
    def field(self, info: Info) -> "CoordinateSystem | None":
        """The field, or the input when the input is its own field. See the model property."""
        return self.effective_field


@kante.django_type(
    models.Transformation,
    filters=filters.TransformationFilter,
    pagination=True,
    description="A declared NON-correspondence: the two systems are related -- one was computed from the other -- and no point of either maps to a point of the other. It has no parameters, no rank and no matrix, and no placement search will walk it, in either direction. This is what a per-object measurement table's relation to the image it was measured from looks like",
)
class UnmappableTransformation(Transformation):
    """A declared non-correspondence: related spaces, and no map between them."""

    id: auto

    @classmethod
    def is_type_of(cls, obj, info) -> bool:
        """Discriminate on the model's `kind` column."""
        return obj.kind == enums.TransformKind.UNMAPPABLE.value

    @kante.django_field(description="Why the geometry does not survive, if the author said. Purely descriptive: the kind is what the graph acts on, and an absent reason does not make the edge any less of a statement")
    def reason(self, info: Info) -> str | None:
        """Why nothing corresponds."""
        return self.params.get("reason")


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


@kante.type(
    description="The connected component of the coordinate graph around one system: every coordinate system it relates to, and every top-level edge between them. Reachability is undirected -- an edge pointing *into* the system you started from (a calibration, say) relates to it just as much as one pointing out -- but every edge is returned in its true stored direction, so composing a path is still the client's job and still needs the inversions flagged"
)
class CoordinateGraph:
    """The subgraph reachable from one coordinate system, edges included."""

    root: CoordinateSystem = strawberry.field(description="The coordinate system the walk started from")
    systems: List[CoordinateSystem] = strawberry.field(description="Every coordinate system reachable from the root, the root included, ordered by ID")
    transformations: List[Transformation] = strawberry.field(description="Every top-level edge with both endpoints in `systems`, ordered by ID. The children of a SEQUENCE / BY_DIMENSION / BIJECTION wrapper are not listed here; they hang off their wrapper")


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
    # The collection's OWN system, not the dataset's. It used to borrow the source's,
    # which forced the vertices to be exactly in that pixel grid; `derivedFrom` is where
    # the relation now lives, and it can say something a borrowed system could not.
    coordinate_system: CoordinateSystem = kante.django_field(description="The coordinate system the collection's vertices are expressed in. The collection owns it; `derivedFrom` relates it to the data the meshes were extracted from")
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

    @kante.django_field(description="The edge relating this collection's space to the space the meshes were extracted from -- an identity when the meshes are in that grid as-is, a scale when they came off a downsampled one. The same relation a derived dataset's `derivedFrom` records. Null for a mesh derived from no data at all")
    def derived_from(self, info: Info) -> Transformation | None:
        """The edge relating this collection's space to the one it came from."""
        system = getattr(self, "coordinate_system", None)
        return graph_logic.collection_derivation_edge(system) if system else None


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
    FieldTransformation,
    BijectionTransformation,
    UnmappableTransformation,
]
