"""A scene unit gets a denominator: help_text only, no schema change (RFC-8).

`point_size`, `line_width` and `stroke_width` are scalar lengths in a space whose axes
need not share a scale, and nothing said what they were denominated in. RFC-8 defines a
scene unit as the world's spatial-axis unit, well defined for a layer exactly when its
path to world preserves lengths up to one common factor -- which `placementInvariance`
now reports. These fields say so.

`help_text` is not a database concern, so every operation here is state-only: Django
records the new field definition and emits no SQL. It exists because `help_text` rides in
a field's deconstruction, so without it `makemigrations --check` fails forever.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0039_alter_axis_unit'),
    ]

    operations = [
        migrations.AlterField(
            model_name='annotation',
            name='stroke_width',
            field=models.FloatField(default=1.0, help_text="The stroke width of the geometry, in the drawing space's units. One number for every direction, so it is a well-defined length only where that space's axes share a scale (RFC-8)"),
        ),
        migrations.AlterField(
            model_name='historicalannotation',
            name='stroke_width',
            field=models.FloatField(default=1.0, help_text="The stroke width of the geometry, in the drawing space's units. One number for every direction, so it is a well-defined length only where that space's axes share a scale (RFC-8)"),
        ),
        migrations.AlterField(
            model_name='historicallayer',
            name='line_width',
            field=models.FloatField(blank=True, help_text="(track) The width of the track lines, in scene units -- the world's spatial-axis unit, which is a well-defined length for a layer only when its `placementInvariance` is SIMILARITY or better (RFC-8)", null=True),
        ),
        migrations.AlterField(
            model_name='historicallayer',
            name='point_size',
            field=models.FloatField(blank=True, help_text="(point) The default point size, in scene units -- the world's spatial-axis unit, which is a well-defined length for a layer only when its `placementInvariance` is SIMILARITY or better (RFC-8)", null=True),
        ),
        migrations.AlterField(
            model_name='layer',
            name='line_width',
            field=models.FloatField(blank=True, help_text="(track) The width of the track lines, in scene units -- the world's spatial-axis unit, which is a well-defined length for a layer only when its `placementInvariance` is SIMILARITY or better (RFC-8)", null=True),
        ),
        migrations.AlterField(
            model_name='layer',
            name='point_size',
            field=models.FloatField(blank=True, help_text="(point) The default point size, in scene units -- the world's spatial-axis unit, which is a well-defined length for a layer only when its `placementInvariance` is SIMILARITY or better (RFC-8)", null=True),
        ),
    ]
