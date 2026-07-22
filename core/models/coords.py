"""The coordinate system graph (RFC-5 inspired).

Coordinate systems are nodes, transformations are directed edges, and every
spatial fact in the array-dataset world is exactly one node or one edge. Pixel
grids, pyramid levels, crops, calibrations, registrations and ROIs all live
here; nothing else in the schema carries a duplicate copy of a spatial fact.

Four rules govern this module.

**Edges are facts, paths are queries.** The API ships transformations as
``(input, output, params)`` edges. It does not resolve "to world" on a dataset
or a system, and it never composes matrices server-side: the same dataset can
appear in two scenes under two different registrations, so any single answer
would be wrong in one of them. The one sanctioned path *query* is scene-scoped
-- a layer belongs to exactly one scene, so ``Layer.pathToWorld`` answers with
the ordered list of edges (see :func:`core.logic.graph.path_in_scene`), and the
client still composes.

**Store what was authored or measured; derive everything else.** A registration,
a crop and a calibration took a judgement call, so they are stored. A pyramid
level's absolute scale follows from the shapes, so it is derived once by
:mod:`core.logic.coords` at write time -- and the *result* is stored, never
re-derived at read, so that no two readers can disagree.

**Pixel space is structural; physical space is an interpretation.** A dataset's
INTRINSIC system is its level-0 pixel grid: axes with names and semantic types,
never units. It is always known, never wrong, and never revised, which is why
ROIs and anchors resolve against it. Physical space enters the model exactly
once, as a *calibration*: a PHYSICAL system (axes carrying the units) plus one
edge mapping intrinsic pixels into it. Refining a calibration bumps that edge's
version; nothing drawn in pixels moves. The same discipline applies to any
future channel-dependent correction (chromatic drift): a dataset-level fact --
one ``aligned`` system plus one channel-wise edge -- never per-view state on a
lens or a layer.

**Coordinate systems are nodes, not strings.** RFC-5 nests ``{path, name}``
because Zarr has no global identifiers and a system's name is unique only within
its container. We have IDs, so ``input``/``output`` are foreign keys, exposed as
GraphQL node references: cacheable, dedupable, and unable to dangle. The Zarr
writer translates them back to ``{path, name}`` on serialization. The API shape
and the on-disk shape are deliberately not the same document.
"""

from django.contrib.auth import get_user_model
from django.db import models
from django_choices_field import TextChoicesField
from authentikate.models import Organization
from koherent.fields import ProvenanceField
from datalayer.models import ParquetStore

from core import enums


class CoordinateSystem(models.Model):
    """A named coordinate space: a node in the transformation graph.

    A system owned by a container cascades with it -- an ARRAY system with its
    pyramid level, an INTRINSIC or PHYSICAL system with its dataset, a lens'
    system with the lens, a *minted* world with its scene. A hub has no owner.
    The ownership is expressed here rather than as a foreign key on the owner
    because a key in both directions is a cycle: creating a lens would require
    its transformation, which requires its coordinate system, which requires
    the lens.

    It also means the cascade says what we mean. Delete a scene and the world
    minted for it goes with it, but an ROI drawn against a dataset's intrinsic
    system is untouched -- an ROI belongs to a coordinate system, not to a scene.
    Ownership is distinct from *use*: which space a scene composes over is
    ``Scene.world``, and a scene adopting a shared hub sets no FK here at all --
    the hub stays ownerless and outlives the scene.

    There is deliberately no stored ``kind`` column: what a system denotes is a
    function of which owner FK is set, and a second, unconstrained copy of that
    fact was free to contradict the one the cascade enforces. ``kind`` below
    derives it instead.
    """

    name = models.CharField(max_length=255, help_text="The name of the coordinate system, unique within its container rather than globally")

    intrinsic_of = models.OneToOneField(
        "ADataset",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="intrinsic_system",
        help_text="The dataset whose INTRINSIC (level-0 pixel grid) space this is. One-to-one: the DB itself enforces one intrinsic system per dataset",
    )
    dataset = models.ForeignKey(
        "ADataset",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="calibrations",
        help_text="The dataset this PHYSICAL (calibrated) space belongs to. A dataset can carry many calibrations -- stage space, specimen space, a re-calibration -- and they cascade with it",
    )
    data_array = models.OneToOneField(
        "DataArray",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="coordinate_system",
        help_text="The pyramid level whose ARRAY (voxel index) space this is",
    )
    lens = models.OneToOneField(
        "Lens",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="coordinate_system",
        help_text="The lens whose (cropped) space this is",
    )
    scene = models.OneToOneField(
        "Scene",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="world_coordinate_system",
        help_text="The scene this world was minted for and cascades with. Ownership only: which space a scene composes over is Scene.world, and an adopted hub leaves this null",
    )
    # A collection owns its space rather than borrowing the dataset's, and how the two
    # relate is an edge. Borrowing forced the vertices to be exactly in the dataset's
    # pixel grid and gave the geometry nowhere to say otherwise; an edge can say "these
    # meshes were extracted from a half-resolution grid" -- and can also say, for a
    # feature table, that nothing corresponds at all.
    mesh_collection = models.OneToOneField(
        "MeshCollection",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="coordinate_system",
        help_text="The mesh collection whose vertex space this is",
    )
    table_dataset = models.OneToOneField(
        "TableDataset",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="coordinate_system",
        help_text="The table dataset whose row/coordinate space this is",
    )
    annotation_collection = models.OneToOneField(
        "AnnotationCollection",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="coordinate_system",
        help_text="The annotation collection whose drawing space this is",
    )

    epoch = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "The wall-clock instant this system's time axis has its origin at, so that "
            "`wall_clock = epoch + t * unit`. A property of the *space*, not of any composition over it -- "
            "two scenes sharing one space cannot disagree about when its clock starts. Meaningful only for "
            "a calibrated system with a TIME axis (a scene's world, a shared hub); optional even there: an "
            "unanchored clock is still a perfectly composable relative coordinate"
        ),
    )

    # Every owner FK above is nullable, and core.scoping._find_org_path follows
    # only non-null FKs -- so without this column the model has no path to an
    # organization and every scoped read raises LookupError.
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, help_text="The organization this coordinate system belongs to")
    creator = models.ForeignKey(get_user_model(), on_delete=models.SET_NULL, null=True, blank=True, help_text="The user that created this coordinate system")
    created_at = models.DateTimeField(auto_now_add=True, help_text="The time this coordinate system was created")

    provenance = ProvenanceField()

    @property
    def kind(self) -> enums.CoordinateSystemKind:
        """What this system denotes, derived from which owner FK is set.

        A collection's native space is INTRINSIC exactly like a dataset's pixel
        grid: the container's own, always-defined space. Only ``intrinsic_of``
        marks *the* grid geometry anchors to -- walks that need that (see
        :func:`core.logic.graph.path_to_intrinsic`) test the FK, not this label.
        """
        if self.intrinsic_of_id or self.mesh_collection_id or self.table_dataset_id or self.annotation_collection_id:
            return enums.CoordinateSystemKind.INTRINSIC
        if self.data_array_id or self.lens_id:
            return enums.CoordinateSystemKind.ARRAY
        if self.dataset_id:
            return enums.CoordinateSystemKind.PHYSICAL
        return enums.CoordinateSystemKind.SHARED

    @property
    def is_adoptable_world(self) -> bool:
        """Whether a scene may compose over this system as its world.

        Everything qualifies except two refusals, each for its own reason. An ARRAY
        system (a pyramid level's grid, a lens' crop) is a *slice of* a space, not a
        space to compose in -- its container's intrinsic system is one hop away and is
        the honest root. And another scene's minted world cascades with its scene, so
        adopting it would let that scene delete the world out from under this one; a
        space shared between scenes is a hub, which nobody owns.

        A scene over an *owned* root (a dataset's intrinsic pixels, a calibration, a
        collection's vertex space) composes that container's fact tree only:
        registrations land exclusively on SHARED spaces, so nothing unrelated can be
        claimed into it -- composing foreign data means a hub. And Scene.world is
        RESTRICT: the container becomes undeletable while a scene is rooted in its
        space, exactly as a hub is.
        """
        return not any((self.scene_id, self.data_array_id, self.lens_id))

    @property
    def is_hub(self) -> bool:
        """An ownerless shared space, built to be registered into.

        The one kind of system created bare (``createCoordinateSystem``), and the only
        kind of adoptable world that can *receive registrations*: a scene's own world
        is SHARED too, but it is scene-owned and cascades away with its scene.
        """
        return not any(
            (
                self.intrinsic_of_id,
                self.dataset_id,
                self.data_array_id,
                self.lens_id,
                self.scene_id,
                self.mesh_collection_id,
                self.table_dataset_id,
                self.annotation_collection_id,
            )
        )

    def __str__(self) -> str:
        """The system's name and derived kind."""
        return f"{self.name} ({self.kind.value})"


class Axis(models.Model):
    """One named, typed dimension of a coordinate system.

    ``order`` is this axis' position in the system's canonical axis order, and that
    identity is load-bearing: it is what makes "the last spatial axis is x" a
    well-defined statement. For an array-backed system (INTRINSIC/ARRAY) that
    position is the index into the array shape, and it is what ties ``scale[i]`` to
    ``shape[i]``; for a TABLE system it is the canonical order of the coordinate
    columns, and no shape exists to index. Nothing recovers it if it drifts, so it
    is enforced unique per system and always written by enumeration, never supplied
    by a caller.

    The axes of a system must be ordered by type -- time first, then channel and
    custom types, then space (an RFC-5 inheritance). That is validated at ingest
    by :func:`core.logic.coords.assert_axis_type_order`, not merely asserted in a
    test: the derivation of the render axes is unsound without it. Axis *names*
    are free-form ("z", "tau"), and ``zyx`` ordering among the spatial axes is
    only a convention.
    """

    coordinate_system = models.ForeignKey(CoordinateSystem, on_delete=models.CASCADE, related_name="axes", help_text="The coordinate system this axis belongs to")
    order = models.PositiveSmallIntegerField(help_text="This axis' position in the system's canonical axis order. For an array-backed system it is the index into the array shape; for a table system it is the order of the coordinate columns")
    name = models.CharField(max_length=32, help_text="The name of the axis, e.g. 'z', 'c' or 'tau'. Free-form")
    type = TextChoicesField(
        choices_enum=enums.AxisTypeChoices,
        default=enums.AxisTypeChoices.SPACE.value,
        help_text="The semantic kind of the axis, which fixes its position in the axis ordering and drives render-axis derivation",
    )
    unit = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="The physical unit of the axis, e.g. 'micrometer'. A pint unit (the kanne `Unit` scalar), validated on write; 'a.u.' for arbitrary units. Set on calibrated (PHYSICAL/WORLD/ATLAS) axes, always null on pixel (INTRINSIC/ARRAY) axes",
    )
    long_name = models.CharField(max_length=255, null=True, blank=True, help_text="A human-readable name for the axis")
    description = models.CharField(max_length=1000, null=True, blank=True, help_text="A free-form description of what the axis measures, e.g. 'distance from the coverslip'")

    class Meta:
        """Meta options for the axis."""

        ordering = ["order"]
        unique_together = [("coordinate_system", "order"), ("coordinate_system", "name")]
        constraints = [
            # A system carries at most one clock. Two TIME axes are otherwise legal --
            # they share an ordering rank, so nothing complains -- and the render-axis
            # derivation silently picks the first and drops the second. A partial unique
            # index, so the rule holds against a write that skips the validation.
            models.UniqueConstraint(
                fields=["coordinate_system"],
                condition=models.Q(type=enums.AxisTypeChoices.TIME.value),
                name="one_time_axis_per_coordinate_system",
            ),
        ]

    def __str__(self) -> str:
        """The axis' name and type."""
        return f"{self.name} ({self.type})"


class Transformation(models.Model):
    """A directed edge of the coordinate graph: a map from ``input`` to ``output``.

    One table, discriminated by ``kind``, with the parameters in JSON -- the same
    shape as ``Layer``, and for the same reason. In GraphQL it is an interface
    whose concrete types unpack ``params`` into typed fields.

    **Direction is always forward: input to output.** Registration libraries
    routinely hand you the inverse map; normalize it at ingest rather than
    recording the direction, or half the graph will point the wrong way and
    nothing will tell you.

    **Not every edge is a map.** An ``UNMAPPABLE`` edge asserts the opposite: the
    two systems are related, and no point of either corresponds to a point of the
    other. It takes no parameters, is bound by no rank, and
    :func:`core.logic.graph.is_traversable` refuses it to every placement search --
    in both directions. It may not be a wrapper child: a SEQUENCE one of whose
    steps maps nothing maps nothing, and would be better written as the one edge
    it is.

    Two limits worth naming, because a reader will assume they were handled.
    Whether an edge can be walked *backwards* is decided by kind and rank
    (:func:`core.logic.graph.is_reverse_traversable`), which is metadata -- so a
    square but **singular** AFFINE (a projection written as a matrix, ``[1,1,0]``)
    is still offered for inversion, and only a determinant would catch it. And a
    FIELD has no closed-form inverse at any rank, which is why kind, and not rank
    alone, decides.
    """

    kind = TextChoicesField(
        choices_enum=enums.TransformKindChoices,
        default=enums.TransformKindChoices.IDENTITY.value,
        help_text="The kind of transformation, which fixes how `params` is interpreted",
    )
    name = models.CharField(max_length=255, null=True, blank=True, help_text="The name of the transformation")

    # Null only for a child of a SEQUENCE / BY_DIMENSION / BIJECTION wrapper --
    # RFC-5 permits omitting them there, because the wrapper supplies them.
    input = models.ForeignKey(CoordinateSystem, on_delete=models.CASCADE, null=True, blank=True, related_name="+", help_text="The coordinate system this transformation maps from")
    output = models.ForeignKey(CoordinateSystem, on_delete=models.CASCADE, null=True, blank=True, related_name="+", help_text="The coordinate system this transformation maps to")

    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="children", help_text="The wrapping SEQUENCE / BY_DIMENSION / BIJECTION transformation, if this is a child")
    order = models.PositiveSmallIntegerField(default=0, help_text="The position of this child within its wrapping SEQUENCE, applied first to last")

    # BY_DIMENSION only: which axes this child acts on, by NAME. RFC-5's
    # transformation table says List[str] while its byDimension prose says
    # integer indices into the axes; the two contradict. Names are
    # self-documenting and survive a reordering, so we use names.
    input_axes = models.JSONField(null=True, blank=True, help_text="(byDimension) The names of the input axes this child acts on, e.g. ['z', 'y', 'x']")
    output_axes = models.JSONField(null=True, blank=True, help_text="(byDimension) The names of the output axes this child produces")

    params = models.JSONField(
        default=dict,
        help_text="The transformation's parameters, keyed by kind: SCALE {'scale': [...]}, TRANSLATION {'translation': [...]}, AFFINE {'affine': [[...], ...]} (M x (N+1), rows outermost), UNMAPPABLE {'reason': '...'} (optional, purely descriptive)",
    )

    # An edge fact, deliberately: it used to be a column on the layer, where two layers
    # over one dataset carried two copies of how-known one registration is, free to
    # disagree -- and nothing ever wrote it. A layer's validity is now derived: the
    # weakest edge on its path to world.
    validity = TextChoicesField(
        choices_enum=enums.PlacementValidityChoices,
        default=enums.PlacementValidityChoices.VALIDATED.value,
        help_text=(
            "How much this map is actually known. VALIDATED is the default because most edges are derived "
            "by the server from shapes and slices -- exact by construction. A writer that merely reads "
            "metadata says INFERRED, one that records an authored registration says MANUAL, and an edge "
            "the server assumed says UNKNOWN"
        ),
    )
    value_relation = TextChoicesField(
        choices_enum=enums.ValueRelationChoices,
        null=True,
        blank=True,
        help_text=(
            "What the derivation this edge records did to the *values* -- the axis the spatial kind says "
            "nothing about: a threshold is spatially IDENTITY with CATEGORIZED values, a crop is "
            "value-IDENTICAL, a deconvolution TRANSFORMED. One derivation event, one row, two orthogonal "
            "statements -- never a parallel table. Null means unstated. Meaningful only on a derivation "
            "(cross-container fact) edge: a registration relates spaces, and values do not cross it"
        ),
    )

    # FIELD only: the array whose values are the map. A *node*, not a store hanging
    # off this edge. The array is data before it is a map -- a label mask has its own
    # lineage, provenance and placement -- and a payload cannot carry any of that. It
    # also cannot carry axes, which is what left AxisType.COORDINATE and
    # AxisType.DISPLACEMENT dead in the enum: the fact "my values are offsets" had no
    # array to sit on. As a node it does, and this edge reads it rather than restating
    # it. Matches DataArray, which owns a system and reaches its dataset's intrinsic
    # space through a stored Transformation: arrays are nodes; edges relate their spaces.
    #
    # **Null means the input is its own field** -- a label mask, whose pixels are the map
    # of the space they index. The same shape as a level-0 DataArray owning no system and
    # an unsliced Lens owning no system: when the answer would be "that one, there", this
    # codebase stores nothing and lets the definition carry it. It is not only an idiom
    # here, it is load-bearing. PROTECT is right for a *separate* array -- deleting a warp
    # field would take a registration nobody named -- but a self-dereference is a fact
    # ABOUT the mask, which `input`'s CASCADE already removes with it. Written as a real
    # self-FK, PROTECT would win that race and the mask could never be deleted at all.
    # Read it through `effective_field`, never directly.
    field = models.ForeignKey(
        CoordinateSystem,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="fields_of",
        help_text="(FIELD) The coordinate system of the array whose values are this map, when that array is a separate one (a warp field). Null when the input is its own field, as for a label mask whose pixels are the map. Its value axis (COORDINATE or DISPLACEMENT) says whether the values are positions or offsets; no value axis means scalar, and scalar means positions",
    )

    @property
    def effective_field(self) -> "CoordinateSystem | None":
        """The array whose values are this map: the `field`, or the input when it is its own.

        The one reader of the null-means-self convention above. Everything that resolves a
        FIELD's map goes through here, so the convention lives in exactly one place.
        """
        if self.kind != enums.TransformKindChoices.FIELD.value:
            return None
        return self.field or self.input

    # Bumped when a registration is refined. ROIs record the version they were
    # authored against as provenance; it is never used to resolve a coordinate.
    version = models.PositiveIntegerField(default=1, help_text="Incremented whenever this transformation's parameters are refined")

    # See CoordinateSystem.organization: a wrapper child has input, output and
    # every non-self FK null, so there is no path to an organization without it.
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, help_text="The organization this transformation belongs to")
    creator = models.ForeignKey(get_user_model(), on_delete=models.SET_NULL, null=True, blank=True, help_text="The user that created this transformation")
    created_at = models.DateTimeField(auto_now_add=True, help_text="The time this transformation was created")

    provenance = ProvenanceField()

    class Meta:
        """Meta options for the transformation."""

        ordering = ["order", "id"]

    def __str__(self) -> str:
        """The transformation's kind and endpoints."""
        return f"{self.kind}: {self.input_id} -> {self.output_id}"


class MeshCollection(models.Model):
    """An immutable, versioned collection of meshes, addressed by store rather than by row.

    The collection resolves to a **Parquet store** and a schema; the client asks the
    datalayer for temporary read credentials and queries the Parquet directly (e.g.
    with DuckDB). It is the same upload path every other Parquet object in the
    system takes -- the client requests a presigned upload, writes the object, and
    hands back the store id. A bare URL would sit outside the datalayer: nothing
    would grant read access to it, nothing would scope it to an organization, and
    nothing would clean it up.

    It deliberately exposes no ``meshes`` field: a paginated list would look
    natural, someone would build a UI on it, and it would end up walking tens of
    millions of Parquet rows through GraphQL to feed a render loop.

    **It owns its coordinate system** (``CoordinateSystem.mesh_collection``, read
    back here as ``.coordinate_system``), and an edge relates that system to the
    dataset the meshes were extracted from. It used to *borrow* the dataset's
    intrinsic system, which forced the vertices to be exactly in that pixel grid
    and left the geometry nowhere to say otherwise -- extract from a
    half-resolution grid and the only honest options were to rewrite every vertex
    or to store a scale factor somewhere no query could find it. As an edge it is
    a fact like any other: an identity when the grids agree, a scale when they do
    not, and refinable without touching a vertex. The edge is *optional*: a mesh in
    some absolute space, belonging to no dataset, simply has none.
    """

    version = models.CharField(max_length=64, help_text="The immutable version of this collection, e.g. 'v20260713-a3f9'")
    spec_version = models.CharField(max_length=64, help_text="The version of the mesh encoding specification this collection conforms to")

    # cellSize is IN VOXELS, so that the octree aligns to the label grid it was
    # extracted from rather than to an arbitrary physical box.
    grid = models.JSONField(default=dict, help_text="The octree grid, e.g. {'cellSize': [64, 64, 64], 'levels': 5, 'sortKey': 'MORTON'}. cellSize is in voxels of the coordinate system")
    encoding = models.JSONField(default=dict, help_text="The geometry encoding, e.g. {'positions': 'UINT16_QUANTIZED_PER_CELL', 'normals': 'OCT16', 'indices': 'UINT16', 'codec': 'MESHOPT', 'compression': 'ZSTD'}")
    catalog = models.ForeignKey(
        ParquetStore,
        on_delete=models.CASCADE,
        related_name="mesh_catalogs",
        help_text="The Parquet store holding the catalog that describes the meshes in this collection. The client reads it directly with a datalayer access grant",
    )
    geometry = models.ManyToManyField(
        ParquetStore,
        related_name="mesh_geometries",
        blank=True,
        help_text="The Parquet stores holding the geometry shards. Sharded because a collection's geometry does not fit in one object, and a renderer only ever wants the cells in view",
    )
    provenance_metadata = models.JSONField(default=dict, help_text="How this collection was produced (the extraction run, its parameters and its inputs)")

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, help_text="The organization this mesh collection belongs to")
    creator = models.ForeignKey(get_user_model(), on_delete=models.SET_NULL, null=True, blank=True, help_text="The user that created this mesh collection")
    created_at = models.DateTimeField(auto_now_add=True, help_text="The time this mesh collection was created")

    provenance = ProvenanceField()

    class Meta:
        """Meta options for the mesh collection."""

        # No `unique_together` on (coordinate_system, version) any more: the system is
        # this collection's own, so the pair was unique by construction and the
        # constraint said nothing. What it used to mean -- one version per anchor --
        # is now a statement about the *anchor edge*, and the graph does not enforce
        # uniqueness on edges anywhere else either.
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """The collection's version."""
        return f"MeshCollection {self.version}"
