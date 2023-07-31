# Generated by Django 4.2.3 on 2023-07-31 17:39

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_file"),
    ]

    operations = [
        migrations.CreateModel(
            name="MediaStore",
            fields=[
                (
                    "s3store_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="core.s3store",
                    ),
                ),
            ],
            bases=("core.s3store",),
        ),
    ]
