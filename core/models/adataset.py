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


class ADataset(models.Model):
    """A DataArray is a multi-dimensional array of data that is associated with a sample.

    It can have multiple scales attached to it, which are represented as DataArrays.

    """

    name = models.CharField(max_length=1000, help_text="The name of the data source")
    description = models.CharField(max_length=1000, help_text="The description of the data source", null=True)
    shape = models.JSONField(help_text="The shape of the data source")
    dims = models.JSONField(help_text="The dimensions of the data source (e.g. ['t', 'c', 'z', 'x', 'y'])")
    dim_descriptors = models.JSONField(help_text="The dimension descriptors of the data source", null=True, blank=True)

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
    def shape_list(self) -> list:
        """Return the shape of the data source as a list."""
        return self.shape if isinstance(self.shape, list) else []

    @property
    def dims_list(self) -> list:
        """Return the dimensions of the data source as a list."""
        return self.dims if isinstance(self.dims, list) else []

    @property
    def dim_descriptors_list(self) -> list[base_models.DimDescriptor]:
        """Return the dimension descriptors of the data source as a list."""
        if isinstance(self.dim_descriptors, list):
            return [base_models.DimDescriptor(**desc) for desc in self.dim_descriptors]
        return []


class DataArray(models.Model):
    """A DataArray is a multi-dimensional array of data that is associated with a sample.

    It can have multiple scaless attached to it, which are represented as DataArrays.

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
    scale_factors = models.JSONField(help_text="The scale factor of the data array", null=True, blank=True)

    dataset = models.ForeignKey(ADataset, on_delete=models.CASCADE, related_name="data_arrays")
    level = models.IntegerField(help_text="The level of the data array (for multi-scale data)", null=True, blank=True)


# ==========================================
# 2. THE HUB & SPOKES (Metadata)
# ==========================================


class CoordinateAnchor(models.Model):
    """The Axis-Agnostic Hub."""

    id = models.BigAutoField(primary_key=True)
    dataset = models.ForeignKey(ADataset, related_name="anchors", on_delete=models.CASCADE)
    coordinates = models.JSONField(default=dict)

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
    """A Lens is aw way of looking at a data array."""

    dataset = models.ForeignKey(ADataset, on_delete=models.CASCADE, related_name="lenses")
    slices = models.JSONField(help_text="The constraints of the lens (for filtering data)", default=dict)
    shape = models.JSONField(help_text="The shape of the lens (for reshaping data)")
    dims = models.JSONField(help_text="The dimensions of the lens (e.g. ['t', 'c', 'z', 'x', 'y'])")
    dim_descriptors = models.JSONField(help_text="The dimension descriptors of the lens")

    provenance = ProvenanceField()

    @property
    def shape_list(self) -> list:
        """Return the shape of the data source as a list."""
        return self.shape if isinstance(self.shape, list) else []

    @property
    def dims_list(self) -> list:
        """Return the dimensions of the data source as a list."""
        return self.dims if isinstance(self.dims, list) else []

    @property
    def slices_list(self) -> list[base_models.SliceModel]:
        """Return the slices of the lens as a list."""
        return [base_models.SliceModel(**slice_dict) for slice_dict in self.slices] if isinstance(self.slices, list) else []

    @property
    def dim_descriptors_list(self) -> list[base_models.DimDescriptor]:
        """Return the dimension descriptors of the data source as a list."""
        if isinstance(self.dim_descriptors, list):
            return [base_models.DimDescriptor(**desc) for desc in self.dim_descriptors]
        return []

    def get_size_of_dim(self, dim_name: str) -> int:
        """Get the size of a dimension by its name."""
        if isinstance(self.dims, list) and isinstance(self.shape, list):
            try:
                index = self.dims.index(dim_name)
                return self.shape[index]
            except ValueError:
                raise ValueError(f"Dimension {dim_name} not found in lens dimensions.")
        raise ValueError("Invalid dims or shape format in lens.")

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
    """The absolute coordinate universe (micrometers)."""

    name = models.CharField(max_length=255)
    blending = TextChoicesField(
        choices_enum=enums.BlendingChoices,
        default=enums.BlendingChoices.ADDITIVE.value,
        help_text="The blending of the scene",
    )
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="subscenes")
    affine_matrix = models.JSONField(default=list, help_text="The 4x4 affine transformation matrix mapping the scene to its parent scene (if any)")
    spatial_unit = models.CharField(max_length=100, help_text="The base unit of the scene (e.g. micrometers)")
    temporal_unit = models.CharField(max_length=100, help_text="The base unit of time dimensions in the scene (e.g. seconds)")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    provenance = ProvenanceField()


class Layer(models.Model):
    """A Layer is the placement of a data source in a scene, and the unit that gets alpha-blended.

    A single table discriminated by ``kind``: it carries the shared placement and
    compositing settings plus the source and render settings for every layer kind
    (image / shape / point / track / mesh). Exactly one source FK is set per kind,
    enforced by the create mutations. In GraphQL this one model is exposed as a
    ``Layer`` interface with concrete ``ImageLayer``/``ShapeLayer``/``PointLayer``/
    ``TrackLayer``/``MeshLayer`` types resolved by ``kind``.
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
    # 4x4 Transformation Matrix mapping the layer's local coordinates to Stage Units
    affine_matrix = models.JSONField(default=list, null=True, blank=True)

    # --- source references (exactly one set, per kind) ---
    lens = models.ForeignKey(Lens, on_delete=models.CASCADE, related_name="layers", null=True, blank=True, help_text="(image) The lens that defines the array data source and constraints")
    data_roi = models.ForeignKey("DataRoi", on_delete=models.CASCADE, related_name="shape_layers", null=True, blank=True, help_text="(shape) The data ROI whose vectors this layer renders")
    table = models.ForeignKey("Table", on_delete=models.CASCADE, related_name="table_layers", null=True, blank=True, help_text="(point/track) The table whose columns provide the coordinates and attributes")
    mesh = models.ForeignKey("Mesh", on_delete=models.CASCADE, related_name="mesh_layers", null=True, blank=True, help_text="(mesh) The mesh whose geometry this layer renders")

    # --- image / volume render settings ---
    render_graph = models.JSONField(null=True, blank=True, default=None, help_text="(image) The composable render recipe (channels + transfer functions + in-layer blend) that is the single source of truth for how the image layer is rendered.")
    colormap = TextChoicesField(choices_enum=enums.ColorMapChoices, default=enums.ColorMapChoices.VIRIDIS.value, help_text="(point/track) The applying color map", null=True, blank=True)
    x_dim = models.CharField(max_length=100, null=True, blank=True, help_text="(image) The name of the x dimension in the data source")
    y_dim = models.CharField(max_length=100, null=True, blank=True, help_text="(image) The name of the y dimension in the data source")
    z_dim = models.CharField(max_length=100, null=True, blank=True, help_text="(image) The name of the z dimension in the data source")
    t_dim = models.CharField(max_length=100, null=True, blank=True, help_text="(image) The name of the t dimension in the data source")
    intensity_dim = models.CharField(max_length=100, null=True, blank=True, help_text="(image) The name of the intensity dimension in the data source")

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
    """A DataRoi is a region of interest in a data array."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dataset = models.ForeignKey(ADataset, related_name="rois", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    x_dim = models.CharField(max_length=100, help_text="The name of the x dimension in the data source")
    y_dim = models.CharField(max_length=100, help_text="The name of the y dimension in the data source")
    z_dim = models.CharField(max_length=100, help_text="The name of the z dimension in the data source", null=True, blank=True)
    x_min = models.IntegerField(help_text="The minimum x coordinate of the ROI", null=True, blank=True)
    x_max = models.IntegerField(help_text="The maximum x coordinate of the ROI", null=True, blank=True)
    y_min = models.IntegerField(help_text="The minimum y coordinate of the ROI", null=True, blank=True)
    y_max = models.IntegerField(help_text="The maximum y coordinate of the ROI", null=True, blank=True)
    z_min = models.IntegerField(help_text="The minimum z coordinate of the ROI", null=True, blank=True)
    z_max = models.IntegerField(help_text="The maximum z coordinate of the ROI", null=True, blank=True)
    kind = TextChoicesField(
        choices_enum=enums.RoiKindChoices,
        default=enums.RoiKindChoices.PATH.value,
        help_text="The Roi can have vasrying kind, consult your API",
    )
    constraints = models.JSONField(help_text="The constraints of the ROI (for filtering data)", default=dict)
    vectors = models.JSONField(help_text="A list of the ROI Vectors (specific for each type)", default=list)
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
