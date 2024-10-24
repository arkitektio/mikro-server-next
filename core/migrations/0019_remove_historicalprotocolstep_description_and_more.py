# Generated by Django 4.2.8 on 2024-10-23 14:23

import core.enums
from django.db import migrations, models
import django.db.models.deletion
import django_choices_field.fields


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0018_historicalprotocolsteptemplate_protocolsteptemplate_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="historicalprotocolstep",
            name="description",
        ),
        migrations.RemoveField(
            model_name="historicalprotocolstep",
            name="expression",
        ),
        migrations.RemoveField(
            model_name="historicalprotocolstep",
            name="kind",
        ),
        migrations.RemoveField(
            model_name="historicalprotocolstep",
            name="name",
        ),
        migrations.RemoveField(
            model_name="historicalprotocolstep",
            name="used_entity_id",
        ),
        migrations.RemoveField(
            model_name="historicalprotocolstep",
            name="used_reagent",
        ),
        migrations.RemoveField(
            model_name="historicalprotocolstep",
            name="used_reagent_mass",
        ),
        migrations.RemoveField(
            model_name="historicalprotocolstep",
            name="used_reagent_volume",
        ),
        migrations.RemoveField(
            model_name="protocolstep",
            name="description",
        ),
        migrations.RemoveField(
            model_name="protocolstep",
            name="expression",
        ),
        migrations.RemoveField(
            model_name="protocolstep",
            name="kind",
        ),
        migrations.RemoveField(
            model_name="protocolstep",
            name="name",
        ),
        migrations.RemoveField(
            model_name="protocolstep",
            name="used_entity_id",
        ),
        migrations.RemoveField(
            model_name="protocolstep",
            name="used_reagent",
        ),
        migrations.RemoveField(
            model_name="protocolstep",
            name="used_reagent_mass",
        ),
        migrations.RemoveField(
            model_name="protocolstep",
            name="used_reagent_volume",
        ),
        migrations.AddField(
            model_name="historicalprotocolstep",
            name="template",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                help_text="The template that was used to create the step",
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="core.protocolsteptemplate",
            ),
        ),
        migrations.AddField(
            model_name="historicalprotocolstep",
            name="variable_mappings",
            field=models.JSONField(
                blank=True,
                help_text="A mapping of variables to values for this step",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="historicalprotocolsteptemplate",
            name="kind",
            field=django_choices_field.fields.TextChoicesField(
                choices=[
                    ("PREP", "Preperation"),
                    ("ADD_REAGENT", "Add Reagent"),
                    ("MEASUREMENT", "Measurement"),
                    ("STORAGE", "Storage"),
                    ("CUSTOM", "Custom"),
                    ("UNKNOWN", "Unknown"),
                ],
                choices_enum=core.enums.ProtocolStepKindChoices,
                default="UNKNOWN",
                help_text="The kind of the step (can be more closely defined in the expression)",
                max_length=11,
            ),
        ),
        migrations.AddField(
            model_name="protocolstep",
            name="template",
            field=models.ForeignKey(
                help_text="The template that was used to create the step",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="steps",
                to="core.protocolsteptemplate",
            ),
        ),
        migrations.AddField(
            model_name="protocolstep",
            name="variable_mappings",
            field=models.JSONField(
                blank=True,
                help_text="A mapping of variables to values for this step",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="protocolsteptemplate",
            name="kind",
            field=django_choices_field.fields.TextChoicesField(
                choices=[
                    ("PREP", "Preperation"),
                    ("ADD_REAGENT", "Add Reagent"),
                    ("MEASUREMENT", "Measurement"),
                    ("STORAGE", "Storage"),
                    ("CUSTOM", "Custom"),
                    ("UNKNOWN", "Unknown"),
                ],
                choices_enum=core.enums.ProtocolStepKindChoices,
                default="UNKNOWN",
                help_text="The kind of the step (can be more closely defined in the expression)",
                max_length=11,
            ),
        ),
        migrations.CreateModel(
            name="ReagentMapping",
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
                    "volume",
                    models.FloatField(
                        help_text="The volume of the reagent in the protocol in µl. If you add some mass of a reagent, you can use the mass field instead.",
                        null=True,
                    ),
                ),
                (
                    "mass",
                    models.FloatField(
                        help_text="The mass of the reagent in the protocol in µg. If you add some volume of a reagent, you can use the volume field instead."
                    ),
                ),
                (
                    "protocol_step",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reagent_mappings",
                        to="core.protocolstep",
                    ),
                ),
                (
                    "reagent",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mappings",
                        to="core.reagent",
                    ),
                ),
            ],
        ),
    ]
