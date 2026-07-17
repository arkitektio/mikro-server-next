# Materialize ADataset.spec onto a stored column.
#
# `spec` (what a dataset structurally is: one spatial member plus a modifier per
# acquisition axis) was derived from the intrinsic axes on every read and in a SQL
# twin filter. The axes are immutable after creation, so the value cannot drift --
# it is now written once, at the moment the axes are, and read straight back.
#
# The backfill recomputes it for existing rows. It imports the live
# `core.logic.coords` logic rather than inlining the count/type mapping: that
# breaks the usual "migrations are frozen in time" guideline, but it is a one-time
# backfill and reusing `specs_for_axes` keeps a single source of truth for the
# derivation, which is the whole point of the change. NOTE: `settings_test`
# disables migrations, so this RunPython is NOT exercised by the test suite --
# verify it manually against a real database.

import django.contrib.postgres.indexes
from django.conf import settings
from django.db import migrations, models


def backfill_stored_spec(apps, schema_editor):
    """Materialize `stored_spec` for every live dataset from its intrinsic axes."""
    from core.logic import coords as coords_logic

    ADataset = apps.get_model("core", "ADataset")
    CoordinateSystem = apps.get_model("core", "CoordinateSystem")

    for dataset in ADataset.objects.all().iterator():
        system = CoordinateSystem.objects.filter(intrinsic_of=dataset).first()
        if system is None:
            continue  # No intrinsic system yet: leave the default empty list.
        axis_specs = [coords_logic.AxisSpec(name=axis.name, type=axis.type) for axis in system.axes.order_by("order")]
        ADataset.objects.filter(pk=dataset.pk).update(
            stored_spec=[spec.value for spec in coords_logic.specs_for_axes(axis_specs)]
        )


class Migration(migrations.Migration):

    dependencies = [
        ('authentikate', '0006_alter_app_identifier_alter_release_unique_together'),
        ('core', '0033_tablecolumn_references'),
        ('koherent', '0003_rename_assignation_to_task'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='adataset',
            name='stored_spec',
            field=models.JSONField(default=list, help_text='What this dataset structurally is: the raw ADatasetSpec values (one spatial member plus a modifier per acquisition axis) that its intrinsic axes satisfy, materialized at creation by the axis writer from core.logic.coords.specs_for_axes. Immutable because the axes are, so it cannot disagree with them. Read it back as enum members through the `spec` property. Empty while the intrinsic system does not exist yet.'),
        ),
        migrations.AddField(
            model_name='historicaladataset',
            name='stored_spec',
            field=models.JSONField(default=list, help_text='What this dataset structurally is: the raw ADatasetSpec values (one spatial member plus a modifier per acquisition axis) that its intrinsic axes satisfy, materialized at creation by the axis writer from core.logic.coords.specs_for_axes. Immutable because the axes are, so it cannot disagree with them. Read it back as enum members through the `spec` property. Empty while the intrinsic system does not exist yet.'),
        ),
        migrations.AddIndex(
            model_name='adataset',
            index=django.contrib.postgres.indexes.GinIndex(fields=['stored_spec'], name='adataset_spec_gin'),
        ),
        migrations.RunPython(backfill_stored_spec, migrations.RunPython.noop),
    ]
