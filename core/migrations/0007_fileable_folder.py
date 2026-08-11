"""Give the four containers a folder, so everything fileable can be filed.

``Image``, ``File`` and ``Table`` have always had one. ``ADataset``, ``TableDataset``,
``MeshCollection`` and ``AnnotationCollection`` -- the same four ``FileLink`` treats as
"a container holding data" -- did not, so the newer half of the model had no place in the
folder tree at all.

Nullable, and deliberately not backfilled: a row that predates the column has no true
answer, and inventing one would file every existing dataset somewhere nobody chose. New
rows are filed by the create mutations, which fall back to the user's default folder the
way ``create_image_from_array`` always has.

``on_delete=CASCADE`` matches ``Image.folder``: deleting a folder deletes what is filed in
it. That is a wider blast radius than it was yesterday -- a folder now takes datasets and
their arrays with it -- and it bypasses the per-object delete guards, exactly as it
already did for images.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_dataset_to_folder'),
    ]

    operations = [
        migrations.AddField(
            model_name='adataset',
            name='folder',
            field=models.ForeignKey(blank=True, help_text='The folder this dataset is filed in. Organisational only -- it says nothing about where the data sits in space', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='adatasets', to='core.folder'),
        ),
        migrations.AddField(
            model_name='annotationcollection',
            name='folder',
            field=models.ForeignKey(blank=True, help_text='The folder this annotation collection is filed in. Organisational only -- it says nothing about the space the shapes are drawn in', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='annotation_collections', to='core.folder'),
        ),
        migrations.AddField(
            model_name='historicaladataset',
            name='folder',
            field=models.ForeignKey(blank=True, db_constraint=False, help_text='The folder this dataset is filed in. Organisational only -- it says nothing about where the data sits in space', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='core.folder'),
        ),
        migrations.AddField(
            model_name='historicalannotationcollection',
            name='folder',
            field=models.ForeignKey(blank=True, db_constraint=False, help_text='The folder this annotation collection is filed in. Organisational only -- it says nothing about the space the shapes are drawn in', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='core.folder'),
        ),
        migrations.AddField(
            model_name='historicalmeshcollection',
            name='folder',
            field=models.ForeignKey(blank=True, db_constraint=False, help_text='The folder this mesh collection is filed in. Organisational only -- it says nothing about where the meshes sit in space', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='core.folder'),
        ),
        migrations.AddField(
            model_name='historicaltabledataset',
            name='folder',
            field=models.ForeignKey(blank=True, db_constraint=False, help_text='The folder this table dataset is filed in. Organisational only -- it says nothing about where the rows sit in space', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='core.folder'),
        ),
        migrations.AddField(
            model_name='meshcollection',
            name='folder',
            field=models.ForeignKey(blank=True, help_text='The folder this mesh collection is filed in. Organisational only -- it says nothing about where the meshes sit in space', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='mesh_collections', to='core.folder'),
        ),
        migrations.AddField(
            model_name='tabledataset',
            name='folder',
            field=models.ForeignKey(blank=True, help_text='The folder this table dataset is filed in. Organisational only -- it says nothing about where the rows sit in space', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='table_datasets', to='core.folder'),
        ),
    ]
