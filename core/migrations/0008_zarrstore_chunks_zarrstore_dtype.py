# Generated by Django 4.2.3 on 2023-08-01 14:46

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0007_image_tags"),
    ]

    operations = [
        migrations.AddField(
            model_name="zarrstore",
            name="chunks",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="zarrstore",
            name="dtype",
            field=models.CharField(blank=True, max_length=1000, null=True),
        ),
    ]
