"""A table column's unit is no longer the coordinate's alone.

An `ATTRIBUTE` column may now state the unit its values are in -- an area in
'micrometer**2', a marker level in 'a.u.' -- which is the fact a client plotting it needs
and the fact `attributePlans` hands a worker along with the column. The roles that are not
measured (an id, a track id, a label, a colour) still refuse one.

Help text only: the column has always been a nullable CharField and stays one. What changed
is the input -- `TableColumnInput.unit` is now the pint-validated `Unit` scalar, so an
unparseable unit is refused at the API boundary rather than stored and discovered later.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_adataset_default_scene'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tablecolumn',
            name='unit',
            field=models.CharField(blank=True, help_text="The unit the column's values are in, e.g. 'nanometer' for a coordinate or 'micrometer**2' for a measured area. A pint unit, validated at the API boundary. Null for pixel-index coordinates and for anything not measured (an id, a label, a colour, which refuse one)", max_length=64, null=True),
        ),
    ]
