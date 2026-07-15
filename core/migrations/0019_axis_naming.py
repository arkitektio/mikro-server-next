# One word for one concept: an axis name is `axis`, never `dim`.
#
# Three renames of stored facts, in one migration so a database is never half-renamed:
#   1. PhasorHistogram.dim / PhasorCalibration.dim -> axis (real columns, with their
#      unique constraints rebuilt around the new name).
#   2. Lens.slices JSON rows carry {"dim": ...} per slice -> {"axis": ...}. SliceModel
#      now validates `axis`, so an unmigrated row would fail at slices_list.
#   3. Layer.render_graph JSON nodes carry intensity_dim / phasor_dim -> intensity_axis /
#      phasor_axis, recursively through the node tree. The pydantic render models now
#      name the new keys, so an unmigrated graph would drop its channel selection.
#
# Plus the state-only related_name/help_text changes on Layer.

import django.db.models.deletion
from django.db import migrations, models


def _rekey(mapping: dict, renames: dict[str, str]) -> dict:
    """One node's keys, renamed; children recursed."""
    out = {}
    for key, value in mapping.items():
        new_key = renames.get(key, key)
        if new_key == "children" and isinstance(value, list):
            value = [_rekey(child, renames) if isinstance(child, dict) else child for child in value]
        out[new_key] = value
    return out


def rekey_forward(apps, schema_editor):
    Lens = apps.get_model("core", "Lens")
    for lens in Lens.objects.exclude(slices=[]).iterator():
        if isinstance(lens.slices, list):
            lens.slices = [_rekey(s, {"dim": "axis"}) if isinstance(s, dict) else s for s in lens.slices]
            lens.save(update_fields=["slices"])

    Layer = apps.get_model("core", "Layer")
    renames = {"intensity_dim": "intensity_axis", "phasor_dim": "phasor_axis"}
    for layer in Layer.objects.exclude(render_graph=None).iterator():
        graph = layer.render_graph
        if isinstance(graph, dict) and isinstance(graph.get("root"), dict):
            layer.render_graph = {**graph, "root": _rekey(graph["root"], renames)}
            layer.save(update_fields=["render_graph"])


def rekey_backward(apps, schema_editor):
    Lens = apps.get_model("core", "Lens")
    for lens in Lens.objects.exclude(slices=[]).iterator():
        if isinstance(lens.slices, list):
            lens.slices = [_rekey(s, {"axis": "dim"}) if isinstance(s, dict) else s for s in lens.slices]
            lens.save(update_fields=["slices"])

    Layer = apps.get_model("core", "Layer")
    renames = {"intensity_axis": "intensity_dim", "phasor_axis": "phasor_dim"}
    for layer in Layer.objects.exclude(render_graph=None).iterator():
        graph = layer.render_graph
        if isinstance(graph, dict) and isinstance(graph.get("root"), dict):
            layer.render_graph = {**graph, "root": _rekey(graph["root"], renames)}
            layer.save(update_fields=["render_graph"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0018_validity_is_an_edge_fact"),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="phasorhistogram", name="unique_phasor_histogram"),
        migrations.RemoveConstraint(model_name="phasorcalibration", name="unique_phasor_calibration"),
        migrations.RenameField(model_name="phasorhistogram", old_name="dim", new_name="axis"),
        migrations.RenameField(model_name="phasorcalibration", old_name="dim", new_name="axis"),
        migrations.AlterField(
            model_name="phasorhistogram",
            name="axis",
            field=models.CharField(help_text="The axis the phasor was taken over, e.g. 'tau'", max_length=32),
        ),
        migrations.AlterField(
            model_name="phasorcalibration",
            name="axis",
            field=models.CharField(help_text="The axis the correction applies to, e.g. 'tau'", max_length=32),
        ),
        migrations.AddConstraint(
            model_name="phasorhistogram",
            constraint=models.UniqueConstraint(fields=("anchor", "axis", "harmonic"), name="unique_phasor_histogram"),
        ),
        migrations.AddConstraint(
            model_name="phasorcalibration",
            constraint=models.UniqueConstraint(fields=("anchor", "axis", "harmonic"), name="unique_phasor_calibration"),
        ),
        migrations.AlterField(
            model_name="layer",
            name="coordinate_system",
            field=models.ForeignKey(
                blank=True,
                help_text="(point/track) The coordinate system the table's coordinate columns are expressed in. Without it a point cloud sits in an undefined space and cannot be registered through the graph",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="layers",
                to="core.coordinatesystem",
            ),
        ),
        migrations.AlterField(
            model_name="layer",
            name="mesh_collection",
            field=models.ForeignKey(
                blank=True,
                help_text="(mesh) The versioned mesh collection, owning its own coordinate system, that this layer renders",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="mesh_layers",
                to="core.meshcollection",
            ),
        ),
        migrations.RunPython(rekey_forward, rekey_backward),
    ]
