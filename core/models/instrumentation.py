from django.db import models
from django.contrib.auth import get_user_model
from kanne_server.fields import QuantityField
from koherent.fields import ProvenanceField
from authentikate.models import Organization


class Objective(models.Model):
    serial_number = models.CharField(max_length=1000)
    name = models.CharField(max_length=1000)
    magnification = models.FloatField(blank=True, null=True)
    na = models.FloatField(blank=True, null=True)
    immersion = models.CharField(max_length=1000, blank=True, null=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    provenance = ProvenanceField()
    pinned_by = models.ManyToManyField(
        get_user_model(),
        related_name="pinned_objectives",
        blank=True,
        help_text="The users that have pinned the objective",
    )

    class Meta:
        unique_together = ("serial_number", "organization")


class Camera(models.Model):
    serial_number = models.CharField(max_length=1000)
    name = models.CharField(max_length=1000)
    model = models.CharField(max_length=1000, blank=True, null=True)
    bit_depth = models.IntegerField(blank=True, null=True)
    sensor_size_x = models.IntegerField(blank=True, null=True)
    sensor_size_y = models.IntegerField(blank=True, null=True)
    pixel_size_x = QuantityField(base_unit="picometer", blank=True, null=True, help_text="The physical pixel size in x direction, stored in picometers")
    pixel_size_y = QuantityField(base_unit="picometer", blank=True, null=True, help_text="The physical pixel size in y direction, stored in picometers")
    manufacturer = models.CharField(max_length=1000, blank=True, null=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    provenance = ProvenanceField()
    pinned_by = models.ManyToManyField(
        get_user_model(),
        related_name="pinned_cameras",
        blank=True,
        help_text="The users that have pinned the camera",
    )

    class Meta:
        unique_together = ("serial_number", "organization")


class Instrument(models.Model):
    name = models.CharField(max_length=1000)
    manufacturer = models.CharField(max_length=1000, null=True, blank=True)
    model = models.CharField(max_length=1000, null=True, blank=True)
    serial_number = models.CharField(max_length=1000)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    provenance = ProvenanceField()
    pinned_by = models.ManyToManyField(
        get_user_model(),
        related_name="pinned_instruments",
        blank=True,
        help_text="The users that have pinned the instrument",
    )

    class Meta:
        unique_together = ("serial_number", "organization")
