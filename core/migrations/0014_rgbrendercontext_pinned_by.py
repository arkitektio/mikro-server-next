# Generated by Django 4.2.3 on 2023-09-07 11:38

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0013_rgbrendercontext_rgbview_historicalrgbview_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="rgbrendercontext",
            name="pinned_by",
            field=models.ManyToManyField(
                blank=True,
                help_text="The users that have pinned the era",
                related_name="pinned_rgbcontexts",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
