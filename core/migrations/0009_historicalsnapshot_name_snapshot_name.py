# Generated by Django 4.2.3 on 2023-08-01 15:04

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0008_zarrstore_chunks_zarrstore_dtype"),
    ]

    operations = [
        migrations.AddField(
            model_name="historicalsnapshot",
            name="name",
            field=models.CharField(
                default="", help_text="The name of the snapshot", max_length=1000
            ),
        ),
        migrations.AddField(
            model_name="snapshot",
            name="name",
            field=models.CharField(
                default="", help_text="The name of the snapshot", max_length=1000
            ),
        ),
    ]
