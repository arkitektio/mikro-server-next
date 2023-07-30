from django.db import models
from django.contrib.auth import get_user_model
from taggit.managers import TaggableManager
from core import enums
from django.contrib.contenttypes.fields import GenericRelation
from koherent.fields import HistoryField
from django_choices_field import TextChoicesField

# Create your models here.


class Dataset(models.Model):
    """
    A dataset is a collection of data files and metadata files.
    It mimics the concept of a folder in a file system and is the top level
    object in the data model.

    """

    created_at = models.DateTimeField(
        auto_now_add=True, help_text="The time the experiment was created"
    )
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    name = models.CharField(max_length=200, help_text="The name of the experiment")
    description = models.CharField(
        max_length=1000,
        null=True,
        blank=True,
        help_text="The description of the experiment",
    )
    pinned_by = models.ManyToManyField(
        get_user_model(),
        related_name="pinned_datasets",
        blank=True,
        help_text="The users that have pinned the experiment",
    )
    tags = TaggableManager(help_text="Tags for the dataset")
    history = HistoryField()

    def __str__(self) -> str:
        return super().__str__()


class Objective(models.Model):
    serial_number = models.CharField(max_length=1000, unique=True)
    name = models.CharField(max_length=1000, unique=True)
    magnification = models.FloatField(blank=True, null=True)
    na = models.FloatField(blank=True, null=True)
    immersion = models.CharField(max_length=1000, blank=True, null=True)

    history = HistoryField()


class Camera(models.Model):
    serial_number = models.CharField(max_length=1000, unique=True)
    name = models.CharField(max_length=1000, unique=True)
    model = models.CharField(max_length=1000, blank=True, null=True)
    bit_depth = models.IntegerField(blank=True, null=True)
    sensor_size_x = models.FloatField(blank=True, null=True)
    sensor_size_y = models.FloatField(blank=True, null=True)
    physical_sensor_size_x = models.FloatField(blank=True, null=True)
    physical_sensor_size_y = models.FloatField(blank=True, null=True)
    physical_sensor_size_unit = models.CharField(max_length=1000, blank=True, null=True)
    manufacturer = models.CharField(max_length=1000, blank=True, null=True)

    history = HistoryField()


class Instrument(models.Model):
    name = models.CharField(max_length=1000, unique=True)
    detectors = models.JSONField(null=True, blank=True, default=list)
    dichroics = models.JSONField(null=True, blank=True, default=list)
    filters = models.JSONField(null=True, blank=True, default=list)
    objectives = models.ManyToManyField(
        Objective, blank=True, related_name="instruments"
    )
    lot_number = models.CharField(max_length=1000, null=True, blank=True)
    manufacturer = models.CharField(max_length=1000, null=True, blank=True)
    model = models.CharField(max_length=1000, null=True, blank=True)
    serial_number = models.CharField(max_length=1000, null=True, blank=True)

    history = HistoryField()


class Image(models.Model):
    """A Representation is 5-dimensional representation of an image

    Mikro stores each image as sa 5-dimensional representation. The dimensions are:
    - t: time
    - c: channel
    - z: z-stack
    - x: x-dimension
    - y: y-dimension

    This ensures a unified api for all images, regardless of their original dimensions. Another main
    determining factor for a representation is its variety:
    A representation can be a raw image representating voxels (VOXEL)
    or a segmentation mask representing instances of a class. (MASK)
    It can also representate a human perception of the image (RGB) or a human perception of the mask (RGBMASK)

    # Meta

    Meta information is stored in the omero field which gives access to the omero-meta data. Refer to the omero documentation for more information.


    #Origins and Derivations

    Images can be filtered, which means that a new representation is created from the other (original) representations. This new representation is then linked to the original representations. This way, we can always trace back to the original representation.
    Both are encapsulaed in the origins and derived fields.

    Representations belong to *one* sample. Every transaction to our image data is still part of the original acuqistion, so also filtered images are refering back to the sample
    Each iamge has also a name, which is used to identify the image. The name is unique within a sample.
    File and Rois that are used to create images are saved in the file origins and roi origins repectively.


    """

    dataset = models.ForeignKey(
        Dataset, on_delete=models.CASCADE, null=True, blank=True, related_name="images"
    )
    origins = models.ManyToManyField(
        "self",
        related_name="derived",
        symmetrical=False,
    )

    description = models.CharField(max_length=1000, null=True, blank=True)
    kind = TextChoicesField(
        choices_enum=enums.ImageKind,
        default=enums.ImageKind.UNKNOWN.value,
        help_text="The Representation can have vasrying kind, consult your API",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    creator = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)

    pinned_by = models.ManyToManyField(
        get_user_model(),
        related_name="pinned_representations",
        help_text="The users that have pinned the representation",
    )
    history = HistoryField(m2m_fields=[origins])

    class Meta:
        permissions = [("inspect_image", "Can view image")]

    def __str__(self):
        return f"Representation {self.id}"


class Channel(models.Model):
    name = models.CharField(max_length=1000, help_text="The name of the channel")
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
    color = models.CharField(
        max_length=1000,
        help_text="The default color for the channel (might be ommited by the rendered)",
        null=True,
        blank=True,
    )

    history = HistoryField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "emission_wavelength", "excitation_wavelength"],
                name="Only one channel per name, emmission_wavelength and excitation_wavelength",
            )
        ]


# TODO: Rename Stage
class Stage(models.Model):

    """A stage is a 3D space corresponding to a
    a 3D space on a microscope during an experiment.

    Stages are used to define governign context for
    transformations and therefore are used to contextualize
    images according to their real world physical location.

    Stages are not meant to be reused outside of the original
    sample context and are therefore not meant to be shared, between
    experiments or samples.

    """

    name = models.CharField(max_length=1000, help_text="The name of the stage")
    kind = models.CharField(max_length=1000)
    instrument = models.ForeignKey(
        Instrument, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(
        auto_now_add=True, help_text="The time the stages was created"
    )
    creator = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="The user that created the stage",
    )
    pinned_by = models.ManyToManyField(
        get_user_model(),
        related_name="pinned_stages",
        blank=True,
        help_text="The users that have pinned the stage",
    )

    history = HistoryField()


class View(models.Model):
    image = models.ForeignKey(Image, on_delete=models.CASCADE, related_name="views")
    z_min = models.IntegerField(
        help_text="The index of the channel", null=True, blank=True
    )
    z_max = models.IntegerField(
        help_text="The index of the channel", null=True, blank=True
    )
    x_min = models.IntegerField(
        help_text="The index of the channel", null=True, blank=True
    )
    x_max = models.IntegerField(
        help_text="The index of the channel", null=True, blank=True
    )
    y_min = models.IntegerField(
        help_text="The index of the channel", null=True, blank=True
    )
    y_max = models.IntegerField(
        help_text="The index of the channel", null=True, blank=True
    )
    t_min = models.IntegerField(
        help_text="The index of the channel", null=True, blank=True
    )
    t_max = models.IntegerField(
        help_text="The index of the channel", null=True, blank=True
    )
    c_min = models.IntegerField(
        help_text="The index of the channel", null=True, blank=True
    )
    c_max = models.IntegerField(
        help_text="The index of the channel", null=True, blank=True
    )


class InstrumentView(View):
    instrument = models.ForeignKey(
        Instrument, on_delete=models.CASCADE, related_name="views"
    )

    history = HistoryField()


class ChannelView(View):
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="views")

    history = HistoryField()


class TransformationView(View):
    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name="views")
    kind = TextChoicesField(
        choices_enum=enums.TransformationKind,
        default=enums.TransformationKind.AFFINE.value,
        help_text="The kind of transformation",
    )
    matrix = models.JSONField()

    history = HistoryField()


class ROI(models.Model):
    """A ROI is a region of interest in a representation.

    This region is to be regarded as a view on the representation. Depending
    on the implementatoin (type) of the ROI, the view can be constructed
    differently. For example, a rectangular ROI can be constructed by cropping
    the representation according to its 2 vectors. while a polygonal ROI can be constructed by masking the
    representation with the polygon.

    The ROI can also store a name and a description. This is used to display the ROI in the UI.

    """

    creator = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        help_text="The user that created the ROI",
    )
    vectors = models.JSONField(
        max_length=3000,
        help_text="A list of the ROI Vectors (specific for each type)",
        default=list,
    )
    kind = TextChoicesField(
        choices_enum=enums.RoiKind,
        default=enums.RoiKind.UNKNOWN.value,
        help_text="The Roi can have vasrying kind, consult your API",
    )
    color = models.CharField(
        max_length=100, blank=True, null=True, help_text="The color of the ROI (for UI)"
    )
    created_at = models.DateTimeField(
        auto_now=True, help_text="The time the ROI was created"
    )
    representation = models.ForeignKey(
        Image,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="rois",
        help_text="The Representation this ROI was original used to create (drawn on)",
    )
    label = models.CharField(
        max_length=1000,
        null=True,
        blank=True,
        help_text="The label of the ROI (for UI)",
    )
    pinned_by = models.ManyToManyField(
        get_user_model(),
        related_name="pinned_rois",
        blank=True,
        help_text="The users that pinned this ROI",
    )

    def __str__(self):
        return f"ROI creatsed by {self.creator.username} on {self.representation.name}"
