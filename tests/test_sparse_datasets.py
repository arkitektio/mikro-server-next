"""`createSparseDataset`: two identified axes, and one or both stored layouts.

A sparse dataset is the shape a colouring needs when a feature stops being a *schema* fact and
becomes a *data* one. Everything asserted here is a refusal that would otherwise be silent:

* a store whose shape contradicts the declared axes places every lookup one position out and
  raises nothing;
* two stores indexing the same axis are one capability twice, with nothing to say which a
  reader should use;
* an axis identified by nothing is not a lax dataset -- it is one no source can ever key,
  because `assert_edge_rank` can only account for an axis the edge supplies or the target
  identifies.

The load-bearing test is :func:`test_the_keyed_axis_is_produced_and_the_referenced_one_is_not`:
a mask supplies one id, and the other axis is accounted for without it.
"""

import pytest
from asgiref.sync import sync_to_async
from kante.context import HttpContext

from core import enums, models
from mikro_server.schema import schema
from tests import seed

CREATE = """
mutation Create($input: CreateSparseDatasetInput!) {
  createSparseDataset(input: $input) {
    id
    name
    axisNames
    shape
    indexableAxes
    arrays { indexedAxis indexedAxisName store { id encoding } }
    axisReferences { axis references { id name } }
    coordinateSystem { id axes { name type } }
  }
}
"""

PLANS = """
query Plans($system: ID!) {
  attributePlans(system: $system) { table { name } sample { produces passthrough } }
}
"""

#: A mask whose pixels are object ids. `(y, x)` in, one id out.
YX_AXES = [seed.axis("y", enums.AxisType.SPACE), seed.axis("x", enums.AxisType.SPACE)]

#: The declared axes of the matrix, in the order its stores' `shape` is written.
SPARSE_AXES = [{"name": "feature", "type": "INDEX"}, {"name": "object", "type": "INDEX"}]

#: 40 features x 12 objects. Small, and the two extents differ so a transposed shape is caught.
SHAPE = [40, 12]


async def _mask(ctx: HttpContext, name: str = "cell labels"):
    """A label mask whose level-0 array has a zarr store, so a plan has something to name.

    `resolve_field_store` refuses a storeless array outright -- a plan is instructions for a
    worker, and one that cannot say where to sample is not instructions.
    """
    dataset = await seed.create_array_dataset(ctx, name, axes=YX_AXES, shapes=[[64, 64]])

    def attach() -> None:
        store = models.ZarrStore.objects.create(path=f"s3://zarr/{name}", bucket="zarr", key=name.replace(" ", "-"), organization=ctx.request.organization)
        array = dataset.data_arrays.get(level=0)
        array.store = store
        array.save()

    await sync_to_async(attach)()
    return dataset


async def _store(ctx: HttpContext, key: str, encoding: str, shape: list[int] | None = None) -> models.SparseStore:
    """A finished sparse store, built directly.

    `fill_info` reads the group off S3, which `tests/test_derived_datasets.py` patches out for
    the same reason. Setting the fields here says the same thing more plainly: what is on trial
    is what the *mutation* does with a store's declared facts, not how they were discovered.
    """
    return await sync_to_async(models.SparseStore.objects.create)(
        path=f"s3://zarr/{key}",
        bucket="zarr",
        key=key,
        organization=ctx.request.organization,
        populated=True,
        encoding=encoding,
        encoding_version="0.1.0",
        shape=list(shape if shape is not None else SHAPE),
        nnz=96,
        dtype="float32",
        chunks={"data": 32768, "indices": 32768, "indptr": 41},
    )


async def _features_table(ctx: HttpContext, name: str = "features") -> str:
    """A table one feature position identifies a row of: keyed by a single INDEX column."""
    parquet = await sync_to_async(models.ParquetStore.objects.create)(path=f"s3://parquet/{name}", bucket="parquet", key=name, organization=ctx.request.organization)
    result = await schema.execute(
        "mutation Create($input: CreateTableDatasetInput!) { createTableDataset(input: $input) { id } }",
        context_value=ctx,
        variable_values={
            "input": {
                "name": name,
                "data": str(parquet.pk),
                "columns": [
                    {"name": "feature_id", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"},
                    {"name": "symbol", "dtype": "VARCHAR", "role": "LABEL"},
                ],
            }
        },
    )
    assert not result.errors, result.errors
    return result.data["createTableDataset"]["id"]


async def _create(ctx: HttpContext, name: str, **extra: object) -> object:
    return await schema.execute(CREATE, context_value=ctx, variable_values={"input": {"name": name, "axes": SPARSE_AXES, **extra}})


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_both_layouts_land_as_two_arrays_of_one_dataset(authenticated_context: HttpContext):
    """One matrix, two stores, and the axis each indexes derived from its own encoding."""
    mask = await _mask(authenticated_context)
    features = await _features_table(authenticated_context)
    by_feature = await _store(authenticated_context, "by-feature", "csr_matrix")
    by_object = await _store(authenticated_context, "by-object", "csc_matrix")

    result = await _create(
        authenticated_context,
        "expression",
        stores=[str(by_feature.pk), str(by_object.pk)],
        keyedBy=[{"kind": "DATASET", "dataset": str(mask.pk)}],
        axisReferences=[{"axis": "feature", "references": features}],
    )
    assert not result.errors, result.errors
    dataset = result.data["createSparseDataset"]

    assert dataset["axisNames"] == ["feature", "object"]
    assert dataset["shape"] == SHAPE, "read off the stores, never declared"
    assert [axis["type"] for axis in dataset["coordinateSystem"]["axes"]] == ["INDEX", "INDEX"]

    arrays = {array["indexedAxisName"]: array["store"]["encoding"] for array in dataset["arrays"]}
    assert arrays == {"feature": "csr_matrix", "object": "csc_matrix"}, "csr indexes axis 0, csc axis 1"
    assert sorted(dataset["indexableAxes"]) == ["feature", "object"], "both questions answerable in one read"

    assert [(entry["axis"], entry["references"]["name"]) for entry in dataset["axisReferences"]] == [("feature", "features")]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_one_layout_is_legal_and_offers_one_capability(authenticated_context: HttpContext):
    """A dataset with a single store is not half-built: it answers one question, and says so."""
    mask = await _mask(authenticated_context)
    features = await _features_table(authenticated_context)
    by_feature = await _store(authenticated_context, "by-feature", "csr_matrix")

    result = await _create(
        authenticated_context,
        "expression",
        stores=[str(by_feature.pk)],
        keyedBy=[{"kind": "DATASET", "dataset": str(mask.pk)}],
        axisReferences=[{"axis": "feature", "references": features}],
    )
    assert not result.errors, result.errors
    assert result.data["createSparseDataset"]["indexableAxes"] == ["feature"], "one store, one capability"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_the_keyed_axis_is_produced_and_the_referenced_one_is_not(authenticated_context: HttpContext):
    """The rule this whole shape rests on: a mask supplies one id, and that is enough.

    `assert_edge_rank` accounts for every axis of a FIELD's target -- by the edge, or by the
    target's own identification. `feature` is identified by `references`, so the edge produces
    only `object`, and the edge is written rather than refused.
    """
    mask = await _mask(authenticated_context)
    features = await _features_table(authenticated_context)
    store = await _store(authenticated_context, "by-feature", "csr_matrix")

    result = await _create(
        authenticated_context,
        "expression",
        stores=[str(store.pk)],
        keyedBy=[{"kind": "DATASET", "dataset": str(mask.pk)}],
        axisReferences=[{"axis": "feature", "references": features}],
    )
    assert not result.errors, result.errors

    def edges() -> list[models.Transformation]:
        system = models.CoordinateSystem.objects.get(pk=result.data["createSparseDataset"]["coordinateSystem"]["id"])
        return list(models.Transformation.objects.filter(output=system, kind=enums.TransformKind.FIELD.value))

    field_edges = await sync_to_async(edges)()
    assert len(field_edges) == 1, "one source, one FIELD edge"
    assert field_edges[0].output_axes == ["object"], "the mask supplies the object id and nothing about a feature"
    assert sorted(field_edges[0].input_axes) == ["x", "y"], "and it consumes the pixel grid to do it"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_axis_identified_by_nothing_is_refused(authenticated_context: HttpContext):
    """Not laxness: an unidentified axis is one no source can ever key."""
    mask = await _mask(authenticated_context)
    store = await _store(authenticated_context, "by-feature", "csr_matrix")

    result = await _create(authenticated_context, "expression", stores=[str(store.pk)], keyedBy=[{"kind": "DATASET", "dataset": str(mask.pk)}])
    assert result.errors, "an axis identified by nothing must be refused"
    message = str(result.errors[0])
    assert "identified by nothing" in message
    assert "feature" in message, "name the axis"
    assert not await sync_to_async(models.SparseDataset.objects.filter(name="expression").exists)(), "the refusal left nothing behind"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_two_stores_indexing_one_axis_are_refused(authenticated_context: HttpContext):
    """One capability twice, and nothing to say which a reader should use."""
    mask = await _mask(authenticated_context)
    features = await _features_table(authenticated_context)
    first = await _store(authenticated_context, "one", "csr_matrix")
    second = await _store(authenticated_context, "two", "csr_matrix")

    result = await _create(
        authenticated_context,
        "expression",
        stores=[str(first.pk), str(second.pk)],
        keyedBy=[{"kind": "DATASET", "dataset": str(mask.pk)}],
        axisReferences=[{"axis": "feature", "references": features}],
    )
    assert result.errors
    assert "one capability twice" in str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_store_whose_shape_contradicts_the_axes_is_refused(authenticated_context: HttpContext):
    """The check only possible because the store read its own shape rather than being told it."""
    mask = await _mask(authenticated_context)
    features = await _features_table(authenticated_context)
    first = await _store(authenticated_context, "one", "csr_matrix")
    transposed = await _store(authenticated_context, "two", "csc_matrix", shape=list(reversed(SHAPE)))

    result = await _create(
        authenticated_context,
        "expression",
        stores=[str(first.pk), str(transposed.pk)],
        keyedBy=[{"kind": "DATASET", "dataset": str(mask.pk)}],
        axisReferences=[{"axis": "feature", "references": features}],
    )
    assert result.errors
    assert "Two different matrices are two datasets" in str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_unfinished_store_is_refused(authenticated_context: HttpContext):
    """An unfinished store knows nothing about itself, so a dataset over it would know nothing."""
    mask = await _mask(authenticated_context)
    features = await _features_table(authenticated_context)
    store = await _store(authenticated_context, "unfinished", "csr_matrix")
    await sync_to_async(models.SparseStore.objects.filter(pk=store.pk).update)(populated=False, encoding=None, shape=None)

    result = await _create(
        authenticated_context,
        "expression",
        stores=[str(store.pk)],
        keyedBy=[{"kind": "DATASET", "dataset": str(mask.pk)}],
        axisReferences=[{"axis": "feature", "references": features}],
    )
    assert result.errors
    assert "finishSparseUpload" in str(result.errors[0]), "name the step that would have read it"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_non_index_axis_is_refused(authenticated_context: HttpContext):
    """Both axes enumerate. A CHANNEL axis is one a layer samples per position, and there are far too many here."""
    features = await _features_table(authenticated_context)
    store = await _store(authenticated_context, "by-feature", "csr_matrix")

    result = await schema.execute(
        CREATE,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "name": "expression",
                "axes": [{"name": "feature", "type": "CHANNEL"}, {"name": "object", "type": "INDEX"}],
                "stores": [str(store.pk)],
                "axisReferences": [{"axis": "feature", "references": features}],
            }
        },
    )
    assert result.errors
    assert "something other than INDEX" in str(result.errors[0])


CREATE_LABEL_LAYER = """
mutation Create($input: CreateLabelLayerInput!) {
  createLabelLayer(input: $input) {
    id
    labelRender {
      colorBys { kind table column dataset at { axis value } colormap min max label }
      activeColorBy
    }
  }
}
"""


async def _placed_mask(ctx: HttpContext):
    """A mask with a lens and a scene it is registered into -- what a label layer needs."""
    mask = await _mask(ctx)
    lens = await seed.create_lens(ctx, mask)
    scene = await seed.create_scene(ctx, "cells")
    await seed.register_into_scene(ctx, scene, mask)
    return mask, lens, scene


async def _expression(ctx: HttpContext, mask, *, encodings: tuple[str, ...] = ("csr_matrix", "csc_matrix")) -> str:
    """A sparse dataset keyed by ``mask``, its feature axis identified by a table."""
    features = await _features_table(ctx)
    stores = [str((await _store(ctx, f"store-{encoding}", encoding)).pk) for encoding in encodings]
    result = await _create(
        ctx,
        "expression",
        stores=stores,
        keyedBy=[{"kind": "DATASET", "dataset": str(mask.pk)}],
        axisReferences=[{"axis": "feature", "references": features}],
    )
    assert not result.errors, result.errors
    return result.data["createSparseDataset"]["id"]


async def _colour(ctx, lens, scene, entry: dict) -> object:
    return await schema.execute(
        CREATE_LABEL_LAYER,
        context_value=ctx,
        variable_values={"input": {"lens": str(lens.id), "scene": str(scene.id), "render": {"colorBys": [entry], "activeColorBy": 0}}},
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_label_layer_colours_by_one_slice_of_a_matrix(authenticated_context: HttpContext):
    """The point of the whole exercise: a feature colours the mask, and nothing was rasterised.

    The mask's pixels are object ids; the matrix is indexed by those same ids on one axis and
    by a feature table on the other. Naming a position along the feature axis is naming one
    slice -- a value per object -- which is exactly what a colouring is.
    """
    mask, lens, scene = await _placed_mask(authenticated_context)
    dataset = await _expression(authenticated_context, mask)

    result = await _colour(
        authenticated_context, lens, scene,
        {"kind": "SPARSE", "dataset": dataset, "at": [{"axis": "feature", "value": 7}], "colormap": "MAGMA", "min": 0.0, "max": 12.0, "label": "Feature 7"},
    )
    assert not result.errors, result.errors
    entry = result.data["createLabelLayer"]["labelRender"]["colorBys"][0]

    assert entry["kind"] == "SPARSE"
    assert entry["dataset"] == dataset
    assert entry["at"] == [{"axis": "feature", "value": 7}]
    assert entry["table"] is None and entry["column"] is None, "the other variant's fields are null, not empty strings"
    assert (entry["colormap"], entry["min"], entry["max"]) == ("MAGMA", 0.0, 12.0)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_slice_the_store_would_have_to_scan_for_is_refused(authenticated_context: HttpContext):
    """The layout rule, made visible. This is why the model holds stores at all.

    With only the object-major layout, reading one feature means touching every object's run --
    a scan of the whole store rather than one contiguous range, measured at 1 777 ms against
    2.2 ms. A colouring the server knows would do that is one it refuses rather than publishes.
    """
    mask, lens, scene = await _placed_mask(authenticated_context)
    dataset = await _expression(authenticated_context, mask, encodings=("csc_matrix",))

    result = await _colour(
        authenticated_context, lens, scene,
        {"kind": "SPARSE", "dataset": dataset, "at": [{"axis": "feature", "value": 7}], "colormap": "MAGMA"},
    )
    assert result.errors
    message = str(result.errors[0])
    assert "holds no layout indexed on 'feature'" in message
    assert "scanning every byte" in message, "say what it would cost, not just that it is refused"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_position_along_the_keyed_axis_is_refused(authenticated_context: HttpContext):
    """Naming the object axis asks for one object's whole profile, which is a hover, not a colouring."""
    mask, lens, scene = await _placed_mask(authenticated_context)
    dataset = await _expression(authenticated_context, mask)

    result = await _colour(
        authenticated_context, lens, scene,
        {"kind": "SPARSE", "dataset": dataset, "at": [{"axis": "object", "value": 3}], "colormap": "MAGMA"},
    )
    assert result.errors
    assert "one object's whole profile" in str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_out_of_range_position_is_refused(authenticated_context: HttpContext):
    """A position is a row of the table that axis references, not an id of its own."""
    mask, lens, scene = await _placed_mask(authenticated_context)
    dataset = await _expression(authenticated_context, mask)

    result = await _colour(
        authenticated_context, lens, scene,
        {"kind": "SPARSE", "dataset": dataset, "at": [{"axis": "feature", "value": SHAPE[0]}], "colormap": "MAGMA"},
    )
    assert result.errors
    assert f"runs 0..{SHAPE[0] - 1}" in str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_sparse_colouring_is_measured_and_takes_no_class_map(authenticated_context: HttpContext):
    """A slice is a value per object. Nothing stores categories sparsely -- the zeros would be one."""
    mask, lens, scene = await _placed_mask(authenticated_context)
    dataset = await _expression(authenticated_context, mask)

    result = await _colour(
        authenticated_context, lens, scene,
        {"kind": "SPARSE", "dataset": dataset, "at": [{"axis": "feature", "value": 1}], "classColors": {"a": [1, 2, 3, 4]}},
    )
    assert result.errors
    assert "never a `classColors`" in str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_matrix_no_field_edge_reaches_is_refused(authenticated_context: HttpContext):
    """The ids that select a value have to be the ids this source supplies."""
    mask, lens, scene = await _placed_mask(authenticated_context)
    other = await _mask(authenticated_context, "other labels")
    dataset = await _expression(authenticated_context, other)

    result = await _colour(
        authenticated_context, lens, scene,
        {"kind": "SPARSE", "dataset": dataset, "at": [{"axis": "feature", "value": 1}], "colormap": "MAGMA"},
    )
    assert result.errors
    assert "not reachable from this mask by a FIELD edge" in str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_two_slices_of_one_matrix_are_two_colourings(authenticated_context: HttpContext):
    """The duplicate check keys on the whole rendering, and a position is part of it.

    Before the variant's fields joined that key, two different features would have keyed
    identically and the second been refused as a copy of the first -- which is the whole
    feature failing on its second entry.
    """
    mask, lens, scene = await _placed_mask(authenticated_context)
    dataset = await _expression(authenticated_context, mask)

    result = await schema.execute(
        CREATE_LABEL_LAYER,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "lens": str(lens.id),
                "scene": str(scene.id),
                "render": {
                    "colorBys": [
                        {"kind": "SPARSE", "dataset": dataset, "at": [{"axis": "feature", "value": 3}], "colormap": "MAGMA", "label": "Feature 3"},
                        {"kind": "SPARSE", "dataset": dataset, "at": [{"axis": "feature", "value": 9}], "colormap": "MAGMA", "label": "Feature 9"},
                    ],
                    "activeColorBy": 1,
                },
            }
        },
    )
    assert not result.errors, result.errors
    render = result.data["createLabelLayer"]["labelRender"]
    assert [entry["at"][0]["value"] for entry in render["colorBys"]] == [3, 9]
    assert render["activeColorBy"] == 1, "and switching between them is an index, not a re-upload"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_matrix_a_picker_names_cannot_be_deleted(authenticated_context: HttpContext):
    """The PROTECT a JSON column cannot express as a foreign key.

    A colouring names its source by id inside `label_render`, so nothing cascades. Without this
    guard the delete would succeed and the entry survive -- looking valid until a renderer went
    looking for bytes that are gone, in a viewer, to whoever opened the scene next.
    """
    mask, lens, scene = await _placed_mask(authenticated_context)
    dataset = await _expression(authenticated_context, mask)

    coloured = await _colour(
        authenticated_context, lens, scene,
        {"kind": "SPARSE", "dataset": dataset, "at": [{"axis": "feature", "value": 2}], "colormap": "MAGMA"},
    )
    assert not coloured.errors, coloured.errors

    result = await schema.execute(
        "mutation Delete($input: DeleteSparseDatasetInput!) { deleteSparseDataset(input: $input) }",
        context_value=authenticated_context,
        variable_values={"input": {"id": dataset}},
    )
    assert result.errors, "a matrix a picker names must not be deletable"
    message = str(result.errors[0])
    assert "colour by a slice of it" in message
    assert "layer" in message and "scene" in message, "name what is holding it, not just that something is"
    assert await sync_to_async(models.SparseDataset.objects.filter(pk=dataset).exists)(), "the refusal left it in place"


OPTIONS = """
query Options($lens: ID!, $filters: ColumnOptionFilter) {
  labelColorByOptions(lens: $lens, filters: $filters) {
    control
    column { name }
    table { name }
    sparseDataset { id name }
    axis
  }
}
"""


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_the_picker_offers_the_sliceable_axis_not_every_position(authenticated_context: HttpContext):
    """One option per axis, and only an axis a stored layout indexes.

    Enumerating positions is what this whole design exists to avoid -- a matrix with 19 059
    features would be 19 059 options through GraphQL. The option names the slice-able axis; the
    client picks the position out of the table that axis references, which it already holds a
    grant for. That is the same line `core.logic.tables` draws about a picker wanting values.
    """
    mask, lens, scene = await _placed_mask(authenticated_context)
    dataset = await _expression(authenticated_context, mask)

    result = await schema.execute(OPTIONS, context_value=authenticated_context, variable_values={"lens": str(lens.id), "filters": None})
    assert not result.errors, result.errors
    sparse = [option for option in result.data["labelColorByOptions"] if option["sparseDataset"] is not None]

    assert len(sparse) == 1, "one option per slice-able axis, not one per position"
    assert sparse[0]["axis"] == "feature", "the axis it identifies itself -- not the one the mask's ids index"
    assert sparse[0]["sparseDataset"]["id"] == dataset
    assert sparse[0]["control"] == "MEASURE", "a slice is a value per object; there is nothing categorical about it"
    assert sparse[0]["table"] is None and sparse[0]["column"] is None, "an option is one half or the other, never both"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_axis_no_layout_indexes_is_not_offered(authenticated_context: HttpContext):
    """The invariant: everything offered is something the mutation accepts.

    With only the object-major layout, a colouring along `feature` is refused -- so offering it
    would be a picker proposing what the write path declines, which is the one failure the
    options query exists to prevent.
    """
    mask, lens, scene = await _placed_mask(authenticated_context)
    await _expression(authenticated_context, mask, encodings=("csc_matrix",))

    result = await schema.execute(OPTIONS, context_value=authenticated_context, variable_values={"lens": str(lens.id), "filters": None})
    assert not result.errors, result.errors
    assert not [option for option in result.data["labelColorByOptions"] if option["sparseDataset"] is not None], (
        "an axis no stored layout indexes is a scan, and a scan is not offered"
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_narrowing_by_role_excludes_the_sparse_half(authenticated_context: HttpContext):
    """A role is a property of a column, and a slice of a matrix has none.

    So filtering for one returns fewer options, never more -- asking for what an option does not
    have must not match all of them.
    """
    mask, lens, scene = await _placed_mask(authenticated_context)
    await _expression(authenticated_context, mask)

    result = await schema.execute(
        OPTIONS, context_value=authenticated_context, variable_values={"lens": str(lens.id), "filters": {"roles": ["ATTRIBUTE"]}}
    )
    assert not result.errors, result.errors
    assert not [option for option in result.data["labelColorByOptions"] if option["sparseDataset"] is not None]

    searched = await schema.execute(
        OPTIONS, context_value=authenticated_context, variable_values={"lens": str(lens.id), "filters": {"search": "feature"}}
    )
    assert not searched.errors, searched.errors
    assert [option["axis"] for option in searched.data["labelColorByOptions"] if option["sparseDataset"]] == ["feature"], (
        "searching matches the axis name and the matrix's own"
    )


SPARSE_PLANS = """
query Plans($system: ID!) {
  attributePlans(system: $system) {
    table { name }
    sparseDataset { id name }
    sample { consumes produces passthrough }
    lookup { kind sql keyAxis valueAxis sparseStore { id encoding } keyColumns { axis } }
  }
}
"""


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_matrix_publishes_a_plan_that_reads_one_slice(authenticated_context: HttpContext):
    """Hover, and the other half of why both layouts are stored.

    The id selects a *slice*, not a row: one read of `indptr` at the object, one of the range
    it names, and back comes every feature that object carries a value for. That is what "what
    is in this object" means for a matrix, and it is a different lookup kind rather than a
    `WHERE` with a hole in it.
    """
    mask = await _mask(authenticated_context)
    await _expression(authenticated_context, mask)
    system = await sync_to_async(lambda: mask.intrinsic_coordinate_system)()

    result = await schema.execute(SPARSE_PLANS, context_value=authenticated_context, variable_values={"system": str(system.pk)})
    assert not result.errors, result.errors
    plans = [plan for plan in result.data["attributePlans"] if plan["sparseDataset"] is not None]
    assert len(plans) == 1, "one plan per matrix the ids index"
    plan = plans[0]

    assert plan["table"] is None, "a plan lands in one or the other, never both"
    assert plan["sample"]["produces"] == ["object"], "the mask supplies the object id"
    assert plan["lookup"]["kind"] == "SPARSE"
    assert plan["lookup"]["sql"] is None, "there is no database in this path"
    assert plan["lookup"]["keyColumns"] == [], "and no columns to bind"
    assert plan["lookup"]["keyAxis"] == "object", "the id binds to the axis the store's indptr indexes"
    assert plan["lookup"]["valueAxis"] == "feature", "and every position along the other comes back"
    assert plan["lookup"]["sparseStore"]["encoding"] == "csc_matrix", "the object-major layout, which is the one that can answer this"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_no_plan_when_only_the_wrong_layout_is_stored(authenticated_context: HttpContext):
    """A plan for a scan is not a slow plan; it is one nobody should execute.

    With only the feature-major layout, reading one object means touching every feature's run.
    The dataset simply publishes no plan until the transposed layout is registered -- the same
    conclusion, and for the same reason, as the colouring that gets refused in the mirror case.
    """
    mask = await _mask(authenticated_context)
    await _expression(authenticated_context, mask, encodings=("csr_matrix",))
    system = await sync_to_async(lambda: mask.intrinsic_coordinate_system)()

    result = await schema.execute(SPARSE_PLANS, context_value=authenticated_context, variable_values={"system": str(system.pk)})
    assert not result.errors, result.errors
    assert not [plan for plan in result.data["attributePlans"] if plan["sparseDataset"] is not None]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_the_two_layouts_answer_the_two_questions(authenticated_context: HttpContext):
    """The whole argument for storing both, in one test.

    Feature-major answers the colouring ("every object's value for this feature"); object-major
    answers the plan ("every feature's value for this object"). Neither can answer the other's,
    so a dataset holding both offers both and a dataset holding one offers one.
    """
    mask, lens, scene = await _placed_mask(authenticated_context)
    dataset = await _expression(authenticated_context, mask)
    system = await sync_to_async(lambda: mask.intrinsic_coordinate_system)()

    coloured = await _colour(
        authenticated_context, lens, scene,
        {"kind": "SPARSE", "dataset": dataset, "at": [{"axis": "feature", "value": 5}], "colormap": "MAGMA"},
    )
    assert not coloured.errors, coloured.errors

    plans = await schema.execute(SPARSE_PLANS, context_value=authenticated_context, variable_values={"system": str(system.pk)})
    assert not plans.errors, plans.errors
    plan = next(plan for plan in plans.data["attributePlans"] if plan["sparseDataset"] is not None)

    assert plan["lookup"]["sparseStore"]["encoding"] == "csc_matrix", "hover reads the object-major layout"
    assert coloured.data["createLabelLayer"]["labelRender"]["colorBys"][0]["at"] == [{"axis": "feature", "value": 5}]
