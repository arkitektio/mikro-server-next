# Generated by Django 4.2.8 on 2024-07-29 11:16

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import simple_history.models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("authentikate", "0002_alter_user_unique_together_and_more"),
        ("core", "0003_rename_of_entity_parent_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="EntityGroup",
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
                    "name",
                    models.CharField(
                        help_text="The name of the entity group", max_length=1000
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="HistoricalEntityGroup",
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
                    "name",
                    models.CharField(
                        help_text="The name of the entity group", max_length=1000
                    ),
                ),
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
                    "history_relation",
                    models.ForeignKey(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="provenance",
                        to="core.entitygroup",
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
            ],
            options={
                "verbose_name": "historical entity group",
                "verbose_name_plural": "historical entity groups",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.AddField(
            model_name="entity",
            name="group",
            field=models.ForeignKey(
                default=1,
                help_text="The group this entity belongs to",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="entities",
                to="core.entitygroup",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="historicalentity",
            name="group",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                help_text="The group this entity belongs to",
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="core.entitygroup",
            ),
        ),
    ]
