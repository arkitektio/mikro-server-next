# RFC-6 (one truth per space): the scene membership set is gone. A registration
# -- an edge into a shared space -- is unique per (data-tree, world) and places
# everything its tree fans out to, so there is nothing left for a scene to
# endorse and no per-layer choice to store. Breaking, schema-only: no data is
# migrated, by decision.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0025_scene_composes_over_a_world"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="scene",
            name="coordinate_transformations",
        ),
        migrations.AlterField(
            model_name="coordinatesystem",
            name="scene",
            field=models.OneToOneField(blank=True, help_text="The scene this world was minted for and cascades with. Ownership only: which space a scene composes over is Scene.world, and an adopted hub leaves this null", null=True, on_delete=django.db.models.deletion.CASCADE, related_name="world_coordinate_system", to="core.scene"),
        ),
        migrations.AlterField(
            model_name="historicalcoordinatesystem",
            name="scene",
            field=models.ForeignKey(blank=True, db_constraint=False, help_text="The scene this world was minted for and cascades with. Ownership only: which space a scene composes over is Scene.world, and an adopted hub leaves this null", null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name="+", to="core.scene"),
        ),
    ]
