# Generated by Django 4.2.8 on 2024-12-12 13:01

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_historicalstructureview_structureview_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="zarrstore",
            name="version",
            field=models.CharField(default="2", max_length=1000),
        ),
    ]