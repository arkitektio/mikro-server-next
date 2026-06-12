from django.db import models
from django.contrib.auth import get_user_model
from koherent.fields import ProvenanceField
from authentikate.models import Organization

from .instrumentation import Instrument


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
    instrument = models.ForeignKey(Instrument, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, help_text="The time the stages was created")
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

    provenance = ProvenanceField()


class MultiWellPlate(models.Model):
    name = models.CharField(
        max_length=1000,
        help_text="A name for the multiwell plate",
        null=True,
        blank=True,
    )
    description = models.CharField(
        max_length=1000,
        help_text="A description for the multiwell plate",
        null=True,
        blank=True,
    )
    rows = models.IntegerField(help_text="The number of rows in the multiwell plate", null=True, blank=True)
    columns = models.IntegerField(help_text="The number of columns in the multiwell plate", null=True, blank=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    pinned_by = models.ManyToManyField(
        get_user_model(),
        related_name="pinned_multiwellplates",
        blank=True,
        help_text="The users that have pinned the stage",
    )

    provenance = ProvenanceField()


# TODO: Rename Stage
class Era(models.Model):
    """A stage is a time space corresponding to a
    a time space on a microscope during an experiment.

    Stages are used to define governign context for
    transformations and therefore are used to contextualize
    images according to their real world physical location.

    Stages are not meant to be reused outside of the original
    sample context and are therefore not meant to be shared, between
    experiments or samples.

    """

    name = models.CharField(max_length=1000, help_text="The name of the stage")
    kind = models.CharField(max_length=1000)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    instrument = models.ForeignKey(Instrument, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, help_text="The time the stages was created")
    begin = models.DateTimeField(help_text="The time the era started", null=True, blank=True)
    end = models.DateTimeField(help_text="The time the era ended", null=True, blank=True)

    creator = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="The user that created the stage",
    )
    pinned_by = models.ManyToManyField(
        get_user_model(),
        related_name="pinned_eras",
        blank=True,
        help_text="The users that have pinned the era",
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
