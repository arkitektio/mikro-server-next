"""File links replace the dead `origins` M2Ms.

`File.origins` and `Table.origins` were File->File and Table->Table many-to-many columns that
no resolver ever wrote, exposed in the SDL under the wrong type (`[Image!]!`). They are dropped
rather than migrated: there is nothing in them to carry over.

What replaces them is `FileLink`, which says the thing they were reaching for and could not --
that a container was converted out of a file, or written out to one. Deliberately not a
`Transformation`: a derivation is an edge of the coordinate graph and relates two spaces, and a
file has none. See the model docstring for the full argument.
"""

import core.enums
import django.db.models.deletion
import django_choices_field.fields
import simple_history.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentikate', '0006_alter_app_identifier_alter_release_unique_together'),
        ('core', '0001_initial'),
        ('koherent', '0003_rename_assignation_to_task'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveField(
            model_name='file',
            name='origins',
        ),
        migrations.RemoveField(
            model_name='table',
            name='origins',
        ),
        migrations.CreateModel(
            name='FileLink',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('direction', django_choices_field.fields.TextChoicesField(choices=[('SOURCE', 'Source (the container was made from the file)'), ('RENDITION', 'Rendition (the file was written from the container)')], choices_enum=core.enums.FileLinkDirectionChoices, help_text='Which side was made from the other: SOURCE for an ingest (the file existed first), RENDITION for an export (the container did). Stored because nothing else records it', max_length=9)),
                ('series_identifier', models.CharField(blank=True, default='', help_text="Which part of the file this link concerns -- the series of a multi-series LIF or CZI. Empty when the file holds one thing. Part of the link's identity, so one dataset fused from two series of one file is two links", max_length=1000)),
                ('value_relation', django_choices_field.fields.TextChoicesField(blank=True, choices=[('IDENTICAL', "Identical (the source's numbers)"), ('TRANSFORMED', 'Transformed (same quantity, new numbers)'), ('CATEGORIZED', 'Categorized (values became labels)')], choices_enum=core.enums.ValueRelationChoices, help_text='What the conversion did to the values: IDENTICAL for a lossless transcode, TRANSFORMED for a projection written to PNG. Null means unstated', max_length=11, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('annotation_collection', models.ForeignKey(blank=True, help_text='(ANNOTATION_COLLECTION) The annotation collection side of the link', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='file_links', to='core.annotationcollection')),
                ('created_through', models.ForeignKey(blank=True, help_text='The task this object was created through, if any', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_%(class)ss', to='koherent.task')),
                ('created_through_by', models.ForeignKey(blank=True, help_text='The assigner of the creating task, denormalized for fast filtering', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_%(class)ss', to=settings.AUTH_USER_MODEL)),
                ('creator', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='file_links', to=settings.AUTH_USER_MODEL)),
                ('dataset', models.ForeignKey(blank=True, help_text='(DATASET) The array dataset side of the link', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='file_links', to='core.adataset')),
                ('file', models.ForeignKey(help_text='The file side of the link', on_delete=django.db.models.deletion.CASCADE, related_name='links', to='core.file')),
                ('mesh_collection', models.ForeignKey(blank=True, help_text='(MESH_COLLECTION) The mesh collection side of the link', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='file_links', to='core.meshcollection')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='file_links', to='authentikate.organization')),
                ('table_dataset', models.ForeignKey(blank=True, help_text='(TABLE_DATASET) The table dataset side of the link', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='file_links', to='core.tabledataset')),
            ],
        ),
        migrations.CreateModel(
            name='HistoricalFileLink',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('direction', django_choices_field.fields.TextChoicesField(choices=[('SOURCE', 'Source (the container was made from the file)'), ('RENDITION', 'Rendition (the file was written from the container)')], choices_enum=core.enums.FileLinkDirectionChoices, help_text='Which side was made from the other: SOURCE for an ingest (the file existed first), RENDITION for an export (the container did). Stored because nothing else records it', max_length=9)),
                ('series_identifier', models.CharField(blank=True, default='', help_text="Which part of the file this link concerns -- the series of a multi-series LIF or CZI. Empty when the file holds one thing. Part of the link's identity, so one dataset fused from two series of one file is two links", max_length=1000)),
                ('value_relation', django_choices_field.fields.TextChoicesField(blank=True, choices=[('IDENTICAL', "Identical (the source's numbers)"), ('TRANSFORMED', 'Transformed (same quantity, new numbers)'), ('CATEGORIZED', 'Categorized (values became labels)')], choices_enum=core.enums.ValueRelationChoices, help_text='What the conversion did to the values: IDENTICAL for a lossless transcode, TRANSFORMED for a projection written to PNG. Null means unstated', max_length=11, null=True)),
                ('created_at', models.DateTimeField(blank=True, editable=False)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('annotation_collection', models.ForeignKey(blank=True, db_constraint=False, help_text='(ANNOTATION_COLLECTION) The annotation collection side of the link', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='core.annotationcollection')),
                ('client', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='authentikate.client')),
                ('created_through', models.ForeignKey(blank=True, db_constraint=False, help_text='The task this object was created through, if any', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='koherent.task')),
                ('created_through_by', models.ForeignKey(blank=True, db_constraint=False, help_text='The assigner of the creating task, denormalized for fast filtering', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('creator', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('dataset', models.ForeignKey(blank=True, db_constraint=False, help_text='(DATASET) The array dataset side of the link', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='core.adataset')),
                ('file', models.ForeignKey(blank=True, db_constraint=False, help_text='The file side of the link', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='core.file')),
                ('history_relation', models.ForeignKey(db_constraint=False, on_delete=django.db.models.deletion.DO_NOTHING, related_name='provenance_entries', to='core.filelink')),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('mesh_collection', models.ForeignKey(blank=True, db_constraint=False, help_text='(MESH_COLLECTION) The mesh collection side of the link', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='core.meshcollection')),
                ('organization', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='authentikate.organization')),
                ('table_dataset', models.ForeignKey(blank=True, db_constraint=False, help_text='(TABLE_DATASET) The table dataset side of the link', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='core.tabledataset')),
                ('task', models.ForeignKey(blank=True, help_text='The task during which the change occurred, if any', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='koherent.task')),
            ],
            options={
                'verbose_name': 'historical file link',
                'verbose_name_plural': 'historical file links',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.AddConstraint(
            model_name='filelink',
            constraint=models.UniqueConstraint(condition=models.Q(('dataset__isnull', False)), fields=('file', 'dataset', 'direction', 'series_identifier'), name='unique_file_link_per_dataset'),
        ),
        migrations.AddConstraint(
            model_name='filelink',
            constraint=models.UniqueConstraint(condition=models.Q(('table_dataset__isnull', False)), fields=('file', 'table_dataset', 'direction', 'series_identifier'), name='unique_file_link_per_table_dataset'),
        ),
        migrations.AddConstraint(
            model_name='filelink',
            constraint=models.UniqueConstraint(condition=models.Q(('mesh_collection__isnull', False)), fields=('file', 'mesh_collection', 'direction', 'series_identifier'), name='unique_file_link_per_mesh_collection'),
        ),
        migrations.AddConstraint(
            model_name='filelink',
            constraint=models.UniqueConstraint(condition=models.Q(('annotation_collection__isnull', False)), fields=('file', 'annotation_collection', 'direction', 'series_identifier'), name='unique_file_link_per_annotation_collection'),
        ),
    ]
