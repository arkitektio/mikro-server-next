"""Move `epoch` from the scene onto its world coordinate system.

The epoch -- the wall-clock instant a time axis has its origin at -- is a property
of the *space*, not of any composition over it: two scenes sharing one space
cannot coherently disagree about when its clock starts. On `CoordinateSystem` it
is also available to any calibrated system with a TIME axis (an ATLAS), which
previously had nowhere to put one.
"""

from django.db import migrations, models


def copy_epoch_to_world(apps, schema_editor):
    """Each scene's epoch becomes its world system's epoch."""
    Scene = apps.get_model("core", "Scene")
    CoordinateSystem = apps.get_model("core", "CoordinateSystem")

    for scene in Scene.objects.exclude(epoch=None).iterator():
        CoordinateSystem.objects.filter(scene=scene).update(epoch=scene.epoch)


def copy_epoch_back_to_scene(apps, schema_editor):
    """Reverse: the world system's epoch becomes the scene's again."""
    CoordinateSystem = apps.get_model("core", "CoordinateSystem")
    Scene = apps.get_model("core", "Scene")

    for system in CoordinateSystem.objects.exclude(epoch=None).exclude(scene=None).iterator():
        Scene.objects.filter(pk=system.scene_id).update(epoch=system.epoch)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0015_drop_borrowed_mesh_system"),
    ]

    operations = [
        migrations.AddField(
            model_name="coordinatesystem",
            name="epoch",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text=(
                    "The wall-clock instant this system's time axis has its origin at, so that "
                    "`wall_clock = epoch + t * unit`. A property of the *space*, not of any composition over it -- "
                    "two scenes sharing one space cannot disagree about when its clock starts. Meaningful only for "
                    "a calibrated system with a TIME axis (a WORLD, an ATLAS); optional even there: an unanchored "
                    "clock is still a perfectly composable relative coordinate"
                ),
            ),
        ),
        migrations.RunPython(copy_epoch_to_world, copy_epoch_back_to_scene),
        migrations.RemoveField(
            model_name="scene",
            name="epoch",
        ),
    ]
