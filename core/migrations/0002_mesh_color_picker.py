"""A mesh layer publishes a picker of colourings, and gains a shading model and an LOD cap.

`mesh_color_by` held one entry, so a layer offered a viewer no choice. It becomes
`mesh_color_bys` -- an ordered list an author publishes -- plus `active_color_by`, the index
of the one currently drawn. The old single colouring is exactly the one-entry picker with
index 0, and no colouring at all is the empty picker with a null index, which is what null
already meant.

Ordered so the data move sits between the additions and the removal, which makes the reverse
read the same way: the old column comes back, the value is carried into it, then the new
columns go. `HistoricalLayer` is carried too -- dropping the column there would erase what
those rows recorded, which is the one thing a history table is for.
"""

import core.enums
import django_choices_field.fields
from django.db import migrations, models


def _fold_into_picker(apps, schema_editor):
    """One colouring becomes a one-entry picker, drawn; none becomes an empty one, not drawn."""
    for model_name in ("Layer", "HistoricalLayer"):
        model = apps.get_model("core", model_name)
        for layer in model.objects.exclude(mesh_color_by=None).iterator():
            entry = dict(layer.mesh_color_by)
            entry.setdefault("label", None)
            layer.mesh_color_bys = [entry]
            layer.active_color_by = 0
            layer.save(update_fields=["mesh_color_bys", "active_color_by"])


def _unfold_to_one(apps, schema_editor):
    """Take the first entry back. A picker's later entries have nowhere to go and are dropped."""
    for model_name in ("Layer", "HistoricalLayer"):
        model = apps.get_model("core", model_name)
        for layer in model.objects.iterator():
            entries = layer.mesh_color_bys or []
            if not entries:
                continue
            entry = dict(entries[0])
            entry.pop("label", None)
            layer.mesh_color_by = entry
            layer.save(update_fields=["mesh_color_by"])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicallayer',
            name='active_color_by',
            field=models.PositiveSmallIntegerField(blank=True, help_text='(mesh) Which entry of `meshColorBys` is currently drawn, as an index into it. Null renders the flat material color -- what having no colouring has always meant', null=True),
        ),
        migrations.AddField(
            model_name='historicallayer',
            name='max_level',
            field=models.PositiveSmallIntegerField(blank=True, help_text="(mesh) The deepest octree level this layer may load, capping detail against the collection's declared `grid.levels`. Null lets the viewer decide", null=True),
        ),
        migrations.AddField(
            model_name='historicallayer',
            name='mesh_color_bys',
            field=models.JSONField(blank=True, default=list, help_text="(mesh) The colourings this layer offers, in the order a picker should show them. Each colours objects by a column of a table this collection's FIELD edge keys into. Empty means the flat material color is the only rendering"),
        ),
        migrations.AddField(
            model_name='historicallayer',
            name='shading',
            field=django_choices_field.fields.TextChoicesField(choices=[('flat', 'Flat (one normal per face)'), ('smooth', 'Smooth (interpolated vertex normals)'), ('pbr', 'Physically based (metallic-roughness)'), ('matcap', 'Matcap (a lit sphere texture, view-space)'), ('unlit', 'Unlit (the material colour, unshaded)')], choices_enum=core.enums.MeshShadingChoices, default='smooth', help_text='(mesh) How the surface is lit. Vocabulary a mesh needs and an image has no use for -- a raster has no normals to shade with', max_length=6),
        ),
        migrations.AddField(
            model_name='layer',
            name='active_color_by',
            field=models.PositiveSmallIntegerField(blank=True, help_text='(mesh) Which entry of `meshColorBys` is currently drawn, as an index into it. Null renders the flat material color -- what having no colouring has always meant', null=True),
        ),
        migrations.AddField(
            model_name='layer',
            name='max_level',
            field=models.PositiveSmallIntegerField(blank=True, help_text="(mesh) The deepest octree level this layer may load, capping detail against the collection's declared `grid.levels`. Null lets the viewer decide", null=True),
        ),
        migrations.AddField(
            model_name='layer',
            name='mesh_color_bys',
            field=models.JSONField(blank=True, default=list, help_text="(mesh) The colourings this layer offers, in the order a picker should show them. Each colours objects by a column of a table this collection's FIELD edge keys into. Empty means the flat material color is the only rendering"),
        ),
        migrations.AddField(
            model_name='layer',
            name='shading',
            field=django_choices_field.fields.TextChoicesField(choices=[('flat', 'Flat (one normal per face)'), ('smooth', 'Smooth (interpolated vertex normals)'), ('pbr', 'Physically based (metallic-roughness)'), ('matcap', 'Matcap (a lit sphere texture, view-space)'), ('unlit', 'Unlit (the material colour, unshaded)')], choices_enum=core.enums.MeshShadingChoices, default='smooth', help_text='(mesh) How the surface is lit. Vocabulary a mesh needs and an image has no use for -- a raster has no normals to shade with', max_length=6),
        ),
        migrations.RunPython(_fold_into_picker, _unfold_to_one),
        migrations.RemoveField(
            model_name='historicallayer',
            name='mesh_color_by',
        ),
        migrations.RemoveField(
            model_name='layer',
            name='mesh_color_by',
        ),
    ]
