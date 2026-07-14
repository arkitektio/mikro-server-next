import uuid

from django.db import models
from django.contrib.auth import get_user_model
from core import enums
from koherent.fields import ProvenanceField
from django_choices_field import TextChoicesField
from authentikate.models import Organization
from django.db.models import Q
from datalayer.models import ZarrStore
from django.contrib.postgres.indexes import GinIndex
from core import base_models
from core.logic import coords as coords_logic
from core.models.coords import CoordinateSystem, Transformation, MeshCollection  # noqa: F401  (re-exported via core.models)


class ADataset(models.Model):
    """A multi-dimensional array of data, with one or more pyramid levels attached as DataArrays.

    The dataset's dimensions and their types live on the axes of its INTRINSIC
    :class:`~core.models.CoordinateSystem` -- its level-0 pixel grid -- and its
    shape is the shape of its level-0 array. Physical units live on its
    calibrations (PHYSICAL systems), never here. None of it is duplicated on
    columns: the properties below derive it, so there is no second copy that can
    disagree. That includes ``multiscale``, which is simply "more than one level".
    """

    name = models.CharField(max_length=1000, help_text="The name of the data source")
    description = models.CharField(max_length=1000, help_text="The description of the data source", null=True)

    created_at = models.DateTimeField(auto_now_add=True, help_text="The time the data source was created")
    creator = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, null=True, blank=True, help_text="The user that created the data source")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, help_text="The organization the data source belongs to")
    created_through = models.ForeignKey(
        "koherent.Task",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_%(class)ss",
        help_text="The task this object was created through, if any",
    )
    created_through_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_%(class)ss",
        help_text="The assigner of the creating task, denormalized for fast filtering",
    )
    provenance = ProvenanceField()

    @property
    def intrinsic_coordinate_system(self):
        """The dataset's level-0 pixel grid: the system every pyramid level and lens maps into."""
        # The reverse of CoordinateSystem.intrinsic_of, which raises rather than
        # returning None when the system has not been created yet.
        return getattr(self, "intrinsic_system", None)

    @property
    def multiscale(self) -> bool:
        """Whether this dataset carries a resolution pyramid. Derived: more than one level."""
        return self.data_arrays.count() > 1

    @property
    def axes(self) -> list:
        """The dataset's axes, in array order."""
        system = self.intrinsic_coordinate_system
        return list(system.axes.all()) if system else []

    @property
    def axis_specs(self) -> list[coords_logic.AxisSpec]:
        """The dataset's axes, coerced for :mod:`core.logic.coords`."""
        return [coords_logic.AxisSpec(name=axis.name, type=axis.type) for axis in self.axes]

    @property
    def dims_list(self) -> list:
        """The dataset's dimension names, in array order. Derived from the intrinsic axes."""
        return [axis.name for axis in self.axes]

    @property
    def shape_list(self) -> list:
        """The dataset's shape: that of its level-0 array."""
        base = self.data_arrays.order_by("level").first()
        return base.shape if base and isinstance(base.shape, list) else []


class DataArray(models.Model):
    """One level of a dataset's resolution pyramid: a zarr-backed array.

    Its voxel-index space is an ARRAY :class:`~core.models.CoordinateSystem`, and
    the map from that space into the dataset's intrinsic space is a stored
    :class:`~core.models.Transformation`. Every level maps into the *same*
    intrinsic system -- a star, not a chain -- so no level's placement depends on
    another's.

    The old ``scale_factors`` column is gone. It stored *nominal* factors
    (1, 2, 4, 8, ...), which a real pyramid does not obey: a 36-voxel axis floors
    to 36, 18, 9, 4, 2, 1, whose true factors are 1, 2, 4, 9, 18, 36. The
    absolute scale is now derived from the actual shapes at write time, by
    :func:`core.logic.coords.pyramid_transform`, and stored on the edge.
    """

    store = models.ForeignKey(
        ZarrStore,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="The store of the data array",
    )
    shape = models.JSONField(help_text="The shape of the data array")
    chunk_shape = models.JSONField(help_text="The chunk shape of the data array")

    dataset = models.ForeignKey(ADataset, on_delete=models.CASCADE, related_name="data_arrays")
    level = models.IntegerField(help_text="The level of the data array in the resolution pyramid, 0 being the highest resolution")

    class Meta:
        """Meta options for the data array."""

        # Everything -- the dataset's shape, the lens edges, the pyramid
        # derivation -- keys off "the level-0 array". Two arrays claiming the
        # same level would make all of it silently ambiguous.
        constraints = [
            models.UniqueConstraint(fields=["dataset", "level"], name="one_data_array_per_level"),
        ]

    @property
    def to_parent(self):
        """The stored edge from this level's voxel space into the dataset's intrinsic space."""
        system = getattr(self, "coordinate_system", None)
        return Transformation.objects.filter(input=system).first() if system else None


# ==========================================
# 2. THE HUB & SPOKES (Metadata)
# ==========================================


class CoordinateAnchor(models.Model):
    """The Axis-Agnostic Hub."""

    id = models.BigAutoField(primary_key=True)
    dataset = models.ForeignKey(ADataset, related_name="anchors", on_delete=models.CASCADE)
    coordinates = models.JSONField(
        default=dict,
        help_text="The coordinates this anchor is pinned to, keyed by axis name, e.g. {'c': 0, 't': 5}. Level-0 pixel indices (the dataset's INTRINSIC space). An omitted axis means global along it",
    )

    class Meta:
        indexes = [GinIndex(fields=["coordinates"], name="anchor_coords_gin")]


class OptikitState(models.Model):
    """1:1 Spoke (Hardware Truth)"""

    anchor = models.OneToOneField(CoordinateAnchor, related_name="microscope", on_delete=models.CASCADE)
    state = models.JSONField(default=dict)


class OmeMetadata(models.Model):
    """N:1 Spoke (Image Truth)"""

    anchor = models.OneToOneField(CoordinateAnchor, related_name="ome_metadata", on_delete=models.CASCADE)
    metadata = models.JSONField(default=dict)


class ValueHistogram(models.Model):
    """N:1 Spoke (Pixel Value Distribution)"""

    anchor = models.OneToOneField(CoordinateAnchor, related_name="value_histogram", on_delete=models.CASCADE)
    histogram = models.JSONField(default=list, help_text="The histogram of the pixel values (y values)")
    bins = models.JSONField(default=list, help_text="The bin indices of the histogram (x values)")
    min = models.FloatField(help_text="The minimum pixel value of the histogram", null=True, blank=True)
    max = models.FloatField(help_text="The maximum pixel value of the histogram", null=True, blank=True)
    p1 = models.FloatField(help_text="The first percentile of the pixel values", null=True, blank=True)
    p99 = models.FloatField(help_text="The 99th percentile of the pixel values", null=True, blank=True)


class ChannelLabel(models.Model):
    """N:1 Spoke (Channel Truth)"""

    anchor = models.OneToOneField(CoordinateAnchor, related_name="channel_label", on_delete=models.CASCADE)
    label = models.CharField(max_length=1000, help_text="The label of the channel", null=True, blank=True)


class LightPath(models.Model):
    """N:1 Spoke (Light Path Truth)"""

    anchor = models.OneToOneField(CoordinateAnchor, related_name="light_graph", on_delete=models.CASCADE)
    graph = models.JSONField(default=dict)


class OmePlaneMetadata(models.Model):
    """N:1 Spoke (Plane Truth)"""

    anchor = models.OneToOneField(CoordinateAnchor, related_name="ome_plane_metadata", on_delete=models.CASCADE)
    plane_metadata = models.JSONField(default=dict)


class Lens(models.Model):
    """A selection over a dataset. Nothing else.

    Its shape and dimensions are derived from the dataset and the slices -- they
    were columns, and two people computing them from the same slices are
    guaranteed to agree, so there was no reason for a second copy that could
    drift.

    The lens has its own coordinate system, and the edge back to the dataset is a
    stored :class:`~core.models.Transformation`. Before that, slicing shifted
    voxel coordinates and nothing recorded the shift: an ROI drawn on a cropped
    lens had no defined path back to its dataset.
    """

    dataset = models.ForeignKey(ADataset, on_delete=models.CASCADE, related_name="lenses")
    slices = models.JSONField(help_text="The selection this lens makes over its dataset, as a list of per-dimension slices", default=list)

    provenance = ProvenanceField()

    @property
    def slices_list(self) -> list[base_models.SliceModel]:
        """Return the slices of the lens as a list."""
        return [base_models.SliceModel(**slice_dict) for slice_dict in self.slices] if isinstance(self.slices, list) else []

    @property
    def dims_list(self) -> list:
        """The lens' dimension names. A selection never drops or reorders an axis."""
        return self.dataset.dims_list

    @property
    def axis_specs(self) -> list[coords_logic.AxisSpec]:
        """The lens' axes, coerced for :mod:`core.logic.coords`."""
        return self.dataset.axis_specs

    @property
    def shape_list(self) -> list:
        """The shape this lens' slices cut out of its dataset."""
        return coords_logic.lens_shape(self.dataset.shape_list, self.dataset.dims_list, self.slices_list)

    @property
    def to_parent(self):
        """The stored edge from this lens' space back into its dataset's level-0 voxel space."""
        system = getattr(self, "coordinate_system", None)
        return Transformation.objects.filter(input=system).first() if system else None

    def get_size_of_dim(self, dim_name: str) -> int:
        """Get the size of a dimension by its name."""
        dims, shape = self.dims_list, self.shape_list
        try:
            return shape[dims.index(dim_name)]
        except ValueError as error:
            raise ValueError(f"Dimension {dim_name} not found in lens dimensions {dims}.") from error

    @property
    def active_anchors(self):
        """
        THE WORKSPACE QUERY:
        Finds all anchors that fall within the boundaries of this Lens.
        Respects the "Axis-Agnostic" rule: If an anchor is global ({})
        or partial ({"c": 0}), it is included as long as it doesn't contradict the Lens.
        """
        qs = CoordinateAnchor.objects.filter(dataset=self.dataset)

        # Loop through the dimensional constraints of the Lens
        for slc in self.slices_list:
            dim = slc.dim

            # Condition A: The anchor is global for this dimension (key doesn't exist)
            dim_is_global = ~Q(coordinates__has_key=dim)

            if slc.start is not None and slc.stop is not None:
                dim_in_range = Q(**{f"coordinates__{dim}__gte": slc.start, f"coordinates__{dim}__lt": slc.stop})
            else:
                continue  # Failsafe for unhandled slice types

            # The anchor must either be global for this axis, OR fall inside the slice limits
            qs = qs.filter(dim_is_global | dim_in_range)

        # OPTIMIZATION: prefetch/select the spokes to prevent N+1 database death
        return qs.select_related("microscope").prefetch_related("ome_metadata", "value_histogram", "ome_plane_metadata")

    def get_anchors_at_view(self, current_view: dict):
        """
        THE SCRUBBING QUERY:
        Used by the frontend when scrubing the timeline/Z-stack.
        Leverages the high-speed GIN Index for sub-millisecond subset matching.

        Args:
            current_view (dict): e.g., {"c": 0, "t": 5, "z": 10}
        """
        # The `<@` (contained_by) operator instantly matches global {}, channel {"c":0},
        # and exact {"c":0, "t":5} anchors simultaneously.
        qs = CoordinateAnchor.objects.filter(dataset=self.dataset, coordinates__contained_by=current_view)

        return qs.select_related("microscope").prefetch_related("ome_metadata", "value_histogram", "ome_plane_metadata")


class Scene(models.Model):
    """A composition of layers over a shared WORLD coordinate system.

    The scene carries no units: they are per-axis, on the axes of its world
    system. It carries no affine either -- the map to a parent scene is an edge
    between the two scenes' world systems, like every other spatial fact.

    ``coordinate_transformations`` is the scene's membership set: which edges are
    part of *this* composition. An edge exists independently of any scene (it is
    a fact about two coordinate systems), so membership is a separate statement
    from the edge itself.
    """

    name = models.CharField(max_length=255)
    blending = TextChoicesField(
        choices_enum=enums.BlendingChoices,
        default=enums.BlendingChoices.ADDITIVE.value,
        help_text="The blending of the scene",
    )
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="subscenes")
    coordinate_transformations = models.ManyToManyField(
        "Transformation",
        blank=True,
        related_name="scenes",
        help_text="The transformation edges that belong to this scene, e.g. the registrations placing each layer's dataset into the scene's world system",
    )
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    provenance = ProvenanceField()


class Layer(models.Model):
    """View state, and the unit that gets alpha-blended. No spatial fields.

    A single table discriminated by ``kind``: it carries the shared placement and
    compositing settings plus the source and render settings for every layer kind
    (image / shape / point / track / mesh). Exactly one source FK is set per kind,
    enforced by the create mutations. In GraphQL this one model is exposed as a
    ``Layer`` interface with concrete ``ImageLayer``/``ShapeLayer``/``PointLayer``/
    ``TrackLayer``/``MeshLayer`` types resolved by ``kind``.

    The layer no longer carries an ``affine_matrix``. Registration belongs to the
    dataset, not to a view of it: two layers over one dataset used to carry two
    copies of one matrix, free to disagree. It is now a scene-level
    :class:`~core.models.Transformation` edge. Nor does it carry ``x_dim`` and
    friends -- those follow from the axis types, and are derived by
    :func:`core.logic.coords.resolve_render_axes`.
    """

    # --- shared placement / compositing ---
    scene = models.ForeignKey(Scene, related_name="layers", on_delete=models.CASCADE)
    kind = TextChoicesField(
        choices_enum=enums.LayerKindChoices,
        default=enums.LayerKindChoices.IMAGE.value,
        help_text="The kind of layer, discriminating its data source and render settings",
    )
    status = TextChoicesField(
        choices_enum=enums.PlacementStatus,
        default=enums.PlacementStatus.ACTIVE.value,
        help_text="The status of the placement",
    )
    validity = TextChoicesField(
        choices_enum=enums.PlacementValidity,
        default=enums.PlacementValidity.UNKNOWN.value,
        help_text="The validity of the placement",
    )
    blending = TextChoicesField(
        choices_enum=enums.BlendingChoices,
        default=enums.BlendingChoices.ADDITIVE.value,
        help_text="The blending mode used to composite this layer over the layers below it",
    )
    opacity = models.FloatField(default=1.0, help_text="Layer alpha for alpha-over compositing (0..1)")
    visible = models.BooleanField(default=True, help_text="Whether the layer participates in compositing")
    order = models.IntegerField(default=0, help_text="Explicit z-index for deterministic back-to-front compositing")

    # --- source references (exactly one set, per kind) ---
    lens = models.ForeignKey(Lens, on_delete=models.CASCADE, related_name="layers", null=True, blank=True, help_text="(image) The lens that defines the array data source and constraints")
    data_roi = models.ForeignKey("DataRoi", on_delete=models.CASCADE, related_name="shape_layers", null=True, blank=True, help_text="(shape) The data ROI whose vectors this layer renders")
    table = models.ForeignKey("Table", on_delete=models.CASCADE, related_name="table_layers", null=True, blank=True, help_text="(point/track) The table whose columns provide the coordinates and attributes")
    mesh = models.ForeignKey("Mesh", on_delete=models.CASCADE, related_name="mesh_layers", null=True, blank=True, help_text="(mesh) The mesh whose geometry this layer renders")
    mesh_collection = models.ForeignKey(
        "MeshCollection",
        on_delete=models.CASCADE,
        related_name="mesh_layers",
        null=True,
        blank=True,
        help_text="(mesh) The versioned, coordinate-system-anchored mesh collection this layer renders",
    )
    coordinate_system = models.ForeignKey(
        "CoordinateSystem",
        on_delete=models.CASCADE,
        related_name="anchored_layers",
        null=True,
        blank=True,
        help_text="(point/track) The coordinate system the table's coordinate columns are expressed in. Without it a point cloud sits in an undefined space and cannot be registered through the graph",
    )

    # --- image / volume render settings ---
    render_graph = models.JSONField(null=True, blank=True, default=None, help_text="(image) The composable render recipe (channels + transfer functions + in-layer blend) that is the single source of truth for how the image layer is rendered.")
    colormap = TextChoicesField(choices_enum=enums.ColorMapChoices, default=enums.ColorMapChoices.VIRIDIS.value, help_text="(point/track) The applying color map", null=True, blank=True)

    # --- shape render settings ---
    stroke_color = models.JSONField(default=None, null=True, blank=True, help_text="(shape) The stroke (outline) color of the geometry (RGBA)")
    fill_color = models.JSONField(default=None, null=True, blank=True, help_text="(shape) The fill color of the geometry (RGBA), or null for no fill")
    stroke_width = models.FloatField(null=True, blank=True, help_text="(shape) The stroke width of the geometry, in scene units")
    filled = models.BooleanField(default=False, help_text="(shape) Whether the geometry is filled with fill_color")

    # --- point/track column-name mappings (shared) ---
    x_column = models.CharField(max_length=100, null=True, blank=True, help_text="(point/track) The table column mapped to the x coordinate")
    y_column = models.CharField(max_length=100, null=True, blank=True, help_text="(point/track) The table column mapped to the y coordinate")
    z_column = models.CharField(max_length=100, null=True, blank=True, help_text="(point/track) The table column mapped to the z coordinate")
    t_column = models.CharField(max_length=100, null=True, blank=True, help_text="(point/track) The table column mapped to the time coordinate")
    # --- point-only ---
    size_column = models.CharField(max_length=100, null=True, blank=True, help_text="(point) The table column mapped to per-point size")
    color_column = models.CharField(max_length=100, null=True, blank=True, help_text="(point) The table column mapped to per-point color/intensity (used with colormap)")
    id_column = models.CharField(max_length=100, null=True, blank=True, help_text="(point) The table column identifying each point")
    point_size = models.FloatField(null=True, blank=True, help_text="(point) The default point size, in scene units")
    # --- track-only ---
    track_id_column = models.CharField(max_length=100, null=True, blank=True, help_text="(track) The table column that groups rows into tracks")
    color_by_column = models.CharField(max_length=100, null=True, blank=True, help_text="(track) The table column used to color tracks (used with colormap)")
    line_width = models.FloatField(null=True, blank=True, help_text="(track) The width of the track lines, in scene units")

    # --- mesh render settings ---
    material_color = models.JSONField(default=None, null=True, blank=True, help_text="(mesh) The material (surface) color of the mesh (RGBA)")
    wireframe = models.BooleanField(default=False, help_text="(mesh) Whether the mesh is rendered as a wireframe instead of a solid surface")

    provenance = ProvenanceField()


class DataRoi(models.Model):
    """A region of interest: an addressable, mutable, owned entity in a coordinate system.

    An ROI belongs to a **coordinate system**, not to a scene. There is no
    ``scene_id`` column here and there must never be one: delete the scene and the
    ROI survives, because what the ROI is drawn against -- a dataset's intrinsic
    space, or a lens' cropped space -- has not gone anywhere. The cascade enforces
    this rather than merely documenting it: the ROI's system hangs off the
    *dataset*, so a scene deletion cannot reach it.

    ``intrinsic_bbox`` is the axis-aligned box of the ROI in its dataset's
    intrinsic space, denormalized for joins and culling. It is deliberately *not*
    a world box: world is scene-owned, and the same dataset can sit in two scenes
    under two registrations, so a single stored world box would be wrong in one of
    them. A genuine per-scene box, if it is ever needed, is a resolver that takes
    a scene -- never a column.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    coordinate_system = models.ForeignKey(
        "CoordinateSystem",
        related_name="rois",
        on_delete=models.CASCADE,
        help_text="The coordinate system this ROI's geometry is expressed in, normally a dataset's INTRINSIC system or a lens' system",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    kind = TextChoicesField(
        choices_enum=enums.RoiKindChoices,
        default=enums.RoiKindChoices.PATH.value,
        help_text="The Roi can have vasrying kind, consult your API",
    )
    # The same shape as CoordinateAnchor.coordinates, deliberately: one canonical
    # representation of "pinned to discrete coordinates", and a dict is
    # GIN-indexable so "every ROI on channel 0" is a containment query. The
    # GraphQL type still ships it as a typed [RoiSelector] list.
    selectors = models.JSONField(
        help_text="The discrete coordinates this ROI is pinned to, keyed by axis name, e.g. {'t': 0, 'c': 0}. An axis the ROI does not pin is one it spans",
        default=dict,
    )
    vectors = models.JSONField(help_text="A list of the ROI Vectors (specific for each type), in the coordinate system's own units", default=list)
    intrinsic_bbox = models.JSONField(
        null=True,
        blank=True,
        help_text="The ROI's axis-aligned bounding box in its dataset's intrinsic space, as {'min': [...], 'max': [...]}. Derived from all corners of the geometry, never from min/max alone",
    )
    created_with_transforms = models.PositiveIntegerField(
        default=0,
        help_text="The version of the transformation chain this ROI was authored against. Provenance only: it is never used to resolve a coordinate",
    )
    creator = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="data_rois",
        help_text="The user that drew this ROI",
    )
    created_through = models.ForeignKey(
        "koherent.Task",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_%(class)ss",
        help_text="The task this object was created through, if any",
    )
    created_through_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_%(class)ss",
        help_text="The assigner of the creating task, denormalized for fast filtering",
    )

    provenance = ProvenanceField()


class LineageLink(models.Model):
    """Linking the lineage of data transformations. Each link describes how a target lens was derived from a source lens, optionally using a mask to specify the region of interest and an action to describe the transformation applied."""

    source_lens = models.ForeignKey(Lens, related_name="lineage_links", on_delete=models.CASCADE)
    source_mask = models.ForeignKey(DataRoi, related_name="lineage_links", on_delete=models.CASCADE, null=True, blank=True)
    target_lens = models.ForeignKey(Lens, related_name="lineage_targets", on_delete=models.CASCADE)
    action = models.CharField(max_length=1000, help_text="The action that was used to create the target from the source", null=True, blank=True)
    provenance = ProvenanceField()
