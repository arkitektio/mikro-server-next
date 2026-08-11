"""A label map is its own layer kind, not an image layer with a flag.

``LayerKind`` discriminates two things -- which source a layer renders, and which render
settings apply to it. Only the first was ever used to mint a kind, but the second alone
already separates POINT from TRACK over one table dataset, and it separates a segmentation
map from an image just as cleanly: contrast limits and gamma are contrast on a continuous
intensity, a colormap maps an ordered scalar (ids 41 and 42 are adjacent in no sense), and
MIP over ids returns a number belonging to no object. A label map was carrying all of that
vocabulary, unused and unrejected, plus one boolean -- ``transfer.categorical`` -- doing the
whole job.

So: a ``label`` kind, a ``label_render`` column holding the recipe ids actually have (the
id-to-colour hashing, a transparent background id, contour-or-fill, a selection, and a
``color_by`` dereferencing the FIELD edge that keys the mask's pixels to a table of
objects), and ``transfer.categorical`` deleted rather than deprecated -- leaving it would be
a second way to say what the kind now says, free to disagree with it.

``label_render`` is a *second* column rather than a second schema inside ``render_graph``:
that column's invariant is "the root is a blend node", and a label map has no compositing
tree to put under one. Keeping them apart is what makes "a label source additively blended
with a fluorescence channel" unrepresentable rather than merely unbuilt.

**The backfill refuses rather than guesses.** Two shapes carry ``categorical`` today. The
canonical one -- a root blend with exactly one child, that child categorical -- is what both
producers emit (``createLabelLayer`` and the bootstrap LABEL recipe), and it translates
exactly. A *mixed* graph, where a categorical child sits among intensity siblings or under a
projection, was reachable through hand-authored ``createLayer`` calls and is precisely the
nonsense this change exists to forbid: converting the layer to LABEL discards real
intensity siblings, leaving it IMAGE discards the label intent. Neither loss is one a
migration may pick silently, so it raises with the offending pks and an operator decides.

Note that the test suite cannot check any of this: ``settings_test`` disables migrations, so
a green run says nothing about whether this file applies. It was exercised by hand against a
real database carrying all three shapes.
"""

from django.db import migrations, models


def _categorical_nodes(node):
    """Every node in a render graph whose transfer function is marked categorical."""
    if not isinstance(node, dict):
        return
    if (node.get("transfer") or {}).get("categorical") is True:
        yield node
    for child in node.get("children") or []:
        yield from _categorical_nodes(child)


def _canonical_label_child(render_graph):
    """The single categorical child of a canonical label graph, or None if it is not one.

    Canonical means what both producers emit: a root blend whose only child is a categorical
    channel source. Anything else with a categorical node in it is a mixed graph.
    """
    root = (render_graph or {}).get("root") or {}
    children = root.get("children") or []
    if root.get("kind") != "blend" or len(children) != 1:
        return None
    child = children[0]
    if child.get("kind") != "channel" or (child.get("transfer") or {}).get("categorical") is not True:
        return None
    if child.get("children"):
        return None
    return child


def label_layers_become_label_kind(apps, schema_editor):
    Layer = apps.get_model("core", "Layer")

    mixed = []
    translated = []
    for layer in Layer.objects.filter(kind="image").iterator():
        if not any(_categorical_nodes((layer.render_graph or {}).get("root") or {})):
            continue
        child = _canonical_label_child(layer.render_graph)
        if child is None:
            mixed.append(layer.pk)
            continue
        layer.kind = "label"
        layer.label_render = {
            "intensity_axis": child.get("intensity_axis"),
            "intensity_index": child.get("intensity_index") or 0,
            "seed": 0,
            "background": 0,
            "opacity": (child.get("transfer") or {}).get("opacity", 1.0),
            "contour": False,
            "contour_width": 1.0,
            "selected": [],
            "selection_color": None,
            "show_unselected": True,
            "color_by": None,
        }
        layer.render_graph = None
        translated.append(layer)

    if mixed:
        raise RuntimeError(
            f"Layers {sorted(mixed)} carry a categorical channel mixed with other render nodes -- a label source blended with intensities, which no renderer honours coherently and which the new `label` kind exists to forbid. "
            "There is no translation this migration may pick for them: converting the layer to a label layer would discard its intensity siblings, and leaving it an image layer would discard the label intent. "
            "Re-author them as separate layers (createLabelLayer plus createIntensityLayer) or delete them, then run this migration again."
        )

    Layer.objects.bulk_update(translated, ["kind", "label_render", "render_graph"])


def label_layers_become_image_kind(apps, schema_editor):
    """Rebuild the canonical categorical graph. Lossless, because only that shape was ever written."""
    Layer = apps.get_model("core", "Layer")

    restored = []
    for layer in Layer.objects.filter(kind="label").iterator():
        recipe = layer.label_render or {}
        layer.kind = "image"
        layer.render_graph = {
            "root": {
                "kind": "blend",
                "blending": "normal",
                "label": "labels",
                "children": [
                    {
                        "kind": "channel",
                        "intensity_axis": recipe.get("intensity_axis"),
                        "intensity_index": recipe.get("intensity_index") or 0,
                        "label": "labels",
                        "visible": True,
                        "transfer": {
                            "clim_min": None,
                            "clim_max": None,
                            "colormap": None,
                            "color": None,
                            "gamma": 1.0,
                            "opacity": recipe.get("opacity", 1.0),
                            "invert": False,
                            "categorical": True,
                        },
                    }
                ],
            }
        }
        layer.label_render = None
        restored.append(layer)

    Layer.objects.bulk_update(restored, ["kind", "label_render", "render_graph"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0008_folder_unfiles_on_delete"),
    ]

    operations = [
        migrations.AddField(
            model_name="layer",
            name="label_render",
            field=models.JSONField(
                blank=True,
                default=None,
                null=True,
                help_text="(label) How discrete object ids become color: the hashing seed, the transparent background id, contour-or-fill, the selection, and an optional `colorBy` naming a column of the table this mask's FIELD edge keys into. The single source of truth for how the label layer is rendered.",
            ),
        ),
        migrations.AddField(
            model_name="historicallayer",
            name="label_render",
            field=models.JSONField(
                blank=True,
                default=None,
                null=True,
                help_text="(label) How discrete object ids become color: the hashing seed, the transparent background id, contour-or-fill, the selection, and an optional `colorBy` naming a column of the table this mask's FIELD edge keys into. The single source of truth for how the label layer is rendered.",
            ),
        ),
        migrations.RunPython(label_layers_become_label_kind, label_layers_become_image_kind),
    ]
