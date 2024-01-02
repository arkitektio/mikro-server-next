# Generated by Django 4.2.3 on 2023-08-02 14:17

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0009_historicalsnapshot_name_snapshot_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="dataset",
            name="creator",
            field=models.ForeignKey(
                default=1,
                help_text="The user that created the dataset",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="created_datasets",
                to=settings.AUTH_USER_MODEL,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="dataset",
            name="is_default",
            field=models.BooleanField(
                default=False,
                help_text="Whether the dataset is the current default dataset for the user",
            ),
        ),
        migrations.AddField(
            model_name="historicaldataset",
            name="creator",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                help_text="The user that created the dataset",
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="historicaldataset",
            name="is_default",
            field=models.BooleanField(
                default=False,
                help_text="Whether the dataset is the current default dataset for the user",
            ),
        ),
        migrations.AlterField(
            model_name="channel",
            name="color",
            field=models.CharField(
                blank=True,
                help_text="The default color for the channel ",
                max_length=1000,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="dataset",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True, help_text="The time the dataset was created"
            ),
        ),
        migrations.AlterField(
            model_name="dataset",
            name="description",
            field=models.CharField(
                blank=True,
                help_text="The description of the dataset",
                max_length=1000,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="dataset",
            name="name",
            field=models.CharField(help_text="The name of the dataset", max_length=200),
        ),
        migrations.AlterField(
            model_name="dataset",
            name="pinned_by",
            field=models.ManyToManyField(
                blank=True,
                help_text="The users that have pinned the dataset",
                related_name="pinned_datasets",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="historicalchannel",
            name="color",
            field=models.CharField(
                blank=True,
                help_text="The default color for the channel ",
                max_length=1000,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="historicaldataset",
            name="created_at",
            field=models.DateTimeField(
                blank=True, editable=False, help_text="The time the dataset was created"
            ),
        ),
        migrations.AlterField(
            model_name="historicaldataset",
            name="description",
            field=models.CharField(
                blank=True,
                help_text="The description of the dataset",
                max_length=1000,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="historicaldataset",
            name="name",
            field=models.CharField(help_text="The name of the dataset", max_length=200),
        ),
        migrations.AddConstraint(
            model_name="dataset",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_default", True)),
                fields=("creator", "is_default"),
                name="unique_default_per_creator",
            ),
        ),
    ]
