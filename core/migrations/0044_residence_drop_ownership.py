"""Ownership is gone: a coordinate system is a pure node (RFC-9).

The destructive half of the series 0042 (add the residence columns) / 0043 (fill them) /
this. Drops all seven owner FKs from `coordinatesystem` and `historicalcoordinatesystem`,
after which a space knows nothing about what lives in it and answers `residents` by asking
who points at it.

`dataset` -- the calibration FK -- goes with the rest and nothing replaces it. A calibrated
space becomes an ordinary space with an edge into it, which is all it ever was; the edge was
already stored, so no geometry moves.

Separate from 0043 on purpose: Postgres refuses DDL on a table with pending FK trigger events
from DML earlier in the same transaction, and a migration is one transaction. This repo has
shipped that failure once already (0013).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentikate', '0006_alter_app_identifier_alter_release_unique_together'),
        ('core', '0043_residence_backfill'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveField(
            model_name='coordinatesystem',
            name='annotation_collection',
        ),
        migrations.RemoveField(
            model_name='coordinatesystem',
            name='data_array',
        ),
        migrations.RemoveField(
            model_name='coordinatesystem',
            name='dataset',
        ),
        migrations.RemoveField(
            model_name='coordinatesystem',
            name='intrinsic_of',
        ),
        migrations.RemoveField(
            model_name='coordinatesystem',
            name='lens',
        ),
        migrations.RemoveField(
            model_name='coordinatesystem',
            name='mesh_collection',
        ),
        migrations.RemoveField(
            model_name='coordinatesystem',
            name='table_dataset',
        ),
        migrations.RemoveField(
            model_name='historicalcoordinatesystem',
            name='annotation_collection',
        ),
        migrations.RemoveField(
            model_name='historicalcoordinatesystem',
            name='data_array',
        ),
        migrations.RemoveField(
            model_name='historicalcoordinatesystem',
            name='dataset',
        ),
        migrations.RemoveField(
            model_name='historicalcoordinatesystem',
            name='intrinsic_of',
        ),
        migrations.RemoveField(
            model_name='historicalcoordinatesystem',
            name='lens',
        ),
        migrations.RemoveField(
            model_name='historicalcoordinatesystem',
            name='mesh_collection',
        ),
        migrations.RemoveField(
            model_name='historicalcoordinatesystem',
            name='table_dataset',
        ),
        migrations.AlterField(
            model_name='coordinatesystem',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, help_text='The time this coordinate space was created'),
        ),
        migrations.AlterField(
            model_name='coordinatesystem',
            name='creator',
            field=models.ForeignKey(blank=True, help_text='The user that created this coordinate space', null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='coordinatesystem',
            name='epoch',
            field=models.DateTimeField(blank=True, help_text="The wall-clock instant this system's time axis has its origin at, so that `wall_clock = epoch + t * unit`. A property of the *space*, not of any composition over it -- two scenes sharing one space cannot disagree about when its clock starts. Meaningful only for a space with a calibrated TIME axis; optional even there: an unanchored clock is still a perfectly composable relative coordinate", null=True),
        ),
        migrations.AlterField(
            model_name='coordinatesystem',
            name='name',
            field=models.CharField(help_text='The name of the coordinate space', max_length=255),
        ),
        migrations.AlterField(
            model_name='coordinatesystem',
            name='organization',
            field=models.ForeignKey(help_text='The organization this coordinate space belongs to', on_delete=django.db.models.deletion.CASCADE, to='authentikate.organization'),
        ),
        migrations.AlterField(
            model_name='historicalcoordinatesystem',
            name='created_at',
            field=models.DateTimeField(blank=True, editable=False, help_text='The time this coordinate space was created'),
        ),
        migrations.AlterField(
            model_name='historicalcoordinatesystem',
            name='creator',
            field=models.ForeignKey(blank=True, db_constraint=False, help_text='The user that created this coordinate space', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='historicalcoordinatesystem',
            name='epoch',
            field=models.DateTimeField(blank=True, help_text="The wall-clock instant this system's time axis has its origin at, so that `wall_clock = epoch + t * unit`. A property of the *space*, not of any composition over it -- two scenes sharing one space cannot disagree about when its clock starts. Meaningful only for a space with a calibrated TIME axis; optional even there: an unanchored clock is still a perfectly composable relative coordinate", null=True),
        ),
        migrations.AlterField(
            model_name='historicalcoordinatesystem',
            name='name',
            field=models.CharField(help_text='The name of the coordinate space', max_length=255),
        ),
        migrations.AlterField(
            model_name='historicalcoordinatesystem',
            name='organization',
            field=models.ForeignKey(blank=True, db_constraint=False, help_text='The organization this coordinate space belongs to', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='authentikate.organization'),
        ),
    ]
