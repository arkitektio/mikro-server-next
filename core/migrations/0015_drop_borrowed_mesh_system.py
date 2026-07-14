"""Drop the borrowed coordinate system from MeshCollection, now that 0014 has replaced it.

Strictly after 0014: that migration reads this column to build the owned system and the
anchor edge, and once it is gone there is nothing left to read. Separate migrations because
they must be separate *transactions* -- see the note in 0014.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0014_mesh_collections_own_their_system"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="meshcollection",
            name="coordinate_system",
        ),
    ]
