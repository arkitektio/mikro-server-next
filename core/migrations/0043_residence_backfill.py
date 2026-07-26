"""Move ownership onto the residents, and give the two zero-cases a home (RFC-9).

Pure DML, deliberately alone in its own migration. Postgres refuses DDL on a table with
pending FK trigger events from DML earlier in the same transaction, and a migration is one
transaction -- this repo has already shipped that failure once (0013, fixed by splitting into
0013/0014/0015). The schema half is 0042 before it and 0044 after it.

Three things happen here.

**Ownership becomes residence.** Each system's owner FK is copied into the resident's new
`coordinate_system` column, in the same direction it always meant: the dataset whose grid it
is, the level whose voxels it holds, the collection whose vertices it expresses.

**Calibrations are deliberately not copied.** A calibration was a dataset-owned PHYSICAL
system, and under RFC-9 it is simply a space with an edge into it -- so its `dataset` FK is
dropped in 0044 and nothing takes its place. The edge already exists (`create_calibration`
wrote it), so no geometry is created or moved here; the space merely stops belonging to
anyone.

**The two zero-cases get a home, which is the point of the redesign.** A level-0 array and an
unsliced lens owned *no* system, with a null standing in for "the dataset's own grid" (see
migration 0017, which deleted those duplicate nodes on purpose). They now point at that grid
explicitly -- the same node the dataset points at, not a copy of it. The special case stops
being a convention readers have to know.

No historical table is touched. The `historical*` twins gain the new column in 0042 and it is
left null for rows written before it existed, which is what a history row should say; their
owner columns are dropped wholesale in 0044, so nulling them first would be a large UPDATE
over an append-only table to no end.
"""

from django.db import migrations
from django.db.models import OuterRef, Subquery

#: (resident model, the owner FK on CoordinateSystem pointing back at it).
_RESIDENTS = [
    ("ADataset", "intrinsic_of_id"),
    ("DataArray", "data_array_id"),
    ("Lens", "lens_id"),
    ("MeshCollection", "mesh_collection_id"),
    ("TableDataset", "table_dataset_id"),
    ("AnnotationCollection", "annotation_collection_id"),
]


def ownership_becomes_residence(apps, schema_editor):
    """Copy each system's owner FK into its resident, then home the two zero-cases."""
    CoordinateSystem = apps.get_model("core", "CoordinateSystem")

    for model_name, owner_field in _RESIDENTS:
        model = apps.get_model("core", model_name)
        owning_system = CoordinateSystem.objects.filter(**{owner_field: OuterRef("pk")}).values("pk")[:1]
        # Only the residents some system actually points at. Updating every row would write
        # the subquery's NULL over the rest, which is harmless here but says the wrong thing.
        owned = CoordinateSystem.objects.exclude(**{owner_field: None}).values(owner_field)
        model.objects.filter(pk__in=owned).update(coordinate_system_id=Subquery(owning_system))

    # Only the rows still without a system: everything above already has its own.
    ADataset = apps.get_model("core", "ADataset")
    dataset_system = ADataset.objects.filter(pk=OuterRef("dataset_id")).values("coordinate_system_id")[:1]

    apps.get_model("core", "DataArray").objects.filter(level=0, coordinate_system_id__isnull=True).update(coordinate_system_id=Subquery(dataset_system))
    apps.get_model("core", "Lens").objects.filter(slices=[], coordinate_system_id__isnull=True).update(coordinate_system_id=Subquery(dataset_system))


def residence_becomes_ownership(apps, schema_editor):
    """Write the owner FKs back, so 0042 can be unapplied.

    The two zero-cases are *not* reversed into owner FKs: a level-0 array and an unsliced lens
    sharing their dataset's grid must not become that grid's owner, which would claim the
    dataset's own system for a level. They are recognised by pointing at the same system the
    dataset does, and left alone.
    """
    ADataset = apps.get_model("core", "ADataset")
    CoordinateSystem = apps.get_model("core", "CoordinateSystem")

    for model_name, owner_field in _RESIDENTS:
        model = apps.get_model("core", model_name)
        for resident in model.objects.exclude(coordinate_system_id=None).iterator():
            if model_name in ("DataArray", "Lens"):
                dataset = ADataset.objects.filter(pk=resident.dataset_id).values_list("coordinate_system_id", flat=True).first()
                if dataset == resident.coordinate_system_id:
                    continue
            CoordinateSystem.objects.filter(pk=resident.coordinate_system_id).update(**{owner_field: resident.pk})


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0042_residence_add_container_systems"),
    ]

    operations = [
        migrations.RunPython(ownership_becomes_residence, residence_becomes_ownership),
    ]
