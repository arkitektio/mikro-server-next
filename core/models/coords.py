"""The RFC-5 coordinate system graph.

Coordinate systems are nodes, transformations are directed edges, and every
spatial fact in the array-dataset world is exactly one node or one edge. Voxel
size, pyramid levels, crops, registration and ROIs all live here; nothing else
in the schema carries a duplicate copy of a spatial fact.

Three rules govern this module.

**Edges are facts, paths are queries.** The API ships transformations as
``(input, output, params)`` edges. It does not resolve "to world" and it does
not compose paths server-side: the same dataset can appear in two scenes under
two different registrations, so any single server-side answer would be wrong in
one of them. The client walks the graph and composes.

**Store what was authored or measured; derive everything else.** A registration,
a crop and a calibration took a judgement call, so they are stored. A pyramid
level's absolute scale follows from the shapes and the base spacing, so it is
derived once by :mod:`core.logic.coords` at write time -- and the *result* is
stored, never re-derived at read, so that no two readers can disagree.

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

from core import enums


class CoordinateSystem(models.Model):
    """A named coordinate space: a node in the transformation graph.

    A system is owned by exactly one container and cascades with it -- an ARRAY
    system by its pyramid level, an INTRINSIC system by its dataset, a lens'
    system by the lens, a WORLD system by its scene. An ATLAS system has no
    owner. The ownership is expressed here rather than as a foreign key on the
    owner because a key in both directions is a cycle: creating a lens would
    require its transformation, which requires its coordinate system, which
    requires the lens.

    It also means the cascade says what we mean. Delete a scene and its world
    system goes with it, but an ROI drawn against a dataset's intrinsic system
    is untouched -- an ROI belongs to a coordinate system, not to a scene.
    """

    name = models.CharField(max_length=255, help_text="The name of the coordinate system, unique within its container rather than globally")
    kind = TextChoicesField(
        choices_enum=enums.CoordinateSystemKindChoices,
        default=enums.CoordinateSystemKindChoices.INTRINSIC.value,
        help_text="What this system denotes: voxel indices, a dataset's physical space, or a shared space",
    )

    dataset = models.ForeignKey(
        "ADataset",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="coordinate_systems",
        help_text="The dataset whose INTRINSIC space this is",
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
        help_text="The scene whose WORLD space this is",
    )

    # Every owner FK above is nullable, and core.scoping._find_org_path follows
    # only non-null FKs -- so without this column the model has no path to an
    # organization and every scoped read raises LookupError.
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, help_text="The organization this coordinate system belongs to")
    creator = models.ForeignKey(get_user_model(), on_delete=models.SET_NULL, null=True, blank=True, help_text="The user that created this coordinate system")
    created_at = models.DateTimeField(auto_now_add=True, help_text="The time this coordinate system was created")

    provenance = ProvenanceField()

    class Meta:
        """Meta options for the coordinate system."""

        constraints = [
            models.UniqueConstraint(
                fields=["dataset"],
                condition=models.Q(kind=enums.CoordinateSystemKindChoices.INTRINSIC.value),
                name="one_intrinsic_system_per_dataset",
            )
        ]

    def __str__(self) -> str:
        """The system's name and kind."""
        return f"{self.name} ({self.kind})"


class Axis(models.Model):
    """One named, typed dimension of a coordinate system.

    ``order`` is the index of this axis into the array shape, and that identity
    is load-bearing: it is what ties ``scale[i]`` to ``shape[i]``, and what makes
    "the last spatial axis is x" a well-defined statement. Nothing recovers it if
    it drifts, so it is enforced unique per system and always written by
    enumerating the array shape.

    RFC-5 requires the axes of a system to be ordered by type -- time first, then
    channel and custom types, then space. That is a MUST, and it is validated at
    ingest by :func:`core.logic.coords.assert_axis_type_order`, not merely
    asserted in a test: the derivation of the render axes is unsound without it.
    Axis *names* are free-form ("z", "tau"), and ``zyx`` ordering among the
    spatial axes is only a SHOULD.
    """

    coordinate_system = models.ForeignKey(CoordinateSystem, on_delete=models.CASCADE, related_name="axes", help_text="The coordinate system this axis belongs to")
    order = models.PositiveSmallIntegerField(help_text="The index of this axis into the array shape")
    name = models.CharField(max_length=32, help_text="The name of the axis, e.g. 'z', 'c' or 'tau'. Free-form")
    type = TextChoicesField(
        choices_enum=enums.AxisTypeChoices,
        default=enums.AxisTypeChoices.SPACE.value,
        help_text="The kind of the axis, which fixes its position in the RFC-5 axis ordering",
    )
    unit = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="The physical unit of the axis, e.g. 'micrometer'. A pint unit (the kanne `Unit` scalar), validated on write; 'a.u.' for arbitrary units, null for discrete and index axes",
    )
    discrete = models.BooleanField(default=False, help_text="Whether the axis' coordinates are discrete indices rather than continuous positions")
    long_name = models.CharField(max_length=255, null=True, blank=True, help_text="A human-readable name for the axis")

    class Meta:
        """Meta options for the axis."""

        ordering = ["order"]
        unique_together = [("coordinate_system", "order"), ("coordinate_system", "name")]

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
        help_text="The transformation's parameters, keyed by kind: SCALE {'scale': [...]}, TRANSLATION {'translation': [...]}, AFFINE {'affine': [[...], ...]} (M x (N+1), rows outermost), DISPLACEMENTS {'store_id': '...'}",
    )

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
    """An immutable, versioned collection of meshes, addressed by URL rather than by row.

    The collection resolves to a catalog URL and a schema; the client queries the
    Parquet directly (e.g. with DuckDB). It deliberately exposes no ``meshes``
    field: a paginated list would look natural, someone would build a UI on it,
    and it would end up walking tens of millions of Parquet rows through GraphQL
    to feed a render loop.
    """

    version = models.CharField(max_length=64, help_text="The immutable version of this collection, e.g. 'v20260713-a3f9'")
    spec_version = models.CharField(max_length=64, help_text="The version of the mesh encoding specification this collection conforms to")
    coordinate_system = models.ForeignKey(CoordinateSystem, on_delete=models.CASCADE, related_name="mesh_collections", help_text="The coordinate system the mesh geometry is expressed in, e.g. that of a label array")

    # cellSize is IN VOXELS, so that the octree aligns to the label grid it was
    # extracted from rather than to an arbitrary physical box.
    grid = models.JSONField(default=dict, help_text="The octree grid, e.g. {'cellSize': [64, 64, 64], 'levels': 5, 'sortKey': 'MORTON'}. cellSize is in voxels of the coordinate system")
    encoding = models.JSONField(default=dict, help_text="The geometry encoding, e.g. {'positions': 'UINT16_QUANTIZED_PER_CELL', 'normals': 'OCT16', 'indices': 'UINT16', 'codec': 'MESHOPT', 'compression': 'ZSTD'}")
    catalog_url = models.URLField(max_length=1000, help_text="The URL of the Parquet catalog describing the meshes in this collection")
    geometry_urls = models.JSONField(default=list, help_text="The URLs of the Parquet geometry shards")
    provenance_metadata = models.JSONField(default=dict, help_text="How this collection was produced (the extraction run, its parameters and its inputs)")

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, help_text="The organization this mesh collection belongs to")
    creator = models.ForeignKey(get_user_model(), on_delete=models.SET_NULL, null=True, blank=True, help_text="The user that created this mesh collection")
    created_at = models.DateTimeField(auto_now_add=True, help_text="The time this mesh collection was created")

    provenance = ProvenanceField()

    class Meta:
        """Meta options for the mesh collection."""

        unique_together = [("coordinate_system", "version")]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """The collection's version."""
        return f"MeshCollection {self.version}"
