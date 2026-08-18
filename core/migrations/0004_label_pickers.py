"""A label layer publishes pickers of colourings and filters, as a mesh layer does.

`label_render.color_by` held one colouring, so a layer offered a viewer no choice. It becomes
`color_bys` -- an ordered list an author publishes -- plus `active_color_by`, the index of the
one currently drawn, and gains the filter picker's `filter_bys` / `active_filter_bys` beside
them. The old single colouring is exactly the one-entry picker with index 0, and no colouring
at all is the empty picker with a null index, which is what null already meant.

Data-only, because `label_render` is a JSON column and the shape inside it is not a schema the
database knows: nothing is added or dropped, one key is folded into three. The old key is
*popped* rather than left in place -- `LabelRenderModel(**blob)` would ignore it, so a row that
kept it would look valid and render nothing.

`HistoricalLayer` is carried too. It mirrors `label_render`, and dropping what those rows
recorded is the one thing a history table exists to prevent.
"""

from django.db import migrations


def _fold_into_pickers(apps, schema_editor):
    """One colouring becomes a one-entry picker, drawn; none becomes an empty one, not drawn."""
    for model_name in ("Layer", "HistoricalLayer"):
        model = apps.get_model("core", model_name)
        for layer in model.objects.exclude(label_render__isnull=True).iterator():
            # Every layer that is not a label layer carries SQL NULL here, and folding one of
            # those would replace "this layer has no label recipe" with an empty one claiming
            # it has. `__isnull` says that outright rather than leaning on how a JSONField
            # reads `=None`, and the emptiness guard below covers the JSON-`null` row too.
            render = dict(layer.label_render or {})
            if not render:
                continue
            entry = render.pop("color_by", None)
            if entry is None:
                # Still normalized: a render written before the pickers existed carries neither
                # key, and the models default both, but writing them makes the stored blob say
                # what it means rather than leaning on a default two layers away.
                render.setdefault("color_bys", [])
                render.setdefault("active_color_by", None)
            else:
                entry = dict(entry)
                entry.setdefault("label", None)
                entry.setdefault("join_path", [])
                render["color_bys"] = [entry]
                render["active_color_by"] = 0
            render.setdefault("filter_bys", [])
            render.setdefault("active_filter_bys", [])
            layer.label_render = render
            layer.save(update_fields=["label_render"])


def _unfold_to_one(apps, schema_editor):
    """Take the first colouring back. Later entries and every filter have nowhere to go."""
    for model_name in ("Layer", "HistoricalLayer"):
        model = apps.get_model("core", model_name)
        for layer in model.objects.exclude(label_render__isnull=True).iterator():
            render = dict(layer.label_render or {})
            if not render:
                continue
            entries = render.pop("color_bys", None) or []
            render.pop("active_color_by", None)
            render.pop("filter_bys", None)
            render.pop("active_filter_bys", None)
            if entries:
                entry = dict(entries[0])
                entry.pop("label", None)
                render["color_by"] = entry
            layer.label_render = render
            layer.save(update_fields=["label_render"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_mesh_filter_picker"),
    ]

    operations = [
        migrations.RunPython(_fold_into_pickers, _unfold_to_one),
    ]
