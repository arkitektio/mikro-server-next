from django.db import models
from django.contrib.auth import get_user_model
from core import enums
from koherent.fields import ProvenanceField, HistoricForeignKey
from authentikate.models import Organization
from django_choices_field import TextChoicesField
from datalayer.models import ZarrStore, ParquetStore

from .dataset import File, Table
from .image import Image
from .instrumentation import Objective, Camera, Instrument
from .stage import Stage, MultiWellPlate, Era
from .roi import ROI


class ViewCollection(models.Model):
    """A ViewCollection is a collection of views.

    It is used to group views together, for example to group all views
    that are used to represent a specific channel.

    """

    name = models.CharField(max_length=1000, help_text="The name of the view")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    provenance = ProvenanceField()
    pinned_by = models.ManyToManyField(
        get_user_model(),
        related_name="pinned_view_collections",
        blank=True,
        help_text="The users that have pinned the view collection",
    )


class View(models.Model):
    image = HistoricForeignKey(Image, on_delete=models.CASCADE)
    collection = models.ForeignKey(ViewCollection, on_delete=models.CASCADE, null=True, blank=True)
    z_min = models.IntegerField(help_text="The index of the channel", null=True, blank=True)
    z_max = models.IntegerField(help_text="The index of the channel", null=True, blank=True)
    x_min = models.IntegerField(help_text="The index of the channel", null=True, blank=True)
    x_max = models.IntegerField(help_text="The index of the channel", null=True, blank=True)
    y_min = models.IntegerField(help_text="The index of the channel", null=True, blank=True)
    y_max = models.IntegerField(help_text="The index of the channel", null=True, blank=True)
    t_min = models.IntegerField(help_text="The index of the channel", null=True, blank=True)
    t_max = models.IntegerField(help_text="The index of the channel", null=True, blank=True)
    c_min = models.IntegerField(help_text="The index of the channel", null=True, blank=True)
    c_max = models.IntegerField(help_text="The index of the channel", null=True, blank=True)
    is_global = models.BooleanField(help_text="Whether the view is global or not", default=False)

    class Meta:
        abstract = True


class OpticsView(View):
    instrument = models.ForeignKey(Instrument, on_delete=models.CASCADE, related_name="views")
    objective = models.ForeignKey(Objective, on_delete=models.CASCADE, related_name="views", null=True)
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE, related_name="views", null=True)

    provenance = ProvenanceField()

    class Meta:
        default_related_name = "optics_views"


class LightpathView(View):
    graph = models.JSONField(help_text="The lightpath of the instrument")

    provenance = ProvenanceField()

    class Meta:
        default_related_name = "lightpath_views"


class ScaleView(View):
    parent = models.ForeignKey("Image", on_delete=models.CASCADE, related_name="derived_scale_views")
    scale_x = models.FloatField(help_text="The scale in x direction")
    scale_y = models.FloatField(help_text="The scale in y direction")
    scale_z = models.FloatField(help_text="The scale in z direction")
    scale_t = models.FloatField(help_text="The scale in t direction")
    scale_c = models.FloatField(help_text="The scale in c direction")

    provenance = ProvenanceField()

    class Meta:
        default_related_name = "scale_views"


class AlphaView(View):
    is_alpha_for = models.ForeignKey(ViewCollection, on_delete=models.CASCADE, related_name="attached_alpha_views")

    class Meta:
        default_related_name = "alpha_views"


class ContinousScanView(View):
    direction = TextChoicesField(
        choices_enum=enums.ContinousScanDirection,
        help_text="The direction of the scan",
    )

    class Meta:
        default_related_name = "continousscan_views"


class WellPositionView(View):
    well = models.ForeignKey(MultiWellPlate, on_delete=models.CASCADE, related_name="views")
    row = models.IntegerField(help_text="The row of the well")
    column = models.IntegerField(help_text="The column of the well")

    provenance = ProvenanceField()

    class Meta:
        default_related_name = "wellposition_views"


class ChannelView(View):
    """A ChannelView is a view on a channel of an image"""

    name = models.CharField(
        max_length=1000,
        help_text="The name of the channel",
        null=True,
        blank=True,
    )
    emission_wavelength = models.FloatField(
        help_text="The emmission wavelength of the fluorophore in nm",
        null=True,
        blank=True,
    )
    excitation_wavelength = models.FloatField(
        help_text="The excitation wavelength of the fluorophore in nm",
        null=True,
        blank=True,
    )
    acquisition_mode = models.CharField(
        max_length=1000,
        help_text="The acquisition mode of the channel",
        null=True,
        blank=True,
    )
    provenance = ProvenanceField()

    class Meta:
        default_related_name = "channel_views"


class ReferenceView(View):
    """A ReferenceView is a view on a image that corresponds to a reference image

    This is used to describe that the image is a reference image for another image.
    It is used to describe the context of the image.

    """

    provenance = ProvenanceField()

    class Meta:
        default_related_name = "reference_views"


class FileView(View):
    """A FileView is a view on a file

    This means that the image part  represents the context of a file in a specific
    context.


    """

    file = models.ForeignKey(File, on_delete=models.CASCADE, related_name="views")
    series_identifier = models.CharField(
        max_length=1000,
        help_text="The series identifier of the file",
        null=True,
        blank=True,
    )

    provenance = ProvenanceField()

    class Meta:
        default_related_name = "file_views"


class HistogramView(View):
    """A Histogram View

    A Histogram View describes the frequency of pixel values in an image. It is used to
    describe the context of the image.

    """

    histogram = models.JSONField(default=list, help_text="The histogram of the image (y values)")
    bins = models.JSONField(default=list, help_text="The bin indices of the histogram (x values)")
    min = models.FloatField(help_text="The minimum pixel value of the histogram", null=True, blank=True)
    max = models.FloatField(help_text="The maximum pixel value of the histogram", null=True, blank=True)
    provenance = ProvenanceField()

    class Meta:
        default_related_name = "histogram_views"


class TableView(View):
    """A TablieView is a view on a file

    This means that the image part was created from a table and represents the context of
    the table in a specific context (i.e the table represent localisations in SMLIM


    """

    table = models.ForeignKey(Table, on_delete=models.CASCADE, related_name="views")
    series_identifier = models.CharField(
        max_length=1000,
        help_text="The series identifier of the file",
        null=True,
        blank=True,
    )

    provenance = ProvenanceField()

    class Meta:
        default_related_name = "table_views"


class DerivedView(View):
    """A DerivedView

    A DerivedView is a view that describes the process of creating the image from
    another image. It is metadata that describes that the image was created from
    another image and is used to describe the context of the image.


    """

    origin_image = models.ForeignKey(Image, on_delete=models.CASCADE, related_name="derived_from_views")
    operation = models.CharField(
        max_length=1000,
        help_text="The operation that was used to create the image",
        null=True,
    )

    provenance = ProvenanceField()

    class Meta:
        default_related_name = "derived_views"


class ROIView(View):
    """A Roi View

    RoiViews describe that the section of the image represents the cut roi of
    another image (the parent image). This is used to describe that the image
    is a cutout of another image and is used to describe the context of the
    image.

    """

    roi = models.ForeignKey("ROI", on_delete=models.CASCADE, related_name="views")

    provenance = ProvenanceField()

    class Meta:
        default_related_name = "roi_views"


class Accessor(models.Model):
    table = HistoricForeignKey(Table, on_delete=models.CASCADE)
    keys = models.JSONField(max_length=1000, help_text="The key of the column")
    min_index = models.IntegerField(
        help_text="The index of the row where this view starts (null if all rows)",
        null=True,
        blank=True,
    )
    max_index = models.IntegerField(
        help_text="The index of the row where this view ends (null if all rows)",
        null=True,
        blank=True,
    )
    is_global = models.BooleanField(help_text="Whether the view is global or not", default=False)

    class Meta:
        abstract = True


class LabelAccessor(Accessor):
    """An label accessor declares the values as pixel_values of an associated mask_view on image"""

    mask_view = models.ForeignKey("MaskView", on_delete=models.CASCADE, related_name="label_accessors")

    class Meta:
        default_related_name = "label_accessors"


class ImageAccessor(Accessor):
    """An image accessor declares the values as ids of an associated image"""

    pass

    class Meta:
        default_related_name = "image_accessors"


class RGBRenderContext(models.Model):
    """A RGBRenderContext is a collection of views.

    It is used to group views together, for example to group all views
    that are used to represent a specific channel.

    """

    image = models.ForeignKey(
        Image,
        on_delete=models.CASCADE,
        related_name="rgb_contexts",
    )
    description = models.CharField(max_length=8000, help_text="The description of the view", null=True, blank=True)
    name = models.CharField(max_length=1000, help_text="The name of the view")
    provenance = ProvenanceField()
    pinned_by = models.ManyToManyField(
        get_user_model(),
        related_name="pinned_rgbcontexts",
        blank=True,
        help_text="The users that have pinned the era",
    )
    blending = TextChoicesField(
        choices_enum=enums.BlendingChoices,
        default=enums.BlendingChoices.ADDITIVE.value,
        help_text="The blending of the channel",
    )
    z = models.IntegerField(help_text="The index of the z (if not in 3D mode)", default=0)
    t = models.IntegerField(help_text="The index of the t (if not in hypermode)", default=0)
    c = models.IntegerField(help_text="The index of the c (if not in multi-channel mode)", default=0)


class RenderTree(models.Model):
    """A RenderTree is a tree structure that describes the rendering of multiple images in a rgb context."""

    name = models.CharField(max_length=1000, help_text="The name of the tree", default="")
    linked_contexts = models.ManyToManyField(RGBRenderContext, related_name="linked_trees")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    tree = models.JSONField()


class AcquisitionView(View):
    """A AcquisitionView

    The AcquisitionView is a view that describes the process of acquiring the
    image. It is used to describe the acquisition time of the image, the operator
    and who acquired the image.

    """

    description = models.CharField(
        max_length=8000,
        help_text="A cleartext description of the image acquisition",
        null=True,
    )
    acquired_at = models.DateTimeField(auto_now_add=True, help_text="The time the image was acquired")
    operator = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="The user that created the image",
    )

    class Meta:
        default_related_name = "acquisition_views"


def create_default_color():
    return [255, 255, 255, 255]


class RGBView(View):
    """An RGBView is a view on a image that corresponds to it being rendered in RGB on a RGBRenderContext"""

    contexts = models.ManyToManyField(RGBRenderContext, related_name="views")
    contrast_limit_min = models.FloatField(help_text="The limits of the channel", null=True, blank=True)
    contrast_limit_max = models.FloatField(help_text="The limits of the channel", null=True, blank=True)
    gamma = models.FloatField(help_text="The gamma of the channel", null=True, blank=True)
    color_map = TextChoicesField(
        choices_enum=enums.ColorMapChoices,
        default=enums.ColorMapChoices.VIRIDIS.value,
        help_text="The applying color map of the channel",
    )
    active = models.BooleanField(default=True, help_text="Whether the view is active")
    base_color = models.JSONField(help_text="The base color of the channel (if using a mapped scaler) (RGBA)", default=create_default_color, null=True)

    provenance = ProvenanceField()

    @property
    def colormap_name(self) -> str:
        import webcolors

        """
        Convert an RGBA value to the closest color name.

        Parameters:
            rgba (tuple): A tuple of 4 integers (red, green, blue, alpha), where each is in the range 0-255.

        Returns:
            str: The closest color name.

        """
        if self.color_map != enums.ColorMapChoices.INTENSITY.value:
            return self.color_map
        # Ignore the alpha channel for color name matching
        rgb = [int(a) for a in self.base_color[:3]]
        # Get the exact or closest color name
        try:
            return webcolors.rgb_to_name(rgb)
        except ValueError:
            return "Unknown Color"

    class Meta:
        default_related_name = "rgb_views"


class TimepointView(View):
    era = models.ForeignKey(Era, on_delete=models.CASCADE, related_name="views")
    ms_since_start = models.FloatField(
        help_text="The time in ms since the start of the era",
        null=True,
        blank=True,
    )
    index_since_start = models.IntegerField(
        help_text="The index of the timepoint since the start of the era",
        null=True,
        blank=True,
    )

    provenance = ProvenanceField()

    class Meta:
        default_related_name = "timepoint_views"


class LabelView(View):
    label = models.CharField(
        max_length=1000,
        help_text="The label of the entity class",
        null=True,
    )

    provenance = ProvenanceField()

    class Meta:
        default_related_name = "label_views"


class MaskView(View):
    """A MaskView is a view on a image that represents a label mask of another image."""

    reference_view = models.ForeignKey(
        ReferenceView,
        on_delete=models.CASCADE,
        related_name="mask_views",
        help_text="The view that is masked by this mask",
    )
    labels_set = models.JSONField(
        default=list,
        help_text="The labels of the mask, and their corresponding colors",
    )
    labels = models.ForeignKey(
        ZarrStore,
        on_delete=models.CASCADE,
        help_text="The store containing the labels of the instances",
        null=True,
        blank=True,
    )

    class Meta:
        default_related_name = "mask_views"


class InstanceMaskView(View):
    """An InstanceMaskView is a view on a image that represents a instance mask of another image."""

    reference_view = models.ForeignKey(
        ReferenceView,
        on_delete=models.CASCADE,
        related_name="instance_mask_views",
        help_text="The view that is masked by this mask",
    )
    classes_set = models.JSONField(
        default=list,
        help_text="The instance labels of the mask, and their corresponding colors",
    )
    labels = models.ForeignKey(
        ParquetStore,
        on_delete=models.CASCADE,
        help_text="The store containing the labels of the instances",
        null=True,
        blank=True,
    )

    class Meta:
        default_related_name = "instance_mask_views"

    provenance = ProvenanceField()


class AffineTransformationView(View):
    """An AffineTransformationView is a view on a image that corresponds to an affine transformation"""

    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name="affine_views")
    affine_matrix = models.JSONField()

    provenance = ProvenanceField()

    class Meta:
        default_related_name = "affine_transformation_views"


class CropView(View):
    """A CropView is a view on a image that represents a cropped section of another image."""

    roi = models.ForeignKey(
        ROI,
        on_delete=models.CASCADE,
        related_name="crop_views",
        help_text="The ROI that defines the crop",
    )
