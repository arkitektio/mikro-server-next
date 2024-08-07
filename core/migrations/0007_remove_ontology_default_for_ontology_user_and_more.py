# Generated by Django 4.2.8 on 2024-07-29 13:08

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0006_remove_entity_unique_entity_kind_name_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="ontology",
            name="default_for",
        ),
        migrations.AddField(
            model_name="ontology",
            name="user",
            field=models.OneToOneField(
                blank=True,
                help_text="The user that this ontol",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="ontologies",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="entitykind",
            name="ontology",
            field=models.ForeignKey(
                default=1,
                help_text="The ontology this entity class belongs to",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="entity_kinds",
                to="core.ontology",
            ),
            preserve_default=False,
        ),
    ]
