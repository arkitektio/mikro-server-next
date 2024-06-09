# Generated by Django 4.2.8 on 2024-05-29 13:15

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0026_remove_historicalrgbview_context_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="historicalrgbrendercontext",
            old_name="governed_by",
            new_name="image",
        ),
        migrations.RemoveField(
            model_name="rgbrendercontext",
            name="governed_by",
        ),
        migrations.AddField(
            model_name="rgbrendercontext",
            name="image",
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="rgb_contexts",
                to="core.image",
            ),
            preserve_default=False,
        ),
    ]
