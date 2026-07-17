"""DISPLACEMENTS and COORDINATES become one FIELD kind, whose map is a node, not a store.

The two kinds said on the edge what the field array's own value axis says better: offsets
(DISPLACEMENT) or absolute positions (COORDINATE). Said twice, they could disagree; and the
store they hung off the edge could carry neither axes nor lineage, which is what left
``AxisType.COORDINATE`` and ``AxisType.DISPLACEMENT`` dead in the enum since they were
written. ``Transformation.field`` points at the array's coordinate system instead.

**This deletes data, and it must.** An existing DISPLACEMENTS / COORDINATES row's map *is*
its ``store``, and the new column cannot be backfilled from one: a bare store has no
coordinate system, so there is no node to point at. The row would survive as an edge that
claims to be a map and holds none -- worse than absent, because a placement walk would cross
it. Re-author any such registration with a field node.
"""

import core.enums
import django.db.models.deletion
import django_choices_field.fields
from django.db import migrations, models


def drop_field_edges(apps, schema_editor):
    """Delete the edges whose map cannot survive this migration. See the module docstring.

    Walks up to the outermost wrapper before deleting. A field kind may be a *child* of a
    SEQUENCE or BY_DIMENSION, and deleting only the child would leave the wrapper composing
    a map with a hole in it -- a mutilated edge rather than a removed one, and one that
    still walks. The parent FK cascades back down to the remaining children.

    The read is raw SQL, and it has to be. A historical model's ``kind`` is a
    ``TextChoicesField`` whose ``choices_enum`` is a *live* import of
    ``core.enums.TransformKindChoices`` -- not a frozen copy -- so the enum this migration
    reads is the one this migration's own commit deleted DISPLACEMENTS from. An ORM
    ``filter(kind__in=("DISPLACEMENTS", ...))`` raises ValidationError while *building* the
    query, before touching a row, on every database including one with nothing to delete.
    Selecting by pk afterwards is safe: it never goes near the field.
    """
    Transformation = apps.get_model("core", "Transformation")
    table = Transformation._meta.db_table

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"SELECT id, parent_id FROM {table}")  # noqa: S608 - table name is from the model's own meta
        parents = {row[0]: row[1] for row in cursor.fetchall()}
        cursor.execute(f"SELECT id FROM {table} WHERE kind IN ('DISPLACEMENTS', 'COORDINATES')")  # noqa: S608 - as above
        field_edge_ids = [row[0] for row in cursor.fetchall()]

    doomed = set()
    for edge_id in field_edge_ids:
        root, seen = edge_id, {edge_id}
        while parents.get(root) is not None:
            root = parents[root]
            if root in seen:  # not expressible through the API, but a delete loop is worse than a raise
                raise RuntimeError(f"Transformation {root} is its own ancestor; refusing to guess what to delete.")
            seen.add(root)
        doomed.add(root)

    if doomed:
        Transformation.objects.filter(pk__in=doomed).delete()


def refuse_reverse(apps, schema_editor):
    """Reversing cannot restore a deleted map, and pretending otherwise would be the lie above."""
    raise RuntimeError("0032 deleted the DISPLACEMENTS / COORDINATES edges whose stores it dropped. Their maps are gone; reversing the schema cannot bring them back. Restore from a backup instead.")


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0031_historicalscene_background_color_and_more'),
    ]

    operations = [
        migrations.RunPython(drop_field_edges, refuse_reverse),
        migrations.RemoveField(
            model_name='historicaltransformation',
            name='store',
        ),
        migrations.RemoveField(
            model_name='transformation',
            name='store',
        ),
        migrations.AddField(
            model_name='historicaltransformation',
            name='field',
            field=models.ForeignKey(blank=True, db_constraint=False, help_text='(FIELD) The coordinate system of the array whose values are this map, when that array is a separate one (a warp field). Null when the input is its own field, as for a label mask whose pixels are the map. Its value axis (COORDINATE or DISPLACEMENT) says whether the values are positions or offsets; no value axis means scalar, and scalar means positions', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='core.coordinatesystem'),
        ),
        migrations.AddField(
            model_name='transformation',
            name='field',
            field=models.ForeignKey(blank=True, help_text='(FIELD) The coordinate system of the array whose values are this map, when that array is a separate one (a warp field). Null when the input is its own field, as for a label mask whose pixels are the map. Its value axis (COORDINATE or DISPLACEMENT) says whether the values are positions or offsets; no value axis means scalar, and scalar means positions', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='fields_of', to='core.coordinatesystem'),
        ),
        migrations.AlterField(
            model_name='historicaltransformation',
            name='kind',
            field=django_choices_field.fields.TextChoicesField(choices=[('IDENTITY', 'Identity'), ('SCALE', 'Scale'), ('TRANSLATION', 'Translation'), ('MAP_AXIS', 'Map Axis'), ('AFFINE', 'Affine'), ('ROTATION', 'Rotation'), ('SEQUENCE', 'Sequence'), ('BY_DIMENSION', 'By Dimension'), ('FIELD', 'Field (a map given by the values of an array)'), ('BIJECTION', 'Bijection'), ('UNMAPPABLE', 'Unmappable (a declared non-correspondence)')], choices_enum=core.enums.TransformKindChoices, default='IDENTITY', help_text='The kind of transformation, which fixes how `params` is interpreted', max_length=12),
        ),
        migrations.AlterField(
            model_name='transformation',
            name='kind',
            field=django_choices_field.fields.TextChoicesField(choices=[('IDENTITY', 'Identity'), ('SCALE', 'Scale'), ('TRANSLATION', 'Translation'), ('MAP_AXIS', 'Map Axis'), ('AFFINE', 'Affine'), ('ROTATION', 'Rotation'), ('SEQUENCE', 'Sequence'), ('BY_DIMENSION', 'By Dimension'), ('FIELD', 'Field (a map given by the values of an array)'), ('BIJECTION', 'Bijection'), ('UNMAPPABLE', 'Unmappable (a declared non-correspondence)')], choices_enum=core.enums.TransformKindChoices, default='IDENTITY', help_text='The kind of transformation, which fixes how `params` is interpreted', max_length=12),
        ),
    ]
