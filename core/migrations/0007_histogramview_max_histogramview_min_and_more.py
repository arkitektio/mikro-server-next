# Generated by Django 4.2.8 on 2025-03-20 15:26

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_histogramview_historicalhistogramview"),
    ]

    operations = [
        migrations.AddField(
            model_name="histogramview",
            name="max",
            field=models.FloatField(
                blank=True,
                help_text="The maximum pixel value of the histogram",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="histogramview",
            name="min",
            field=models.FloatField(
                blank=True,
                help_text="The minimum pixel value of the histogram",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="historicalhistogramview",
            name="max",
            field=models.FloatField(
                blank=True,
                help_text="The maximum pixel value of the histogram",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="historicalhistogramview",
            name="min",
            field=models.FloatField(
                blank=True,
                help_text="The minimum pixel value of the histogram",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="histogramview",
            name="histogram",
            field=models.JSONField(
                default=list, help_text="The histogram of the image (y values)"
            ),
        ),
        migrations.AlterField(
            model_name="histogramview",
            name="nbins",
            field=models.JSONField(
                default=list, help_text="The bin indices of the histogram (x values)"
            ),
        ),
        migrations.AlterField(
            model_name="historicalhistogramview",
            name="histogram",
            field=models.JSONField(
                default=list, help_text="The histogram of the image (y values)"
            ),
        ),
        migrations.AlterField(
            model_name="historicalhistogramview",
            name="nbins",
            field=models.JSONField(
                default=list, help_text="The bin indices of the histogram (x values)"
            ),
        ),
    ]
