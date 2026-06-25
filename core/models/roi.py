import random

from django.db import models
from django.contrib.auth import get_user_model
from core import enums
from koherent.fields import ProvenanceField
from authentikate.models import Organization
from django_choices_field import TextChoicesField

from .image import Image


class ROIGroup(models.Model):
    """A ROIGroup is a collection of ROIs.

    It is used to group ROIs together, for example to group all ROIs
    that are used to represent a specific channel.

    """

    name = models.CharField(max_length=1000, help_text="The name of the ROI group")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    provenance = ProvenanceField()


def random_color():
    levels = range(32, 256, 32)
    return tuple(random.choice(levels) for _ in range(3))


class ROI(models.Model):
    """A ROI is a region of interest in a representation.

    This region is to be regarded as a view on the representation. Depending
    on the implementatoin (type) of the ROI, the view can be constructed
    differently. For example, a rectangular ROI can be constructed by cropping
    the representation according to its 2 vectors. while
      a polygonal ROI can be constructed by masking the
    representation with the polygon.

    The ROI can also store a name and a description. T
    his is used to display the ROI in the UI.

    """

    group = models.ForeignKey(
        ROIGroup,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="rois",
        help_text="The group this ROI belongs to",
    )
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
    min_x = models.IntegerField(help_text="The minimum x coordinate of the ROI", null=True, blank=True)
    max_x = models.IntegerField(help_text="The maximum x coordinate of the ROI", null=True, blank=True)
    min_y = models.IntegerField(help_text="The minimum y coordinate of the ROI", null=True, blank=True)
    max_y = models.IntegerField(help_text="The maximum y coordinate of the ROI", null=True, blank=True)
    min_z = models.IntegerField(help_text="The minimum z coordinate of the ROI", null=True, blank=True)
    max_z = models.IntegerField(help_text="The maximum z coordinate of the ROI", null=True, blank=True)
    min_t = models.IntegerField(help_text="The minimum t coordinate of the ROI", null=True, blank=True)
    max_t = models.IntegerField(help_text="The maximum t coordinate of the ROI", null=True, blank=True)
    min_c = models.IntegerField(help_text="The minimum c coordinate of the ROI", null=True, blank=True)
    max_c = models.IntegerField(help_text="The maximum c coordinate of the ROI", null=True, blank=True)
    kind = TextChoicesField(
        choices_enum=enums.RoiKindChoices,
        default=enums.RoiKindChoices.PATH.value,
        help_text="The Roi can have vasrying kind, consult your API",
    )
    color = models.CharField(max_length=100, blank=True, null=True, help_text="The color of the ROI (for UI)")
    created_at = models.DateTimeField(auto_now=True, help_text="The time the ROI was created")
    image = models.ForeignKey(
        Image,
        on_delete=models.CASCADE,
        related_name="rois",
        help_text="The Image this ROI was original used to create (drawn on)",
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

    def __str__(self):
        return f"ROI creatsed by {self.creator} on {self.image.name}"

    def calculate_bounds(self) -> None:
        """
        Calculate and update the min/max coordinate fields based on vectors and kind.

        This method calculates the bounding hull of the ROI and updates the
        min_x, max_x, min_y, max_y, min_z, max_z, min_t, max_t, min_c, max_c fields.
        """
        from core.logic.roi import update_roi_bounds  # noqa: E402

        update_roi_bounds(self)
