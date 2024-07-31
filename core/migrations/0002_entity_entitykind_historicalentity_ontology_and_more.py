# Generated by Django 4.2.8 on 2024-07-29 11:11

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import simple_history.models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("authentikate", "0002_alter_user_unique_together_and_more"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Entity",
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
                        help_text="The name of the entity", max_length=1000
                    ),
                ),
                (
                    "index",
                    models.IntegerField(
                        default=0, help_text="The index of the entity in the image"
                    ),
                ),
            ],
            options={
                "default_related_name": "entities",
            },
        ),
        migrations.CreateModel(
            name="EntityKind",
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
                    "ontology",
                    models.CharField(
                        blank=True,
                        help_text="The ontology of the entity class. This should be a world wide accepted ontology",
                        max_length=1000,
                        null=True,
                    ),
                ),
                (
                    "label",
                    models.CharField(
                        help_text="The label of the entity class",
                        max_length=1000,
                        null=True,
                    ),
                ),
                (
                    "description",
                    models.CharField(
                        help_text="The description of the entity class",
                        max_length=1000,
                        null=True,
                    ),
                ),
                (
                    "is_roughly_equivalent_to",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="core.entitykind",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="HistoricalEntity",
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
                        help_text="The name of the entity", max_length=1000
                    ),
                ),
                (
                    "index",
                    models.IntegerField(
                        default=0, help_text="The index of the entity in the image"
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
                        to="core.entity",
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
                    "kind",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        help_text="The type of the entity",
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="core.entitykind",
                    ),
                ),
                (
                    "of",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        help_text="The entity this entity is part of",
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="core.entity",
                    ),
                ),
            ],
            options={
                "verbose_name": "historical entity",
                "verbose_name_plural": "historical entitys",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name="Ontology",
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
                        help_text="The name of the ontology", max_length=1000
                    ),
                ),
                (
                    "description",
                    models.CharField(
                        help_text="The description of the ontology", max_length=1000
                    ),
                ),
                (
                    "public_url",
                    models.CharField(
                        help_text="The public url of the ontology",
                        max_length=1000,
                        null=True,
                    ),
                ),
                (
                    "default",
                    models.BooleanField(
                        default=False,
                        help_text="Whether the ontology is the default ontology",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="PixelLabel",
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
                ("value", models.FloatField()),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now=True, help_text="The time the ROI was created"
                    ),
                ),
                (
                    "label",
                    models.CharField(
                        blank=True,
                        help_text="The label of the ROI (for UI)",
                        max_length=1000,
                        null=True,
                    ),
                ),
                (
                    "entity",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="pixel_labels",
                        to="core.entity",
                    ),
                ),
                (
                    "pinned_by",
                    models.ManyToManyField(
                        blank=True,
                        help_text="The users that pinned this ROI",
                        related_name="pinned_labels",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="historicalpixelview",
            name="is_instance_mask",
            field=models.BooleanField(
                default=False, help_text="Whether the pixel view is an instance mask"
            ),
        ),
        migrations.AddField(
            model_name="pixelview",
            name="is_instance_mask",
            field=models.BooleanField(
                default=False, help_text="Whether the pixel view is an instance mask"
            ),
        ),
        migrations.DeleteModel(
            name="Label",
        ),
        migrations.AddField(
            model_name="pixellabel",
            name="view",
            field=models.ForeignKey(
                blank=True,
                help_text="The Representation this ROI was original used to create (drawn on)",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="labels",
                to="core.pixelview",
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="kind",
            field=models.ForeignKey(
                help_text="The type of the entity",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="entities",
                to="core.entitykind",
            ),
        ),
        migrations.AddField(
            model_name="entity",
            name="of",
            field=models.ForeignKey(
                blank=True,
                help_text="The entity this entity is part of",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="parts",
                to="core.entity",
            ),
        ),
        migrations.AddField(
            model_name="roi",
            name="entity",
            field=models.ForeignKey(
                blank=True,
                help_text="The entity this ROI belongs to",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="rois",
                to="core.entity",
            ),
        ),
        migrations.AddConstraint(
            model_name="entity",
            constraint=models.UniqueConstraint(
                fields=("kind", "name"), name="unique_entity_kind_name"
            ),
        ),
    ]
