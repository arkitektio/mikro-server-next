"""Purge the array-dataset world so it can be rebuilt on the RFC-5 coordinate graph.

This is a **destructive, one-way migration**. It deletes every ADataset, DataArray,
CoordinateAnchor, Lens, Scene, Layer, DataRoi and LineageLink -- and their history
tables -- so that the non-null coordinate-system columns 0008 adds have no rows to
fail against.

It is deliberate, not incidental. The old rows cannot be migrated forward:

* ``DataArray.scale_factors`` stored *nominal* pyramid factors (1, 2, 4, 8, ...),
  and a real pyramid does not obey them -- a 36-voxel axis floors to 36, 18, 9, 4,
  2, 1, whose true factors are 1, 2, 4, **9, 18, 36**. Backfilling an absolute
  scale from the nominal chain would carry the error forward with more precision.
* There is no ``base_spacing`` anywhere in the old model (``Scene.spatial_unit`` is
  ``"UNKNOWN"``), so there is no physical size to derive an absolute scale *from*.
  It has to come back in at ingest.
* The arrays themselves are one axis-swap away from the RFC-5 ordering, which is a
  data-plane operation on the Zarr stores, not something Django can do.

So the data is re-ingested rather than migrated. The **legacy Image / ROI / View /
Dataset world is untouched** -- it does not share these tables.
"""

from django.db import migrations

# Children first: the FK graph is Layer -> {Lens, DataRoi, Table, Mesh},
# Lens -> ADataset, DataRoi -> ADataset, DataArray -> ADataset.
_MODELS = (
    "LineageLink",
    "Layer",
    "DataRoi",
    "Lens",
    "OptikitState",
    "OmeMetadata",
    "OmePlaneMetadata",
    "ValueHistogram",
    "ChannelLabel",
    "LightPath",
    "CoordinateAnchor",
    "DataArray",
    "ADataset",
    "Scene",
)

# simple_history's HistoricalRecords is not attached to the migration-state models,
# so no cascade and no signal clears these. They have to be emptied by hand, or the
# shadow rows outlive the rows they shadow and 0008's AddField hits them.
_HISTORICAL = (
    "HistoricalLineageLink",
    "HistoricalLayer",
    "HistoricalDataRoi",
    "HistoricalLens",
    "HistoricalADataset",
    "HistoricalScene",
)


def purge(apps, schema_editor):
    """Delete every row of the array-dataset world, and its history."""
    for label in _MODELS + _HISTORICAL:
        apps.get_model("core", label).objects.all().delete()


def noop(apps, schema_editor):
    """Irreversible: the deleted rows are gone, and there is nothing to restore them from."""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_alter_camera_name_alter_camera_serial_number_and_more"),
    ]

    operations = [
        migrations.RunPython(purge, noop),
    ]
