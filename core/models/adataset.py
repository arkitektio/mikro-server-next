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

from .view import create_default_color


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

            if slice.start is not None and slice.stop is not None:
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
    """A Placement is a placement of one data channel in a scene. Probably"""

    scene = models.ForeignKey(Scene, related_name="layers", on_delete=models.CASCADE)
    lens = models.ForeignKey(Lens, on_delete=models.CASCADE, related_name="layers", help_text="The lens that defines the data source and constraints of the placement")
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
        help_text="The blending of the channel",
    )
    provenance = ProvenanceField()
    # 4x4 Transformation Matrix mapping Local Pixels to Stage Units
    affine_matrix = models.JSONField(
        default=list,
        null=True,
        blank=True,
    )
    colormap = TextChoicesField(
        choices_enum=enums.ColorMapChoices,
        default=enums.ColorMapChoices.VIRIDIS.value,
        help_text="The applying color map of the channel",
        null=True,
        blank=True,
    )
    color = models.JSONField(help_text="The base color of the channel (if using a mapped scaler) (RGBA)", default=create_default_color, null=True)
    clim_min = models.FloatField(help_text="The contrast limit min of the channel", null=True, blank=True)
    clim_max = models.FloatField(help_text="The contrast limit max of the channel", null=True, blank=True)
    gamma = models.FloatField(help_text="The gamma of the channel", null=True, blank=True)
    x_dim = models.CharField(max_length=100, help_text="The name of the x dimension in the data source")
    y_dim = models.CharField(max_length=100, help_text="The name of the y dimension in the data source")
    z_dim = models.CharField(max_length=100, help_text="The name of the z dimension in the data source", null=True, blank=True)
    t_dim = models.CharField(max_length=100, help_text="The name of the t dimension in the data source", null=True, blank=True)
    intensity_dim = models.CharField(max_length=100, help_text="The name of the intensity dimension in the data source", null=True, blank=True)


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


class LineageLink(models.Model):
    """Linking the lineage of data transformations. Each link describes how a target lens was derived from a source lens, optionally using a mask to specify the region of interest and an action to describe the transformation applied."""

    source_lens = models.ForeignKey(Lens, related_name="lineage_links", on_delete=models.CASCADE)
    source_mask = models.ForeignKey(DataRoi, related_name="lineage_links", on_delete=models.CASCADE, null=True, blank=True)
    target_lens = models.ForeignKey(Lens, related_name="lineage_targets", on_delete=models.CASCADE)
    action = models.CharField(max_length=1000, help_text="The action that was used to create the target from the source", null=True, blank=True)
    provenance = ProvenanceField()
