from django.db import models
from django.contrib.auth import get_user_model
from core import enums
from koherent.fields import ProvenanceField, HistoricForeignKey
from django_choices_field import TextChoicesField
from authentikate.models import Organization
from taggit.managers import TaggableManager
from datalayer.models import ZarrStore, MediaStore

from .dataset import Dataset


class Image(models.Model):
    """A Representation is 5-dimensional representation of an image

    Mikro stores each image as sa 5-dimensional representation. The dimensions are:
    - t: time
    - c: channel
    - z: z-stack
    - x: x-dimension
    - y: y-dimension

    This ensures a unified api for all images, regardless of their original dimensions.
      Another main
    determining factor for a representation is its variety:
    A representation can be a raw image representating voxels (VOXEL)
    or a segmentation mask representing instances of a class. (MASK)
    It can also representate a human perception of the image (RGB)
    or a human perception of the mask (RGBMASK)


    #Origins and Derivations

    Images can be filtered, which means that a new representation
    is created from the other (original) representations.
    This new representation is then linked to the original representations.
    This way, we can always trace back to the original representation.
    Both are encapsulaed in the origins and derived fields.

    Representations belong to *one* sample. Every transaction to our image data
    is still part of the original acuqistion, so also filtered
      images are refering back to the sample
    Each iamge has also a name, which is used to identify the image.
    The name is unique within a sample.
    File and Rois that are used to create images are saved in
      the file origins and roi origins repectively.


    """

    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, null=True, blank=True, related_name="images")
    store = models.ForeignKey(
        ZarrStore,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="The store of the image",
    )

    name = models.CharField(max_length=1000, help_text="The name of the image", default="")

    description = models.CharField(max_length=1000, null=True, blank=True)
    kind = TextChoicesField(
        choices_enum=enums.ImageKind,
        default=enums.ImageKind.UNKNOWN.value,
        help_text="The Representation can have vasrying kind, consult your API",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    creator = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
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

    pinned_by = models.ManyToManyField(
        get_user_model(),
        related_name="pinned_images",
        help_text="The users that have pinned the images",
    )
    provenance = ProvenanceField()
    tags = TaggableManager()

    class Meta:
        permissions = [("inspect_image", "Can view image")]

    def __str__(self) -> str:
        return f"Image {self.id}"


class Render(models.Model):
    dataset = models.ForeignKey(
        Dataset,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    creator = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, null=True)
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

    class Meta:
        abstract = True


class Blurhash(Render):
    image = HistoricForeignKey(Image, on_delete=models.CASCADE, related_name="blurhashes")
    hash = models.CharField(max_length=1000, help_text="The blurhash of the image")

    provenance = ProvenanceField()


class Video(Render):
    image = HistoricForeignKey(Image, on_delete=models.CASCADE, related_name="videos")
    store = models.ForeignKey(
        MediaStore,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="The store of the video",
        related_name="videos",
    )
    thumbnail = models.ForeignKey(
        MediaStore,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="The store of the video",
        related_name="thumbnails",
    )
    provenance = ProvenanceField()


class Snapshot(Render):
    image = HistoricForeignKey(Image, on_delete=models.CASCADE, related_name="snapshots")
    context = models.ForeignKey(
        "RGBRenderContext",
        on_delete=models.SET_NULL,
        related_name="snapshots",
        null=True,
        blank=True,
        help_text="The context of the snapshot",
    )
    store = models.ForeignKey(
        MediaStore,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="The store of the file",
    )
    name = models.CharField(max_length=1000, help_text="The name of the snapshot", default="")
    major_color = models.JSONField(null=True, blank=True, help_text="The major color of the snapshot")
    provenance = ProvenanceField()
