# FeatureCollection is subsumed by TableDataset: a measurement table is just a table
# dataset with no coordinate columns (a single INDEX axis, an UNMAPPABLE edge). This
# migration carries every existing FeatureCollection over as a TableDataset -- moving only
# the owner FK on its coordinate system, so every edge, axis and coordinateGraph fact
# survives -- then drops the FeatureCollection model.

from django.db import migrations


def carry_over_feature_collections(apps, schema_editor):
    FeatureCollection = apps.get_model("core", "FeatureCollection")
    TableDataset = apps.get_model("core", "TableDataset")

    for fc in FeatureCollection.objects.all().iterator():
        table = TableDataset.objects.create(
            # Keep the version identity in the name: a mutable table dataset has no
            # version field, and two versions of one collection are two tables now.
            name=f"{fc.name} ({fc.version})" if fc.version else fc.name,
            store=fc.store,
            provenance_metadata=fc.provenance_metadata,
            creator=fc.creator,
            organization=fc.organization,
        )
        # created_at is auto_now_add, so preserve the original after the fact.
        TableDataset.objects.filter(pk=table.pk).update(created_at=fc.created_at)

        # The collection's coordinate system already carries the INDEX axis and the
        # UNMAPPABLE edge; only its owner and kind move. No TableColumn rows: an empty
        # schema is the legal degenerate (measurement) case.
        system = getattr(fc, "coordinate_system", None)
        if system is not None:
            system.feature_collection = None
            system.table_dataset = table
            system.kind = "TABLE"
            system.save(update_fields=["feature_collection", "table_dataset", "kind"])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0021_table_dataset'),
    ]

    operations = [
        migrations.RunPython(carry_over_feature_collections, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='historicalfeaturecollection',
            name='history_relation',
        ),
        migrations.RemoveField(
            model_name='historicalcoordinatesystem',
            name='feature_collection',
        ),
        migrations.RemoveField(
            model_name='coordinatesystem',
            name='feature_collection',
        ),
        migrations.RemoveField(
            model_name='historicalfeaturecollection',
            name='client',
        ),
        migrations.RemoveField(
            model_name='historicalfeaturecollection',
            name='creator',
        ),
        migrations.RemoveField(
            model_name='historicalfeaturecollection',
            name='history_user',
        ),
        migrations.RemoveField(
            model_name='historicalfeaturecollection',
            name='organization',
        ),
        migrations.RemoveField(
            model_name='historicalfeaturecollection',
            name='store',
        ),
        migrations.RemoveField(
            model_name='historicalfeaturecollection',
            name='task',
        ),
        migrations.DeleteModel(
            name='FeatureCollection',
        ),
        migrations.DeleteModel(
            name='HistoricalFeatureCollection',
        ),
    ]
