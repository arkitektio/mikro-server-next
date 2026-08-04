"""A dataset may nominate the scene to open for it, and take its thumbnail from.

A *choice*, not a derived fact -- which is what makes it storable. `ADataset.scenes` remains
the derived answer to which scenes show a dataset; this says which one a person wants opened,
which nothing in the coordinate graph can know.

`latestSnapshot` reads it, replacing a five-query sole-occupancy walk that returned null for
any dataset staged alongside another. Run `backfill_default_scenes` after applying this, or
existing datasets show no thumbnail.
"""


import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_file_links'),
    ]

    operations = [
        migrations.AddField(
            model_name='adataset',
            name='default_scene',
            field=models.ForeignKey(blank=True, help_text='The scene to open for this dataset, and the one its thumbnail is taken from. Bookkeeping only: it claims nothing about where the data sits and is not an answer to which scenes *show* this dataset -- that is `scenes`, a question the coordinate graph answers. Several datasets may nominate one scene. Cleared, not cascaded, when the scene is deleted', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='default_for', to='core.scene'),
        ),
        migrations.AddField(
            model_name='historicaladataset',
            name='default_scene',
            field=models.ForeignKey(blank=True, db_constraint=False, help_text='The scene to open for this dataset, and the one its thumbnail is taken from. Bookkeeping only: it claims nothing about where the data sits and is not an answer to which scenes *show* this dataset -- that is `scenes`, a question the coordinate graph answers. Several datasets may nominate one scene. Cleared, not cascaded, when the scene is deleted', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='core.scene'),
        ),
    ]
