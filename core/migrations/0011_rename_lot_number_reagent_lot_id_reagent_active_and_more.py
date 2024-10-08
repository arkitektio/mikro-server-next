# Generated by Django 4.2.8 on 2024-09-12 10:03

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0010_remove_reagent_concentration_remove_reagent_entity_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="reagent",
            old_name="lot_number",
            new_name="lot_id",
        ),
        migrations.AddField(
            model_name="reagent",
            name="active",
            field=models.BooleanField(
                default=True,
                help_text="Whether the reagent is the active stock for most experiments",
            ),
        ),
        migrations.AlterField(
            model_name="reagent",
            name="expression",
            field=models.ForeignKey(
                default=1,
                help_text="The type of reagent (based on an ontology)",
                on_delete=django.db.models.deletion.CASCADE,
                to="core.expression",
            ),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="reagent",
            constraint=models.UniqueConstraint(
                fields=("lot_id", "expression"),
                name="Only one reagent per expression and lot_id",
            ),
        ),
    ]
