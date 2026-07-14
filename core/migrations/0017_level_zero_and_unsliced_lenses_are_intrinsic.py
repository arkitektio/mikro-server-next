"""Fold the coordinate systems that duplicate the intrinsic space into it.

Two kinds of system were materialized that assert, by definition, the very same
space as the dataset's INTRINSIC system -- the level-0 pixel grid:

- every level-0 ARRAY system, joined to intrinsic by an all-ones SCALE edge, and
- every *unsliced* lens' system, joined by a zero-shift edge.

An identity edge between one space and itself records nothing, and a second node
for the same space is a stored duplicate. Everything that referenced those
systems -- lens edges, registrations, ROIs, point/track layers -- now references
the intrinsic system directly; the identity edges and the duplicate nodes go.

Forward-only: recreating the duplicates would be writing the redundancy back.
"""

from django.db import migrations


def _fold_system_into(system, intrinsic, *, Transformation, DataRoi, Layer):
    """Repoint everything from one system onto another, then delete it.

    The edge(s) between the two -- the stored identity -- are deleted first, so the
    repoint cannot turn them into self-loops.
    """
    Transformation.objects.filter(input=system, output=intrinsic).delete()
    Transformation.objects.filter(input=intrinsic, output=system).delete()
    Transformation.objects.filter(input=system).update(input=intrinsic)
    Transformation.objects.filter(output=system).update(output=intrinsic)
    DataRoi.objects.filter(coordinate_system=system).update(coordinate_system=intrinsic)
    Layer.objects.filter(coordinate_system=system).update(coordinate_system=intrinsic)
    system.delete()


def fold_duplicates_into_intrinsic(apps, schema_editor):
    """Level-0 ARRAY systems first (lens edges land on intrinsic), then unsliced lenses' systems."""
    CoordinateSystem = apps.get_model("core", "CoordinateSystem")
    Transformation = apps.get_model("core", "Transformation")
    DataRoi = apps.get_model("core", "DataRoi")
    Layer = apps.get_model("core", "Layer")

    models = {"Transformation": Transformation, "DataRoi": DataRoi, "Layer": Layer}

    level_zero_systems = CoordinateSystem.objects.filter(data_array__level=0).select_related("data_array")
    for system in level_zero_systems.iterator():
        intrinsic = CoordinateSystem.objects.filter(intrinsic_of=system.data_array.dataset_id).first()
        if intrinsic is None:
            continue  # A dataset with no intrinsic system has nothing to fold into.
        _fold_system_into(system, intrinsic, **models)

    unsliced_lens_systems = CoordinateSystem.objects.filter(lens__isnull=False, lens__slices=[]).select_related("lens")
    for system in unsliced_lens_systems.iterator():
        intrinsic = CoordinateSystem.objects.filter(intrinsic_of=system.lens.dataset_id).first()
        if intrinsic is None:
            continue
        _fold_system_into(system, intrinsic, **models)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0016_epoch_lives_on_the_world_system"),
    ]

    operations = [
        migrations.RunPython(fold_duplicates_into_intrinsic, migrations.RunPython.noop),
    ]
