"""Give every existing mesh collection a coordinate system of its own.

Data only, and in a migration of its own on purpose. Postgres refuses DDL on a table that
has pending foreign-key trigger events from earlier writes *in the same transaction*, so
inserting these coordinate systems and then dropping `MeshCollection.coordinate_system` in
one migration fails outright:

    cannot ALTER TABLE "core_coordinatesystem" because it has pending trigger events

A migration is one transaction, so the data step and the column drop have to be two. The
drop is 0015, and it must stay after this: this reads the column it removes.
"""

from django.db import migrations


def give_mesh_collections_their_own_system(apps, schema_editor):
    """Move every existing mesh collection off its borrowed system and onto one of its own.

    A collection used to point straight at the system its meshes were extracted from -- the
    label array's intrinsic grid -- which asserted that the vertices were expressed in
    exactly that grid. That assertion is preserved here, but as an edge: the collection gets
    a MESH system with the same axes, and an IDENTITY edge relating it to the system it used
    to borrow. Nothing about the geometry changes; what changes is that there is now
    somewhere to say otherwise -- meshes extracted from a half-resolution grid are a SCALE,
    and under the old shape the only way to record that was to rewrite every vertex.

    Without this, the drop in 0015 would take the only record of where every existing
    collection's meshes live with it.
    """
    MeshCollection = apps.get_model("core", "MeshCollection")
    CoordinateSystem = apps.get_model("core", "CoordinateSystem")
    Transformation = apps.get_model("core", "Transformation")
    Axis = apps.get_model("core", "Axis")

    for collection in MeshCollection.objects.select_related("coordinate_system").iterator():
        source = collection.coordinate_system
        if source is None:
            continue

        system = CoordinateSystem.objects.create(
            name=f"{collection.version}/mesh",
            kind="MESH",
            mesh_collection=collection,
            creator_id=collection.creator_id,
            organization_id=collection.organization_id,
        )

        Axis.objects.bulk_create(
            [
                Axis(
                    coordinate_system=system,
                    order=axis.order,
                    name=axis.name,
                    type=axis.type,
                    unit=axis.unit,
                    long_name=axis.long_name,
                )
                for axis in source.axes.all().order_by("order")
            ]
        )

        Transformation.objects.create(
            kind="IDENTITY",
            name=f"{collection.version} <- {source.name}",
            input=system,
            output=source,
            params={},
            creator_id=collection.creator_id,
            organization_id=collection.organization_id,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0013_unmappable_and_collection_systems"),
    ]

    operations = [
        migrations.RunPython(give_mesh_collections_their_own_system, migrations.RunPython.noop),
    ]
