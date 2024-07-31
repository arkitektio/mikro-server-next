# Generated by Django 4.2.8 on 2024-07-31 16:44

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import simple_history.models


class Migration(migrations.Migration):
    dependencies = [
        ("authentikate", "0002_alter_user_unique_together_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0012_remove_historicalantibody_app_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScaleView",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "z_min",
                    models.IntegerField(
                        blank=True, help_text="The index of the channel", null=True
                    ),
                ),
                (
                    "z_max",
                    models.IntegerField(
                        blank=True, help_text="The index of the channel", null=True
                    ),
                ),
                (
                    "x_min",
                    models.IntegerField(
                        blank=True, help_text="The index of the channel", null=True
                    ),
                ),
                (
                    "x_max",
                    models.IntegerField(
                        blank=True, help_text="The index of the channel", null=True
                    ),
                ),
                (
                    "y_min",
                    models.IntegerField(
                        blank=True, help_text="The index of the channel", null=True
                    ),
                ),
                (
                    "y_max",
                    models.IntegerField(
                        blank=True, help_text="The index of the channel", null=True
                    ),
                ),
                (
                    "t_min",
                    models.IntegerField(
                        blank=True, help_text="The index of the channel", null=True
                    ),
                ),
                (
                    "t_max",
                    models.IntegerField(
                        blank=True, help_text="The index of the channel", null=True
                    ),
                ),
                (
                    "c_min",
                    models.IntegerField(
                        blank=True, help_text="The index of the channel", null=True
                    ),
                ),
                (
                    "c_max",
                    models.IntegerField(
                        blank=True, help_text="The index of the channel", null=True
                    ),
                ),
                (
                    "is_global",
                    models.BooleanField(
                        default=False, help_text="Whether the view is global or not"
                    ),
                ),
                ("scale_x", models.FloatField(help_text="The scale in x direction")),
                ("scale_y", models.FloatField(help_text="The scale in y direction")),
                ("scale_z", models.FloatField(help_text="The scale in z direction")),
                ("scale_t", models.FloatField(help_text="The scale in t direction")),
                ("scale_c", models.FloatField(help_text="The scale in c direction")),
                (
                    "collection",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="core.viewcollection",
                    ),
                ),
                (
                    "image",
                    simple_history.models.HistoricForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="core.image"
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="derived_scale_views",
                        to="core.image",
                    ),
                ),
            ],
            options={
                "default_related_name": "scale_views",
            },
        ),
        migrations.CreateModel(
            name="HistoricalScaleView",
            fields=[
                (
                    "id",
                    models.BigIntegerField(
                        auto_created=True, blank=True, db_index=True, verbose_name="ID"
                    ),
                ),
                (
                    "assignation_id",
                    models.CharField(blank=True, max_length=1000, null=True),
                ),
                (
                    "z_min",
                    models.IntegerField(
                        blank=True, help_text="The index of the channel", null=True
                    ),
                ),
                (
                    "z_max",
                    models.IntegerField(
                        blank=True, help_text="The index of the channel", null=True
                    ),
                ),
                (
                    "x_min",
                    models.IntegerField(
                        blank=True, help_text="The index of the channel", null=True
                    ),
                ),
                (
                    "x_max",
                    models.IntegerField(
                        blank=True, help_text="The index of the channel", null=True
                    ),
                ),
                (
                    "y_min",
                    models.IntegerField(
                        blank=True, help_text="The index of the channel", null=True
                    ),
                ),
                (
                    "y_max",
                    models.IntegerField(
                        blank=True, help_text="The index of the channel", null=True
                    ),
                ),
                (
                    "t_min",
                    models.IntegerField(
                        blank=True, help_text="The index of the channel", null=True
                    ),
                ),
                (
                    "t_max",
                    models.IntegerField(
                        blank=True, help_text="The index of the channel", null=True
                    ),
                ),
                (
                    "c_min",
                    models.IntegerField(
                        blank=True, help_text="The index of the channel", null=True
                    ),
                ),
                (
                    "c_max",
                    models.IntegerField(
                        blank=True, help_text="The index of the channel", null=True
                    ),
                ),
                (
                    "is_global",
                    models.BooleanField(
                        default=False, help_text="Whether the view is global or not"
                    ),
                ),
                ("scale_x", models.FloatField(help_text="The scale in x direction")),
                ("scale_y", models.FloatField(help_text="The scale in y direction")),
                ("scale_z", models.FloatField(help_text="The scale in z direction")),
                ("scale_t", models.FloatField(help_text="The scale in t direction")),
                ("scale_c", models.FloatField(help_text="The scale in c direction")),
                ("history_id", models.AutoField(primary_key=True, serialize=False)),
                ("history_date", models.DateTimeField(db_index=True)),
                ("history_change_reason", models.CharField(max_length=100, null=True)),
                (
                    "history_type",
                    models.CharField(
                        choices=[("+", "Created"), ("~", "Changed"), ("-", "Deleted")],
                        max_length=1,
                    ),
                ),
                (
                    "app",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="authentikate.app",
                    ),
                ),
                (
                    "collection",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="core.viewcollection",
                    ),
                ),
                (
                    "history_relation",
                    models.ForeignKey(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="provenance",
                        to="core.scaleview",
                    ),
                ),
                (
                    "history_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "image",
                    simple_history.models.HistoricForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="core.image",
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="core.image",
                    ),
                ),
            ],
            options={
                "verbose_name": "historical scale view",
                "verbose_name_plural": "historical scale views",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
    ]
