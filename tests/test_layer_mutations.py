"""Tests for the composable in-layer render graph and the layer helper mutations.

A layer is the alpha-blended unit; inside it a render graph combines one or more
channels (each with its own transfer function). These tests cover: creating a
layer with an explicit multi-channel render graph, the relaxed single-channel
rule, the round-trip of the typed render-graph output, and the three convenience
builders (createRgbLayer / createIntensityLayer / createLabelLayer).
"""

import pytest

from asgiref.sync import sync_to_async
from core import enums, models
from kante.context import HttpContext
from mikro_server.schema import schema
from tests import seed


async def _seed_lens(ctx: HttpContext, *, axis_names, shape, descriptors) -> models.Lens:
    dataset = await seed.create_array_dataset(ctx, "LensDS", axes=descriptors, shapes=[shape])
    return await seed.create_lens(ctx, dataset)


async def _seed_scene(ctx: HttpContext, lens: models.Lens | None = None) -> models.Scene:
    """A scene -- and, when a lens is given, the explicit registration its dataset needs.

    Layer mutations no longer fabricate placements: an unplaced source is refused. Passing
    the lens here is the test-side equivalent of the createTransformation step a real
    client takes before composing a layer.
    """
    scene = await seed.create_scene(ctx)
    if lens is not None:
        # `lens.dataset` is cached from creation, so this reads no DB in async context.
        await seed.register_into_scene(ctx, scene, lens.dataset)
    return scene


# The axes are ordered channel-before-space, which is conventional rather than required:
# nothing holds a declaration to a type ordering. Within the spatial block, the last axis is x,
# and that part is read.
_CYX = (
    ["c", "y", "x"],
    [3, 32, 32],
    [
        seed.axis("c", enums.AxisType.CHANNEL),
        seed.axis("y", enums.AxisType.SPACE),
        seed.axis("x", enums.AxisType.SPACE),
    ],
)
_YX = (
    ["y", "x"],
    [32, 32],
    [
        seed.axis("y", enums.AxisType.SPACE),
        seed.axis("x", enums.AxisType.SPACE),
    ],
)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_layer_with_render_graph(db, authenticated_context: HttpContext):
    """A layer may combine multiple channels via a render graph, relaxing the single-channel rule."""
    axis_names, shape, descriptors = _CYX
    lens = await _seed_lens(authenticated_context, axis_names=axis_names, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context, lens)

    mutation = """
        mutation Create($input: CreateLayerInput!) {
            createLayer(input: $input) {
                id
                opacity
                visible
                order
                blending
                renderGraph {
                    root {
                        kind
                        blending
                        children {
                            __typename
                            kind
                            ... on ChannelSourceNode {
                                intensityAxis
                                intensityIndex
                                transfer { colormap climMin climMax }
                            }
                        }
                    }
                }
            }
        }
    """
    variables = {
        "input": {
            "scene": str(scene.id),
            "lens": str(lens.id),
            "opacity": 0.5,
            "order": 2,
            "blending": "NORMAL",
            "renderGraph": {
                "root": {
                    "kind": "blend",
                    "blending": "ADDITIVE",
                    "children": [
                        {"kind": "channel", "intensityAxis": "c", "intensityIndex": 0, "transfer": {"colormap": "RED", "climMin": 0.0, "climMax": 0.8}},
                        {"kind": "channel", "intensityAxis": "c", "intensityIndex": 1, "transfer": {"colormap": "GREEN"}},
                    ],
                }
            },
        }
    }

    result = await schema.execute(mutation, context_value=authenticated_context, variable_values=variables)
    assert not result.errors, result.errors

    data = result.data["createLayer"]
    assert data["opacity"] == 0.5
    assert data["order"] == 2
    assert data["blending"] == "NORMAL"
    children = data["renderGraph"]["root"]["children"]
    assert [c["__typename"] for c in children] == ["ChannelSourceNode", "ChannelSourceNode"]
    assert children[0]["intensityIndex"] == 0
    assert children[0]["transfer"]["colormap"] == "RED"
    assert children[1]["intensityAxis"] == "c"

    layer = await models.Layer.objects.aget(id=data["id"])
    assert layer.render_graph["root"]["kind"] == "blend"
    assert len(layer.render_graph["root"]["children"]) == 2


_STOPS_CREATE = """
    mutation Create($input: CreateLayerInput!) { createLayer(input: $input) { id } }
"""

_STOPS_QUERY = """
    query Layer($id: ID!) {
        layer(id: $id) {
            ... on ImageLayer {
                renderGraph { root { children { ... on ChannelSourceNode {
                    transfer { gamma climMin climMax stops { position value } }
                } } } }
            }
        }
    }
"""


async def _create_layer_with_transfer(ctx: HttpContext, transfer: dict) -> str:
    """Create a single-channel layer carrying one transfer function, and return its id."""
    axis_names, shape, descriptors = _CYX
    lens = await _seed_lens(ctx, axis_names=axis_names, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(ctx, lens)
    result = await schema.execute(
        _STOPS_CREATE,
        context_value=ctx,
        variable_values={
            "input": {
                "scene": str(scene.id),
                "lens": str(lens.id),
                "renderGraph": {"root": {"kind": "blend", "children": [{"kind": "channel", "intensityAxis": "c", "intensityIndex": 0, "transfer": transfer}]}},
            }
        },
    )
    assert not result.errors, result.errors
    return result.data["createLayer"]["id"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_transfer_stops_round_trip(db, authenticated_context: HttpContext):
    """A hand-authored transfer curve survives the trip through the JSON column intact.

    The mutation response is not enough to prove that: the graph is lowered into the storage
    model, dumped to JSON, stored, and rehydrated on read, and a stop could be dropped at any
    of those four steps while the response still looked right. So the assertions here are on a
    *re-query* and on the stored column, not on what `createLayer` echoed back.

    Positions are raw intensities -- 4000 is an ordinary 12-bit reading -- which is why the
    curve here spans a range no normalized fraction could.
    """
    stops = [{"position": 100.0, "value": 0.0}, {"position": 900.0, "value": 0.8}, {"position": 4000.0, "value": 1.0}]
    layer_id = await _create_layer_with_transfer(authenticated_context, {"colormap": "VIRIDIS", "stops": stops})

    result = await schema.execute(_STOPS_QUERY, context_value=authenticated_context, variable_values={"id": str(layer_id)})
    assert not result.errors, result.errors

    transfer = result.data["layer"]["renderGraph"]["root"]["children"][0]["transfer"]
    assert transfer["stops"] == stops, "the curve comes back in the order it was authored"

    layer = await models.Layer.objects.aget(id=layer_id)
    assert layer.render_graph["root"]["children"][0]["transfer"]["stops"] == stops


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_transfer_without_stops_still_reads(db, authenticated_context: HttpContext):
    """No curve is null, never an empty one -- the shape every render graph written before `stops` existed has.

    `stops` is a new key inside a JSON column that gets no migration and no backfill, so every
    stored graph predates it. A required field, or one defaulting to `[]`, would turn reading
    any of those rows into a validation error at `LayerRenderGraphModel(**self.render_graph)`.
    """
    layer_id = await _create_layer_with_transfer(authenticated_context, {"colormap": "GREY", "gamma": 2.2})

    result = await schema.execute(_STOPS_QUERY, context_value=authenticated_context, variable_values={"id": str(layer_id)})
    assert not result.errors, result.errors

    transfer = result.data["layer"]["renderGraph"]["root"]["children"][0]["transfer"]
    assert transfer["stops"] is None
    assert transfer["gamma"] == 2.2, "with no curve, gamma is still the transfer"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_layer_without_graph_is_rejected(db, authenticated_context: HttpContext):
    """createLayer requires a render graph: the graph is the single source of truth for rendering."""
    axis_names, shape, descriptors = _CYX
    lens = await _seed_lens(authenticated_context, axis_names=axis_names, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context, lens)

    mutation = "mutation Create($input: CreateLayerInput!) { createLayer(input: $input) { id } }"
    result = await schema.execute(
        mutation,
        context_value=authenticated_context,
        variable_values={"input": {"scene": str(scene.id), "lens": str(lens.id)}},
    )
    assert result.errors, "expected createLayer without a required renderGraph to be rejected"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_render_graph_rejects_out_of_range_index(db, authenticated_context: HttpContext):
    """A channel source referencing an out-of-range index is rejected."""
    axis_names, shape, descriptors = _CYX
    lens = await _seed_lens(authenticated_context, axis_names=axis_names, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context, lens)

    mutation = "mutation Create($input: CreateLayerInput!) { createLayer(input: $input) { id } }"
    variables = {
        "input": {
            "scene": str(scene.id),
            "lens": str(lens.id),
            "renderGraph": {"root": {"kind": "blend", "children": [{"kind": "channel", "intensityAxis": "c", "intensityIndex": 9}]}},
        }
    }
    result = await schema.execute(mutation, context_value=authenticated_context, variable_values=variables)
    assert result.errors, "expected out-of-range intensity_index to be rejected"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_rgb_layer(db, authenticated_context: HttpContext):
    axis_names, shape, descriptors = _CYX
    lens = await _seed_lens(authenticated_context, axis_names=axis_names, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context, lens)

    mutation = """
        mutation Create($input: CreateRgbLayerInput!) {
            createRgbLayer(input: $input) {
                id
                blending
                renderGraph { root { blending children { ... on ChannelSourceNode { intensityIndex transfer { colormap } } } } }
            }
        }
    """
    result = await schema.execute(
        mutation,
        context_value=authenticated_context,
        variable_values={"input": {"scene": str(scene.id), "lens": str(lens.id)}},
    )
    assert not result.errors, result.errors
    data = result.data["createRgbLayer"]
    assert data["blending"] == "NORMAL"
    children = data["renderGraph"]["root"]["children"]
    assert [c["transfer"]["colormap"] for c in children] == ["RED", "GREEN", "BLUE"]
    assert [c["intensityIndex"] for c in children] == [0, 1, 2]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_intensity_layer(db, authenticated_context: HttpContext):
    axis_names, shape, descriptors = _CYX
    lens = await _seed_lens(authenticated_context, axis_names=axis_names, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context, lens)

    mutation = """
        mutation Create($input: CreateIntensityLayerInput!) {
            createIntensityLayer(input: $input) {
                id
                renderGraph { root { children { ... on ChannelSourceNode { intensityIndex transfer { colormap gamma } } } } }
            }
        }
    """
    result = await schema.execute(
        mutation,
        context_value=authenticated_context,
        variable_values={"input": {"scene": str(scene.id), "lens": str(lens.id), "intensityIndex": 1, "colormap": "MAGMA"}},
    )
    assert not result.errors, result.errors
    child = result.data["createIntensityLayer"]["renderGraph"]["root"]["children"][0]
    assert child["intensityIndex"] == 1
    assert child["transfer"]["colormap"] == "MAGMA"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_label_layer_without_channel_axis(db, authenticated_context: HttpContext):
    """A label / instance map often has no channel axis: the pixel value itself is the id.

    And the layer that comes back is a LABEL layer, not an image one carrying a flag. It
    holds no render graph at all -- there is no compositing tree over a single field of
    ids, and none of the graph's vocabulary means anything over them.
    """
    axis_names, shape, descriptors = _YX
    lens = await _seed_lens(authenticated_context, axis_names=axis_names, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context, lens)

    mutation = """
        mutation Create($input: CreateLabelLayerInput!) {
            createLabelLayer(input: $input) {
                id
                kind
                blending
                labelRender { intensityAxis intensityIndex background showUnselected selected colorBy { table } }
            }
        }
    """
    result = await schema.execute(
        mutation,
        context_value=authenticated_context,
        variable_values={"input": {"scene": str(scene.id), "lens": str(lens.id)}},
    )
    assert not result.errors, result.errors
    data = result.data["createLabelLayer"]
    assert data["kind"] == "LABEL"
    # Adding two objects' colors together would make a third belonging to neither.
    assert data["blending"] == "NORMAL"
    render = data["labelRender"]
    assert render["intensityAxis"] is None
    assert render["background"] == 0, "0 is the conventional 'not an object' value, drawn transparent"
    assert render["selected"] == [] and render["showUnselected"] is True
    assert render["colorBy"] is None, "nothing was keyed off this mask, so there is nothing to color by"

    layer = await models.Layer.objects.aget(id=data["id"])
    assert layer.render_graph is None, "a label layer carries its recipe in label_render, never a render graph"
    assert await sync_to_async(lambda: layer.label_render["intensity_index"])() == 0


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_render_graph_with_projection_node(db, authenticated_context: HttpContext):
    """A render graph may include a projection node (volume rendering mode) over a channel subtree."""
    axis_names, shape, descriptors = _CYX
    lens = await _seed_lens(authenticated_context, axis_names=axis_names, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context, lens)

    mutation = """
        mutation Create($input: CreateLayerInput!) {
            createLayer(input: $input) {
                id
                renderGraph { root { children {
                    __typename
                    ... on ProjectionNode { mode children { __typename ... on ChannelSourceNode { intensityIndex } } }
                } } }
            }
        }
    """
    variables = {
        "input": {
            "scene": str(scene.id),
            "lens": str(lens.id),
            "renderGraph": {
                "root": {
                    "kind": "blend",
                    "blending": "ADDITIVE",
                    "children": [
                        {
                            "kind": "projection",
                            "mode": "ATTENUATED_MIP",
                            "children": [{"kind": "channel", "intensityAxis": "c", "intensityIndex": 0}],
                        }
                    ],
                }
            },
        }
    }
    result = await schema.execute(mutation, context_value=authenticated_context, variable_values=variables)
    assert not result.errors, result.errors
    child = result.data["createLayer"]["renderGraph"]["root"]["children"][0]
    assert child["__typename"] == "ProjectionNode"
    assert child["mode"] == "ATTENUATED_MIP"
    assert child["children"][0]["intensityIndex"] == 0


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_volume_layer(db, authenticated_context: HttpContext):
    axis_names, shape, descriptors = _CYX
    lens = await _seed_lens(authenticated_context, axis_names=axis_names, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context, lens)

    mutation = """
        mutation Create($input: CreateVolumeLayerInput!) {
            createVolumeLayer(input: $input) {
                id
                renderGraph { root { children { __typename ... on ProjectionNode { mode } } } }
            }
        }
    """
    result = await schema.execute(
        mutation,
        context_value=authenticated_context,
        variable_values={"input": {"scene": str(scene.id), "lens": str(lens.id), "mode": "VOLUME"}},
    )
    assert not result.errors, result.errors
    child = result.data["createVolumeLayer"]["renderGraph"]["root"]["children"][0]
    assert child["__typename"] == "ProjectionNode"
    assert child["mode"] == "VOLUME"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_scene_layers_resolves_imagelayer_polymorphically(db, authenticated_context: HttpContext):
    """Scene.layers returns the polymorphic Layer interface, resolving to concrete ImageLayer."""
    axis_names, shape, descriptors = _CYX
    lens = await _seed_lens(authenticated_context, axis_names=axis_names, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context, lens)

    create = "mutation Create($input: CreateRgbLayerInput!) { createRgbLayer(input: $input) { id } }"
    result = await schema.execute(
        create,
        context_value=authenticated_context,
        variable_values={"input": {"scene": str(scene.id), "lens": str(lens.id)}},
    )
    assert not result.errors, result.errors
    layer_id = result.data["createRgbLayer"]["id"]

    query = """
        query Scene($id: ID!) {
            scene(id: $id) {
                layers {
                    __typename
                    id
                    opacity
                    ... on ImageLayer {
                        lens { renderAxes { x y z intensity } }
                        renderGraph { root { blending } }
                    }
                }
            }
        }
    """
    result = await schema.execute(query, context_value=authenticated_context, variable_values={"id": str(scene.id)})
    assert not result.errors, result.errors
    layers = result.data["scene"]["layers"]
    assert len(layers) == 1
    assert layers[0]["__typename"] == "ImageLayer"
    assert layers[0]["id"] == str(layer_id)
    assert layers[0]["renderGraph"]["root"]["blending"] == "ADDITIVE"

    # The render axes are derived from the axis types, not stored on the layer --
    # so two layers over one lens cannot disagree about which axis is x. Note that
    # x is the LAST spatial axis: the old stored rule took the first, and for these
    # (c, y, x) axes it wrote xDim="y".
    assert layers[0]["lens"]["renderAxes"] == {"x": "x", "y": "y", "z": None, "intensity": "c"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_layer_scoping_seam_is_the_scene(db, authenticated_context: HttpContext, other_org_context: HttpContext):
    """The org-scoping seam (get_for_org) resolves through the scene, not the lens.

    Layer has only nullable source FKs (lens/annotation collection/table/mesh); org isolation for
    single-object access must go through the (required) scene FK. Assert both the
    resolved path and that another org cannot fetch the layer via get_for_org.
    """
    from asgiref.sync import sync_to_async
    from core.scoping import organization_path, get_for_org

    # The required scene FK is authoritative (the source FKs are nullable and skipped).
    assert organization_path(models.Layer) == "scene__organization"

    axis_names, shape, descriptors = _CYX
    lens = await _seed_lens(authenticated_context, axis_names=axis_names, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context, lens)
    create = "mutation Create($input: CreateRgbLayerInput!) { createRgbLayer(input: $input) { id } }"
    result = await schema.execute(
        create,
        context_value=authenticated_context,
        variable_values={"input": {"scene": str(scene.id), "lens": str(lens.id)}},
    )
    assert not result.errors, result.errors
    layer_id = result.data["createRgbLayer"]["id"]

    class _Info:
        def __init__(self, ctx):
            self.context = ctx

    mine = await sync_to_async(get_for_org)(models.Layer, _Info(authenticated_context), id=layer_id)
    assert str(mine.id) == str(layer_id)

    with pytest.raises(models.Layer.DoesNotExist):
        await sync_to_async(get_for_org)(models.Layer, _Info(other_org_context), id=layer_id)


# ---------------------------------------------------------------------------
# Phasor nodes
#
# A phasor node *consumes* an axis rather than indexing into it: it reduces the
# whole profile along a MICROTIME (FLIM arrival time) or SPECTRUM (wavelength)
# axis to a single (g, s) and colors the pixel by it. Its output is a raster that
# composites into the scene like any other leaf -- there is no plot.
# ---------------------------------------------------------------------------

# A FLIM cube: an arrival-time axis, and one detection channel. Ordered by type
# (channel and microtime rank together, before space).
_C_TAU_YX = (
    ["c", "tau", "y", "x"],
    [2, 16, 32, 32],
    [
        seed.axis("c", enums.AxisType.CHANNEL),
        seed.axis("tau", enums.AxisType.MICROTIME),
        seed.axis("y", enums.AxisType.SPACE),
        seed.axis("x", enums.AxisType.SPACE),
    ],
)

# A hyperspectral cube: a wavelength axis, no detection channel.
_LAMBDA_YX = (
    ["lambda", "y", "x"],
    [24, 32, 32],
    [
        seed.axis("lambda", enums.AxisType.SPECTRUM),
        seed.axis("y", enums.AxisType.SPACE),
        seed.axis("x", enums.AxisType.SPACE),
    ],
)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_render_graph_with_phasor_node(db, authenticated_context: HttpContext):
    """A render graph may include a phasor node reducing the microtime axis."""
    axis_names, shape, descriptors = _C_TAU_YX
    lens = await _seed_lens(authenticated_context, axis_names=axis_names, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context, lens)

    mutation = """
        mutation Create($input: CreateLayerInput!) {
            createLayer(input: $input) {
                id
                renderGraph { root { children {
                    __typename
                    ... on PhasorNode {
                        phasorAxis
                        harmonic
                        intensityAxis
                        intensityIndex
                        transfer { mode colormap min max weightByIntensity cursors { kind g s radius color label } }
                    }
                } } }
            }
        }
    """
    variables = {
        "input": {
            "scene": str(scene.id),
            "lens": str(lens.id),
            "renderGraph": {
                "root": {
                    "kind": "blend",
                    "blending": "NORMAL",
                    "children": [
                        {
                            "kind": "phasor",
                            "phasorAxis": "tau",
                            "harmonic": 2,
                            "intensityAxis": "c",
                            "intensityIndex": 1,
                            "phasorTransfer": {
                                "mode": "MODULATION",
                                "colormap": "VIRIDIS",
                                "min": "0.5 ns",
                                "max": "4 ns",
                                "cursors": [{"kind": "CIRCLE", "g": 0.4, "s": 0.3, "radius": 0.05, "color": [255, 0, 0, 255], "label": "bound"}],
                            },
                        }
                    ],
                }
            },
        }
    }
    result = await schema.execute(mutation, context_value=authenticated_context, variable_values=variables)
    assert not result.errors, result.errors

    node = result.data["createLayer"]["renderGraph"]["root"]["children"][0]
    assert node["__typename"] == "PhasorNode"
    assert node["phasorAxis"] == "tau"
    assert node["harmonic"] == 2
    assert node["intensityAxis"] == "c"
    assert node["intensityIndex"] == 1
    assert node["transfer"]["mode"] == "MODULATION"
    assert node["transfer"]["colormap"] == "VIRIDIS"
    assert node["transfer"]["weightByIntensity"] is True

    # The bounds keep their unit: over a microtime axis they are durations, and it is the
    # unit -- not the field -- that says so.
    assert "nanosecond" in node["transfer"]["min"]
    assert node["transfer"]["cursors"][0]["label"] == "bound"
    assert node["transfer"]["cursors"][0]["radius"] == 0.05

    layer = await models.Layer.objects.aget(id=result.data["createLayer"]["id"])
    stored = await sync_to_async(lambda: layer.render_graph["root"]["children"][0])()
    assert stored["kind"] == "phasor"
    assert stored["phasor_axis"] == "tau"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_phasor_node_over_a_spectrum_axis(db, authenticated_context: HttpContext):
    """The generalization is real, not nominal: the same node reduces a wavelength axis."""
    axis_names, shape, descriptors = _LAMBDA_YX
    lens = await _seed_lens(authenticated_context, axis_names=axis_names, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context, lens)

    mutation = """
        mutation Create($input: CreatePhasorLayerInput!) {
            createPhasorLayer(input: $input) {
                id
                blending
                renderGraph { root { children { __typename ... on PhasorNode { phasorAxis harmonic transfer { min } } } } }
            }
        }
    """
    result = await schema.execute(
        mutation,
        context_value=authenticated_context,
        # No phasorAxis: it defaults to the lens' only phasor-capable axis.
        variable_values={"input": {"scene": str(scene.id), "lens": str(lens.id), "transfer": {"min": "480 nm", "max": "620 nm"}}},
    )
    assert not result.errors, result.errors

    data = result.data["createPhasorLayer"]
    node = data["renderGraph"]["root"]["children"][0]
    assert node["__typename"] == "PhasorNode"
    assert node["phasorAxis"] == "lambda"
    assert "nanometer" in node["transfer"]["min"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_phasor_layer_is_an_overlay(db, authenticated_context: HttpContext):
    """The layer alpha-composites over what is beneath it. A hue carrying a lifetime is not
    something you *add* to the layers underneath -- that is what an intensity is."""
    axis_names, shape, descriptors = _C_TAU_YX
    lens = await _seed_lens(authenticated_context, axis_names=axis_names, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context, lens)

    mutation = """
        mutation Create($input: CreatePhasorLayerInput!) {
            createPhasorLayer(input: $input) { id blending opacity }
        }
    """
    result = await schema.execute(
        mutation,
        context_value=authenticated_context,
        variable_values={"input": {"scene": str(scene.id), "lens": str(lens.id)}},
    )
    assert not result.errors, result.errors
    assert result.data["createPhasorLayer"]["blending"] == "NORMAL"

    layer = await models.Layer.objects.aget(id=result.data["createPhasorLayer"]["id"])
    root = await sync_to_async(lambda: layer.render_graph["root"])()
    assert root["children"][0]["kind"] == "phasor"
    assert root["children"][0]["harmonic"] == 1
    # No detection channel was named, so none is claimed -- the pixel value is the photon count.
    assert root["children"][0]["intensity_axis"] is None


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_phasor_node_inside_a_projection_node(db, authenticated_context: HttpContext):
    """A phasor-colored volume, MIP'd into the scene's z. The phasor consumes tau; z stays free."""
    axis_names = ["tau", "z", "y", "x"]
    shape = [16, 8, 32, 32]
    descriptors = [
        seed.axis("tau", enums.AxisType.MICROTIME),
        seed.axis("z", enums.AxisType.SPACE),
        seed.axis("y", enums.AxisType.SPACE),
        seed.axis("x", enums.AxisType.SPACE),
    ]
    lens = await _seed_lens(authenticated_context, axis_names=axis_names, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context, lens)

    mutation = """
        mutation Create($input: CreateLayerInput!) {
            createLayer(input: $input) {
                renderGraph { root { children {
                    __typename
                    ... on ProjectionNode { mode children { __typename ... on PhasorNode { phasorAxis } } }
                } } }
            }
        }
    """
    variables = {
        "input": {
            "scene": str(scene.id),
            "lens": str(lens.id),
            "renderGraph": {
                "root": {
                    "kind": "blend",
                    "blending": "NORMAL",
                    "children": [{"kind": "projection", "mode": "MIP", "children": [{"kind": "phasor", "phasorAxis": "tau"}]}],
                }
            },
        }
    }
    result = await schema.execute(mutation, context_value=authenticated_context, variable_values=variables)
    assert not result.errors, result.errors

    projection = result.data["createLayer"]["renderGraph"]["root"]["children"][0]
    assert projection["__typename"] == "ProjectionNode"
    assert projection["children"][0]["__typename"] == "PhasorNode"
    assert projection["children"][0]["phasorAxis"] == "tau"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.parametrize("bad_axis", ["c", "x"])
async def test_phasor_axis_must_be_a_phasor_axis(db, authenticated_context: HttpContext, bad_axis: str):
    """A DFT over a channel or a spatial axis produces a (g, s) that means nothing, and nothing
    downstream could tell it from a real phasor. So it is rejected here."""
    axis_names, shape, descriptors = _C_TAU_YX
    lens = await _seed_lens(authenticated_context, axis_names=axis_names, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context, lens)

    mutation = "mutation Create($input: CreateLayerInput!) { createLayer(input: $input) { id } }"
    variables = {
        "input": {
            "scene": str(scene.id),
            "lens": str(lens.id),
            "renderGraph": {"root": {"kind": "blend", "children": [{"kind": "phasor", "phasorAxis": bad_axis}]}},
        }
    }
    result = await schema.execute(mutation, context_value=authenticated_context, variable_values=variables)
    assert result.errors, f"expected a phasor over the {bad_axis!r} axis to be rejected"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_channel_node_still_rejects_the_microtime_axis(db, authenticated_context: HttpContext):
    """The pre-existing guarantee must not regress: a channel source composites each position of
    its axis as a separate channel, so sampling tau that way stacks all 16 arrival-time bins."""
    axis_names, shape, descriptors = _C_TAU_YX
    lens = await _seed_lens(authenticated_context, axis_names=axis_names, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context, lens)

    mutation = "mutation Create($input: CreateLayerInput!) { createLayer(input: $input) { id } }"
    variables = {
        "input": {
            "scene": str(scene.id),
            "lens": str(lens.id),
            "renderGraph": {"root": {"kind": "blend", "children": [{"kind": "channel", "intensityAxis": "tau", "intensityIndex": 0}]}},
        }
    }
    result = await schema.execute(mutation, context_value=authenticated_context, variable_values=variables)
    assert result.errors, "expected a channel source over the microtime axis to still be rejected"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cursor",
    [
        {"kind": "CIRCLE", "g": 0.4, "s": 0.3},  # no radius: selects nothing
        {"kind": "CIRCLE", "g": 0.4, "s": 0.3, "radius": 0},  # a point: selects nothing
        {"kind": "POLYGON", "points": [[0.1, 0.1], [0.2, 0.2]]},  # a line: selects nothing
    ],
)
async def test_degenerate_phasor_cursor_is_rejected(db, authenticated_context: HttpContext, cursor: dict):
    """A cursor that selects no region is not a degenerate color rule, it is one that silently
    never fires -- while still appearing in the response the client reads back."""
    axis_names, shape, descriptors = _C_TAU_YX
    lens = await _seed_lens(authenticated_context, axis_names=axis_names, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context, lens)

    mutation = "mutation Create($input: CreatePhasorLayerInput!) { createPhasorLayer(input: $input) { id } }"
    result = await schema.execute(
        mutation,
        context_value=authenticated_context,
        variable_values={"input": {"scene": str(scene.id), "lens": str(lens.id), "transfer": {"cursors": [cursor]}}},
    )
    assert result.errors, f"expected the degenerate cursor {cursor} to be rejected"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_phasor_harmonic_must_be_positive(db, authenticated_context: HttpContext):
    """There is no zeroth harmonic: it is the DC term, which is the total photon count."""
    axis_names, shape, descriptors = _C_TAU_YX
    lens = await _seed_lens(authenticated_context, axis_names=axis_names, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context, lens)

    mutation = "mutation Create($input: CreatePhasorLayerInput!) { createPhasorLayer(input: $input) { id } }"
    result = await schema.execute(
        mutation,
        context_value=authenticated_context,
        variable_values={"input": {"scene": str(scene.id), "lens": str(lens.id), "harmonic": 0}},
    )
    assert result.errors, "expected harmonic 0 to be rejected"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_phasor_layer_needs_a_phasor_axis(db, authenticated_context: HttpContext):
    """A plain c/y/x stack has nothing to take a phasor over, and says so."""
    axis_names, shape, descriptors = _CYX
    lens = await _seed_lens(authenticated_context, axis_names=axis_names, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context, lens)

    mutation = "mutation Create($input: CreatePhasorLayerInput!) { createPhasorLayer(input: $input) { id } }"
    result = await schema.execute(
        mutation,
        context_value=authenticated_context,
        variable_values={"input": {"scene": str(scene.id), "lens": str(lens.id)}},
    )
    assert result.errors, "expected a phasor layer over a lens with no MICROTIME/SPECTRUM axis to be rejected"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_moving_a_layer_to_another_scene_meets_the_same_placement_gate(db, authenticated_context: HttpContext):
    """Rebinding a layer into a scene is the same claim creating it there makes.

    An update that only touches styling never re-litigates the placement; an update that
    changes the scene is refused until the source is registered into the new world.
    """
    axis_names, shape, descriptors = _CYX
    lens = await _seed_lens(authenticated_context, axis_names=axis_names, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context, lens)

    create = "mutation Create($input: CreateLayerInput!) { createLayer(input: $input) { id } }"
    created = await schema.execute(
        create,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "scene": str(scene.id),
                "lens": str(lens.id),
                "renderGraph": {"root": {"kind": "blend", "children": [{"kind": "channel", "intensityAxis": "c", "intensityIndex": 0}]}},
            }
        },
    )
    assert not created.errors, created.errors
    layer_id = created.data["createLayer"]["id"]

    update = "mutation Update($input: UpdateLayerInput!) { updateLayer(input: $input) { id opacity } }"

    # A styling-only update never re-checks the placement.
    styled = await schema.execute(update, context_value=authenticated_context, variable_values={"input": {"id": layer_id, "opacity": 0.5}})
    assert not styled.errors, styled.errors
    assert styled.data["updateLayer"]["opacity"] == 0.5

    # Moving into a scene whose world the source does not reach is refused...
    other = await seed.create_scene(authenticated_context, "Elsewhere")
    moved = await schema.execute(update, context_value=authenticated_context, variable_values={"input": {"id": layer_id, "scene": str(other.pk)}})
    assert moved.errors, "rebinding into a scene with no path is the unplaced-layer case again"
    assert "createTransformation" in str(moved.errors[0])

    # ...and allowed once someone registers it there.
    await seed.register_into_scene(authenticated_context, other, lens.dataset)
    moved = await schema.execute(update, context_value=authenticated_context, variable_values={"input": {"id": layer_id, "scene": str(other.pk)}})
    assert not moved.errors, moved.errors
