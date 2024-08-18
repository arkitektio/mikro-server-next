# Generated by Django 4.2.8 on 2024-08-18 19:44

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_remove_entity_parent_remove_historicalentity_parent"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="entityrelation",
            constraint=models.UniqueConstraint(
                fields=("left", "kind", "right"), name="only_one_relation_per_kind"
            ),
        ),
    ]