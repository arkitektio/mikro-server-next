"""Deleting a folder unfiles its contents; it never destroys them.

Every ``folder`` FK moves from CASCADE to SET_NULL -- the four containers added in 0007,
and the four older holders (``Image``, ``File``, ``Table``, and the three ``Render``
subclasses from one abstract line) that have been CASCADE since long before this.

A folder is organisational. Deleting one is a statement about where things are kept, not
about whether they should exist, and CASCADE made it the second thing: it destroyed data
through the database relation, which also meant the per-object delete guards
(``self_owner`` on ``deleteADataset``) never ran. Deletion of the data itself stays where
it belongs, on the delete mutation for the thing.

``File.folder`` additionally becomes nullable. It was the one holder declared NOT NULL,
which made ``releaseFilesFromFolder`` -- a mutation that has always set it to None -- an
``IntegrityError`` on every call. Nullable is what that mutation always assumed.

No historical twins here: history FKs are already nullable ``DO_NOTHING``, so neither the
nullability nor the delete rule is a fact they carry.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_fileable_folder'),
    ]

    operations = [
        migrations.AlterField(
            model_name='adataset',
            name='folder',
            field=models.ForeignKey(blank=True, help_text='The folder this dataset is filed in. Organisational only -- it says nothing about where the data sits in space', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='adatasets', to='core.folder'),
        ),
        migrations.AlterField(
            model_name='annotationcollection',
            name='folder',
            field=models.ForeignKey(blank=True, help_text='The folder this annotation collection is filed in. Organisational only -- it says nothing about the space the shapes are drawn in', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='annotation_collections', to='core.folder'),
        ),
        migrations.AlterField(
            model_name='blurhash',
            name='folder',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.folder'),
        ),
        migrations.AlterField(
            model_name='file',
            name='folder',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='files', to='core.folder'),
        ),
        migrations.AlterField(
            model_name='image',
            name='folder',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='images', to='core.folder'),
        ),
        migrations.AlterField(
            model_name='meshcollection',
            name='folder',
            field=models.ForeignKey(blank=True, help_text='The folder this mesh collection is filed in. Organisational only -- it says nothing about where the meshes sit in space', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='mesh_collections', to='core.folder'),
        ),
        migrations.AlterField(
            model_name='snapshot',
            name='folder',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.folder'),
        ),
        migrations.AlterField(
            model_name='table',
            name='folder',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tables', to='core.folder'),
        ),
        migrations.AlterField(
            model_name='tabledataset',
            name='folder',
            field=models.ForeignKey(blank=True, help_text='The folder this table dataset is filed in. Organisational only -- it says nothing about where the rows sit in space', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='table_datasets', to='core.folder'),
        ),
        migrations.AlterField(
            model_name='video',
            name='folder',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.folder'),
        ),
    ]
