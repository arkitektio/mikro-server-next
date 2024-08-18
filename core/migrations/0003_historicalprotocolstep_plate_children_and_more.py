# Generated by Django 4.2.8 on 2024-08-16 13:16

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_alter_protocolstepmapping_t"),
    ]

    operations = [
        migrations.AddField(
            model_name="historicalprotocolstep",
            name="plate_children",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="The children of the slate",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="protocolstep",
            name="plate_children",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="The children of the slate",
                null=True,
            ),
        ),
    ]