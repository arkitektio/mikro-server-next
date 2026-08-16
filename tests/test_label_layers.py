"""A label layer is its own kind, and `colorBy` is the join it exists to reach.

Two things are being pinned here. First, that `LayerKind.LABEL` is a real kind and not a
render treatment: the layer resolves as `LabelLayer` through the `Layer` interface, carries
a label recipe instead of a render graph, and none of an image's vocabulary is reachable on
it. Second, that `colorBy` is checked against the coordinate graph rather than taken on
faith -- the table must be one this mask's pixels actually dereference into (a `FIELD`
edge, the same relation `attributePlans` publishes), the column must exist on it, and the
way the column becomes colour must match the role the table declared for it.

The refusals are the interesting half. A `colorBy` naming an unrelated table is not a
display preference a client can hold until the edge shows up; it is a join nothing can
execute, and accepting it would store a layer that renders differently from what it says.
"""

import pytest
from asgiref.sync import sync_to_async
from kante.context import HttpContext

from core import enums, models
from mikro_server.schema import schema
from tests import seed

CREATE_LABEL_LAYER = """
mutation Create($input: CreateLabelLayerInput!) {
  createLabelLayer(input: $input) {
    id
    kind
    labelRender {
      intensityAxis
      seed
      background
      contour
      selected
      showUnselected
      colorBy { table column colormap classColors }
    }
  }
}
"""

UPDATE_LABEL_LAYER = """
mutation Update($input: UpdateLabelLayerInput!) {
  updateLabelLayer(input: $input) {
    id
    opacity
    labelRender { seed contour contourWidth selected showUnselected colorBy { table column } }
  }
}
"""

SCENE_LAYERS = """
query SceneLayers($id: ID!) {
  scene(id: $id) {
    layers {
      __typename
      id
      ... on LabelLayer { labelRender { background } levelPaths { dataArray { id } } }
    }
  }
}
"""

#: A mask and its object table share `t`; the mask's `(y, x)` are consumed to produce `i`.
TYX_AXES = [
    seed.axis("t", enums.AxisType.TIME),
    seed.axis("y", enums.AxisType.SPACE),
    seed.axis("x", enums.AxisType.SPACE),
]

OBJECT_COLUMNS = [
    {"name": "t", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "TIME"},
    {"name": "i", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"},
    {"name": "area", "dtype": "DOUBLE", "role": "ATTRIBUTE"},
    {"name": "cell_type", "dtype": "VARCHAR", "role": "LABEL"},
]


async def _parquet(ctx: HttpContext, key: str) -> models.ParquetStore:
    return await sync_to_async(models.ParquetStore.objects.create)(path=f"s3://parquet/{key}", bucket="parquet", key=key, organization=ctx.request.organization)


async def _mask_scene_lens(ctx: HttpContext, name: str = "nuclei labels") -> tuple[models.ADataset, models.Scene, models.Lens]:
    """A placed mask: the dataset, a scene its intrinsic system is registered into, and a lens."""
    dataset = await seed.create_adataset(ctx, name, axes=TYX_AXES, shapes=[[10, 64, 64]])
    lens = await seed.create_lens(ctx, dataset)
    scene = await seed.create_scene(ctx, f"{name} scene")
    await seed.register_into_scene(ctx, scene, dataset)
    return dataset, scene, lens


async def _object_table(ctx: HttpContext, mask: models.ADataset, name: str = "nuclei morphology", *, keyed: bool = True) -> str:
    """A per-object table, keyed off the mask (or deliberately not, for the refusal)."""
    variables = {
        "input": {
            "name": name,
            "data": str((await _parquet(ctx, name.replace(" ", "-"))).pk),
            "columns": OBJECT_COLUMNS,
        }
    }
    if keyed:
        variables["input"]["keyedBy"] = [{"kind": "DATASET", "dataset": str(mask.pk)}]
    result = await schema.execute(
        "mutation Create($input: CreateTableDatasetInput!) { createTableDataset(input: $input) { id } }",
        context_value=ctx,
        variable_values=variables,
    )
    assert not result.errors, result.errors
    return result.data["createTableDataset"]["id"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_color_by_dereferences_the_field_edge(authenticated_context: HttpContext):
    """The capability the kind exists for: colour instances by a column of the table they key into.

    Nothing about the mask says which object is which type -- the pixels hold ids. The
    answer is a row in the table the `FIELD` edge lands on, and `colorBy` is the layer
    saying which column of it to read. The edge was authored by `keyedBy`; the layer only
    points at it.
    """
    mask, scene, lens = await _mask_scene_lens(authenticated_context)
    table = await _object_table(authenticated_context, mask)

    result = await schema.execute(
        CREATE_LABEL_LAYER,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "scene": str(scene.id),
                "lens": str(lens.id),
                "render": {"colorBy": {"table": table, "column": "cell_type", "classColors": {"nucleus": [255, 0, 0, 255]}}},
            }
        },
    )
    assert not result.errors, result.errors
    data = result.data["createLabelLayer"]
    assert data["kind"] == "LABEL"
    color_by = data["labelRender"]["colorBy"]
    assert color_by["table"] == table
    assert color_by["column"] == "cell_type"
    assert color_by["classColors"] == {"nucleus": [255, 0, 0, 255]}
    assert color_by["colormap"] is None, "a categorical column takes an explicit map, never a colormap"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_measure_column_takes_a_colormap(authenticated_context: HttpContext):
    """The other half of the same rule: a measured column is coloured over its range."""
    mask, scene, lens = await _mask_scene_lens(authenticated_context)
    table = await _object_table(authenticated_context, mask)

    result = await schema.execute(
        CREATE_LABEL_LAYER,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "scene": str(scene.id),
                "lens": str(lens.id),
                "render": {"colorBy": {"table": table, "column": "area", "colormap": "VIRIDIS"}},
            }
        },
    )
    assert not result.errors, result.errors
    color_by = result.data["createLabelLayer"]["labelRender"]["colorBy"]
    assert color_by["column"] == "area"
    assert color_by["colormap"] == "VIRIDIS"
    assert color_by["classColors"] is None


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_color_by_refuses_a_table_no_field_edge_reaches(authenticated_context: HttpContext):
    """A table the mask does not key into is a join nothing can execute.

    The table is real and the column exists; what is missing is the one thing that makes
    the question answerable -- a `FIELD` edge from the mask's pixels to its rows. Without
    it there is no way to get from a pixel value to a row, so the layer would name a colour
    rule no renderer could follow.
    """
    mask, scene, lens = await _mask_scene_lens(authenticated_context)
    unrelated = await _object_table(authenticated_context, mask, name="unrelated objects", keyed=False)

    result = await schema.execute(
        CREATE_LABEL_LAYER,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "scene": str(scene.id),
                "lens": str(lens.id),
                "render": {"colorBy": {"table": unrelated, "column": "area", "colormap": "VIRIDIS"}},
            }
        },
    )
    assert result.errors, "expected a colorBy naming an unkeyed table to be refused"
    assert "not reachable from this mask by a FIELD edge" in str(result.errors[0])
    assert await models.Layer.objects.filter(scene_id=scene.id).acount() == 0, "the refusal left no layer behind"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_color_by_refuses_a_colormap_over_a_categorical_column(authenticated_context: HttpContext):
    """A colormap over a class column would impose an order the values do not have."""
    mask, scene, lens = await _mask_scene_lens(authenticated_context)
    table = await _object_table(authenticated_context, mask)

    result = await schema.execute(
        CREATE_LABEL_LAYER,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "scene": str(scene.id),
                "lens": str(lens.id),
                "render": {"colorBy": {"table": table, "column": "cell_type", "colormap": "VIRIDIS"}},
            }
        },
    )
    assert result.errors, "expected a colormap over a LABEL column to be refused"
    assert "categorical" in str(result.errors[0]) and "classColors" in str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_color_by_refuses_class_colors_over_a_measure_column(authenticated_context: HttpContext):
    """And the mirror: naming each value of a continuous measurement is not a colour rule."""
    mask, scene, lens = await _mask_scene_lens(authenticated_context)
    table = await _object_table(authenticated_context, mask)

    result = await schema.execute(
        CREATE_LABEL_LAYER,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "scene": str(scene.id),
                "lens": str(lens.id),
                "render": {"colorBy": {"table": table, "column": "area", "classColors": {"3.5": [255, 0, 0, 255]}}},
            }
        },
    )
    assert result.errors, "expected classColors over an ATTRIBUTE column to be refused"
    assert "measured" in str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_color_by_refuses_an_undeclared_column(authenticated_context: HttpContext):
    """The edge is right and the column is not: the table's own schema settles it."""
    mask, scene, lens = await _mask_scene_lens(authenticated_context)
    table = await _object_table(authenticated_context, mask)

    result = await schema.execute(
        CREATE_LABEL_LAYER,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "scene": str(scene.id),
                "lens": str(lens.id),
                "render": {"colorBy": {"table": table, "column": "perimeter", "colormap": "VIRIDIS"}},
            }
        },
    )
    assert result.errors, "expected a colorBy naming an undeclared column to be refused"
    assert "declares no column 'perimeter'" in str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_update_is_a_patch_not_a_replacement(authenticated_context: HttpContext):
    """Toggling `contour` must not drop the selection the client is not sending.

    A label layer's settings are edited one at a time from a viewer -- a contour toggle
    here, a click on an object there. If an omitted field reset to its default, every one
    of those edits would silently discard the rest of the state.
    """
    mask, scene, lens = await _mask_scene_lens(authenticated_context)
    table = await _object_table(authenticated_context, mask)

    created = await schema.execute(
        CREATE_LABEL_LAYER,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "scene": str(scene.id),
                "lens": str(lens.id),
                "render": {"selected": [7, 42], "showUnselected": False, "colorBy": {"table": table, "column": "area", "colormap": "VIRIDIS"}},
            }
        },
    )
    assert not created.errors, created.errors
    layer_id = created.data["createLabelLayer"]["id"]

    updated = await schema.execute(
        UPDATE_LABEL_LAYER,
        context_value=authenticated_context,
        variable_values={"input": {"id": layer_id, "render": {"contour": True, "contourWidth": 2.0}, "opacity": 0.5}},
    )
    assert not updated.errors, updated.errors
    render = updated.data["updateLabelLayer"]["labelRender"]
    assert render["contour"] is True and render["contourWidth"] == 2.0, "what was sent changed"
    assert render["selected"] == [7, 42], "what was not sent survived"
    assert render["showUnselected"] is False
    assert render["colorBy"]["column"] == "area"
    assert updated.data["updateLabelLayer"]["opacity"] == 0.5


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_update_label_layer_refuses_an_image_layer(authenticated_context: HttpContext):
    """The two kinds' render settings are different vocabularies, so their updates are too."""
    _, scene, lens = await _mask_scene_lens(authenticated_context)

    created = await schema.execute(
        "mutation Create($input: CreateIntensityLayerInput!) { createIntensityLayer(input: $input) { id } }",
        context_value=authenticated_context,
        variable_values={"input": {"scene": str(scene.id), "lens": str(lens.id)}},
    )
    assert not created.errors, created.errors

    result = await schema.execute(
        UPDATE_LABEL_LAYER,
        context_value=authenticated_context,
        variable_values={"input": {"id": created.data["createIntensityLayer"]["id"], "render": {"contour": True}}},
    )
    assert result.errors, "expected updateLabelLayer over an image layer to be refused"
    assert "not a label layer" in str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_update_layer_refuses_a_label_layer(authenticated_context: HttpContext):
    """The mirror guard, and the one that protects the split.

    Without it a single `updateLayer` writes a render graph onto a label layer and leaves
    it carrying both recipes -- the two-schemas-in-one-place state the separate
    `label_render` column exists to make unrepresentable.
    """
    _, scene, lens = await _mask_scene_lens(authenticated_context)

    created = await schema.execute(
        CREATE_LABEL_LAYER,
        context_value=authenticated_context,
        variable_values={"input": {"scene": str(scene.id), "lens": str(lens.id)}},
    )
    assert not created.errors, created.errors
    layer_id = created.data["createLabelLayer"]["id"]

    result = await schema.execute(
        "mutation U($input: UpdateLayerInput!) { updateLayer(input: $input) { id } }",
        context_value=authenticated_context,
        variable_values={
            "input": {
                "id": layer_id,
                "renderGraph": {"root": {"kind": "blend", "children": [{"kind": "channel", "transfer": {"colormap": "VIRIDIS"}}]}},
            }
        },
    )
    assert result.errors, "expected updateLayer over a label layer to be refused"
    assert "not its render vocabulary" in str(result.errors[0])

    layer = await models.Layer.objects.aget(id=layer_id)
    assert layer.render_graph is None and layer.label_render is not None, "the refusal left one recipe, not two"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_label_layer_resolves_through_the_scene_interface(authenticated_context: HttpContext):
    """`Scene.layers` returns it as a `LabelLayer`, and it places like any lens-backed layer.

    This is what the `layer_types` registration buys: a subtype reachable only through the
    `Layer` interface is dropped from the SDL unless it is listed there, and the failure is
    a resolution error at query time rather than anything a create test would notice.
    `levelPaths` is here for the second half -- a label map has a pyramid, and placement is
    a fact of its lens' space, which it shares with an image layer.
    """
    mask, scene, lens = await _mask_scene_lens(authenticated_context)

    created = await schema.execute(
        CREATE_LABEL_LAYER,
        context_value=authenticated_context,
        variable_values={"input": {"scene": str(scene.id), "lens": str(lens.id)}},
    )
    assert not created.errors, created.errors

    result = await schema.execute(SCENE_LAYERS, context_value=authenticated_context, variable_values={"id": str(scene.id)})
    assert not result.errors, result.errors
    (layer,) = result.data["scene"]["layers"]
    assert layer["__typename"] == "LabelLayer"
    assert layer["labelRender"]["background"] == 0
    assert len(layer["levelPaths"]) == 1, "one pyramid level, placed like any lens-backed layer"
