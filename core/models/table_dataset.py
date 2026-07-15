"""The parquet-backed tabular dataset, sibling of :class:`~core.models.ADataset`.

A ``TableDataset`` is what the coordinate graph had no first-class home for: a
table whose rows are scientific records -- one row per segmented object with its
measurements, one row per single-molecule localization with its coordinates, one
row per cell with its marker levels. It parallels ``ADataset`` (mutable, its
geometry derived from an owned coordinate system, provenance through a task) but
is backed by a single Parquet store rather than a Zarr pyramid, and has no
multiscale.

Its columns are declared -- name, dtype, and a role. The *coordinate* columns are
special: they become the axes of the table's own coordinate system, which is what
makes a localization table placeable in a scene (its rows are points in a real
space). A table with no coordinate columns degenerates to a single INDEX axis: its
rows enumerate objects, nothing maps a pixel to a row, and the edge to the image it
came from is UNMAPPABLE. That degenerate case is exactly the old FeatureCollection.
"""

from typing import TYPE_CHECKING

from django.db import models
from django.contrib.auth import get_user_model

from authentikate.models import Organization
from datalayer.models import ParquetStore
from koherent.fields import ProvenanceField
from django_choices_field import TextChoicesField

from core import enums

if TYPE_CHECKING:
    from core.models.coords import CoordinateSystem


class TableDataset(models.Model):
    """A parquet-backed table whose rows are scientific records, placed by its coordinate columns.

    Mutable, like ``ADataset`` -- there is no version field, and a recomputation
    edits the store rather than minting a new immutable row. Its axes and units are
    not stored here: they live on the owned coordinate system, derived from the
    declared coordinate columns, so there is no second copy that can disagree.
    """

    name = models.CharField(max_length=1000, help_text="The name of this table dataset")
    description = models.CharField(max_length=1000, null=True, blank=True, help_text="The description of this table dataset")

    store = models.ForeignKey(
        ParquetStore,
        on_delete=models.CASCADE,
        related_name="table_datasets",
        help_text="The Parquet store holding the rows. The client reads it directly with a datalayer access grant",
    )
    provenance_metadata = models.JSONField(default=dict, help_text="How this table was produced (the run, its parameters and its inputs)")

    created_at = models.DateTimeField(auto_now_add=True, help_text="The time this table dataset was created")
    creator = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, null=True, blank=True, help_text="The user that created this table dataset")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, help_text="The organization this table dataset belongs to")
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

    class Meta:
        """Meta options for the table dataset."""

        ordering = ["-created_at"]

    def __str__(self) -> str:
        """The table dataset's name."""
        return self.name

    @property
    def coordinate_system_or_none(self) -> "CoordinateSystem | None":
        """The coordinate system this table owns, or None before it is created."""
        # The reverse of CoordinateSystem.table_dataset, which raises rather than
        # returning None when the system has not been created yet.
        return getattr(self, "coordinate_system", None)

    @property
    def axes(self) -> list:
        """The table's axes (its coordinate columns, materialized as Axis rows), in order."""
        system = self.coordinate_system_or_none
        return list(system.axes.all()) if system else []

    @property
    def axis_names(self) -> list:
        """The table's axis names, in order. Derived from the owned system's axes."""
        return [axis.name for axis in self.axes]

    def columns_by_role(self, role: str) -> list["TableColumn"]:
        """The declared columns of a given role, in declared order."""
        return list(self.columns.filter(role=role).order_by("order"))


class TableColumn(models.Model):
    """One declared column of a :class:`TableDataset`: its name, dtype, and role.

    The role is load-bearing. A ``COORDINATE`` column carries an axis type and unit
    and becomes an axis of the table's coordinate system; every other role is data a
    layer may read but which never places the row. Name, type and unit on a
    coordinate column are the same fact as the derived ``Axis`` -- they are written
    from here, once, in the same transaction, never edited into disagreement.
    """

    table = models.ForeignKey(TableDataset, on_delete=models.CASCADE, related_name="columns", help_text="The table dataset this column belongs to")
    order = models.PositiveSmallIntegerField(help_text="The column's position in the declared schema. For a coordinate column this is also its axis order")
    name = models.CharField(max_length=255, help_text="The column name, matching the Parquet column")
    dtype = models.CharField(max_length=64, help_text="The column's data type, as a DuckDB type string, e.g. 'DOUBLE', 'BIGINT'")
    role = TextChoicesField(choices_enum=enums.TableColumnRoleChoices, default=enums.TableColumnRoleChoices.ATTRIBUTE, help_text="What the column is for: a coordinate that places the row, or data hanging off it")
    axis_type = TextChoicesField(choices_enum=enums.AxisTypeChoices, null=True, blank=True, help_text="(coordinate) The semantic axis type this column samples, SPACE or TIME")
    unit = models.CharField(max_length=64, null=True, blank=True, help_text="(coordinate) The physical unit of the column's values, e.g. 'nanometer'. Null for pixel-index coordinates")
    long_name = models.CharField(max_length=255, null=True, blank=True, help_text="A human-readable name for the column")

    class Meta:
        """Meta options for the table column."""

        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["table", "name"], name="unique_table_column_name"),
            models.UniqueConstraint(fields=["table", "order"], name="unique_table_column_order"),
        ]

    def __str__(self) -> str:
        """The column's name and role."""
        return f"{self.name} ({self.role})"
