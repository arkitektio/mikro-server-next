"""Tests for the composable in-layer render graph and the layer helper mutations.

A layer is the alpha-blended unit; inside it a render graph combines one or more
channels (each with its own transfer function). These tests cover: creating a
layer with an explicit multi-channel render graph, the relaxed single-channel
rule, the round-trip of the typed render-graph output, and the three convenience
builders (createRgbLayer / createIntensityLayer / createLabelLayer).
"""

import pytest

from asgiref.sync import sync_to_async
from core import models
from kante.context import HttpContext
from mikro_server.schema import schema


async def _seed_lens(ctx: HttpContext, *, dims, shape, descriptors) -> models.Lens:
    dataset = await models.ADataset.objects.acreate(
        name="LensDS",
        shape=shape,
        dims=dims,
        dim_descriptors=descriptors,
        organization=ctx.request.organization,  # type: ignore[arg-type]
    )
    return await models.Lens.objects.acreate(
        dataset=dataset,
        slices=[],
        shape=shape,
        dims=dims,
        dim_descriptors=descriptors,
    )


async def _seed_scene(ctx: HttpContext) -> models.Scene:
    return await models.Scene.objects.acreate(
        name="Scene",
        organization=ctx.request.organization,  # type: ignore[arg-type]
        spatial_unit="micrometers",
        temporal_unit="seconds",
    )


_CYX = (
    ["c", "y", "x"],
    [3, 32, 32],
    [{"key": "c", "kind": "channel"}, {"key": "y", "kind": "space"}, {"key": "x", "kind": "space"}],
)
_YX = (
    ["y", "x"],
    [32, 32],
    [{"key": "y", "kind": "space"}, {"key": "x", "kind": "space"}],
)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_layer_with_render_graph(db, authenticated_context: HttpContext):
    """A layer may combine multiple channels via a render graph, relaxing the single-channel rule."""
    dims, shape, descriptors = _CYX
    lens = await _seed_lens(authenticated_context, dims=dims, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context)

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
                                intensityDim
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
                        {"kind": "channel", "intensityDim": "c", "intensityIndex": 0, "transfer": {"colormap": "RED", "climMin": 0.0, "climMax": 0.8}},
                        {"kind": "channel", "intensityDim": "c", "intensityIndex": 1, "transfer": {"colormap": "GREEN"}},
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
    assert children[1]["intensityDim"] == "c"

    layer = await models.Layer.objects.aget(id=data["id"])
    assert layer.render_graph["root"]["kind"] == "blend"
    assert len(layer.render_graph["root"]["children"]) == 2


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_layer_without_graph_is_rejected(db, authenticated_context: HttpContext):
    """createLayer requires a render graph: the graph is the single source of truth for rendering."""
    dims, shape, descriptors = _CYX
    lens = await _seed_lens(authenticated_context, dims=dims, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context)

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
    dims, shape, descriptors = _CYX
    lens = await _seed_lens(authenticated_context, dims=dims, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context)

    mutation = "mutation Create($input: CreateLayerInput!) { createLayer(input: $input) { id } }"
    variables = {
        "input": {
            "scene": str(scene.id),
            "lens": str(lens.id),
            "renderGraph": {"root": {"kind": "blend", "children": [{"kind": "channel", "intensityDim": "c", "intensityIndex": 9}]}},
        }
    }
    result = await schema.execute(mutation, context_value=authenticated_context, variable_values=variables)
    assert result.errors, "expected out-of-range intensity_index to be rejected"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_rgb_layer(db, authenticated_context: HttpContext):
    dims, shape, descriptors = _CYX
    lens = await _seed_lens(authenticated_context, dims=dims, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context)

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
    dims, shape, descriptors = _CYX
    lens = await _seed_lens(authenticated_context, dims=dims, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context)

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
async def test_create_label_layer_without_channel_dim(db, authenticated_context: HttpContext):
    """A label / instance map often has no channel axis; the channel source's intensity_dim is null."""
    dims, shape, descriptors = _YX
    lens = await _seed_lens(authenticated_context, dims=dims, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context)

    mutation = """
        mutation Create($input: CreateLabelLayerInput!) {
            createLabelLayer(input: $input) {
                id
                blending
                renderGraph { root { children { ... on ChannelSourceNode { intensityDim transfer { categorical } } } } }
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
    assert data["blending"] == "NORMAL"
    child = data["renderGraph"]["root"]["children"][0]
    assert child["intensityDim"] is None
    assert child["transfer"]["categorical"] is True

    layer = await models.Layer.objects.aget(id=data["id"])
    assert await sync_to_async(lambda: layer.render_graph["root"]["children"][0]["transfer"]["categorical"])() is True


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_render_graph_with_projection_node(db, authenticated_context: HttpContext):
    """A render graph may include a projection node (volume rendering mode) over a channel subtree."""
    dims, shape, descriptors = _CYX
    lens = await _seed_lens(authenticated_context, dims=dims, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context)

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
                            "children": [{"kind": "channel", "intensityDim": "c", "intensityIndex": 0}],
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
    dims, shape, descriptors = _CYX
    lens = await _seed_lens(authenticated_context, dims=dims, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context)

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
    dims, shape, descriptors = _CYX
    lens = await _seed_lens(authenticated_context, dims=dims, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context)

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
                    ... on ImageLayer { xDim renderGraph { root { blending } } }
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


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_layer_scoping_seam_is_the_scene(db, authenticated_context: HttpContext, other_org_context: HttpContext):
    """The org-scoping seam (get_for_org) resolves through the scene, not the lens.

    Layer has two nullable source FKs (lens/data_roi/table/mesh); org isolation for
    single-object access must go through the (required) scene FK. Assert both the
    resolved path and that another org cannot fetch the layer via get_for_org.
    """
    from asgiref.sync import sync_to_async
    from core.scoping import organization_path, get_for_org

    # The required scene FK is authoritative (the source FKs are nullable and skipped).
    assert organization_path(models.Layer) == "scene__organization"

    dims, shape, descriptors = _CYX
    lens = await _seed_lens(authenticated_context, dims=dims, shape=shape, descriptors=descriptors)
    scene = await _seed_scene(authenticated_context)
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
