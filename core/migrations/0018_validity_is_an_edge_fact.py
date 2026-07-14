"""Validity moves onto the transformation edge; the layer's dead placement columns go.

`Layer.validity` was a per-layer copy of a per-edge fact -- two layers over one
dataset in one scene carried two copies of how-known one registration is, free to
disagree -- and nothing ever wrote it. It is now stored on the edge and *derived*
on the layer: the weakest edge on its path to world. `Layer.status` had no readers
at all.

Existing edges are classified by what wrote them: an "(assumed)" edge is UNKNOWN,
a registration into a WORLD system is MANUAL (someone authored it), a calibration
(intrinsic -> physical) is INFERRED, and everything else -- the shape-derived
pyramid, lens and derivation plumbing -- keeps the VALIDATED default.
"""

from django.db import migrations, models
import django_choices_field.fields

from core import enums


def classify_existing_edges(apps, schema_editor):
    """Set validity on pre-existing edges from what is known about their writers."""
    Transformation = apps.get_model("core", "Transformation")

    Transformation.objects.filter(parent__isnull=True, output__kind="WORLD").update(validity="MANUAL")
    Transformation.objects.filter(input__kind="INTRINSIC", output__kind="PHYSICAL").update(validity="INFERRED")
    Transformation.objects.filter(name__endswith="(assumed)").update(validity="UNKNOWN")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0017_level_zero_and_unsliced_lenses_are_intrinsic"),
    ]

    operations = [
        migrations.AddField(
            model_name="transformation",
            name="validity",
            field=django_choices_field.fields.TextChoicesField(
                choices=enums.PlacementValidityChoices.choices,
                choices_enum=enums.PlacementValidityChoices,
                default="VALIDATED",
                help_text=(
                    "How much this map is actually known. VALIDATED is the default because most edges are derived "
                    "by the server from shapes and slices -- exact by construction. A writer that merely reads "
                    "metadata says INFERRED, one that records an authored registration says MANUAL, and an edge "
                    "the server assumed says UNKNOWN"
                ),
                max_length=9,
            ),
        ),
        migrations.RunPython(classify_existing_edges, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="layer",
            name="status",
        ),
        migrations.RemoveField(
            model_name="layer",
            name="validity",
        ),
    ]
