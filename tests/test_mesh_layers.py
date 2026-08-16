"""Colouring a mesh layer by a column of the table its collection keys into.

The same display pick a label layer makes with `colorBy`, over the same relation: a
`FIELD` edge from the collection into a table of per-object rows, authored by
`createTableDataset(keyedBy: {kind: MESH_COLLECTION})`. What differs is only where the id
was materialised -- on the geometry rows rather than in pixels -- which is invisible from
here, and is exactly the point: the check is one function for both layer kinds.

The refusals matter more than the happy path. A `colorBy` naming a table nothing reaches
is not a preference a client can hold onto until the edge shows up; it is a join nothing
can execute, and it would sit in the column looking valid until a renderer tried it.
"""

import pytest
from asgiref.sync import sync_to_async
from kante.context import HttpContext

from core import enums, models
from mikro_server.schema import schema
from tests import seed

CREATE_LAYER = """
mutation Create($input: CreateMeshLayerInput!) {
  createMeshLayer(input: $input) {
    id
    materialColor
    wireframe
    colorBy { table column colormap classColors }
  }
}
"""

UPDATE_LAYER = """
mutation Update($input: UpdateMeshLayerInput!) {
  updateMeshLayer(input: $input) {
    id
    materialColor
    wireframe
    opacity
    colorBy { table column colormap classColors }
  }
}
"""

CREATE_TABLE = """
mutation Create($input: CreateTableDatasetInput!) {
  createTableDataset(input: $input) { id }
}
"""

ZYX_MESH_AXES = [{"name": "z", "type": "SPACE"}, {"name": "y", "type": "SPACE"}, {"name": "x", "type": "SPACE"}]

#: One measure column and one categorical one, so both halves of the role split are testable
#: off a single table.
SHAPE_COLUMNS = [
    {"name": "object", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"},
    {"name": "volume", "dtype": "DOUBLE", "role": "ATTRIBUTE"},
    {"name": "cell_type", "dtype": "VARCHAR", "role": "LABEL"},
]


async def _collection(ctx: HttpContext) -> models.MeshCollection:
    """A mesh collection in a space of its own, registered into a scene's world."""
    store = await seed.create_fabriks_store(ctx)
    result = await schema.execute(
        "mutation Create($input: CreateMeshCollectionInput!) { createMeshCollection(input: $input) { id } }",
        context_value=ctx,
        variable_values={"input": {"version": "v1", "store": str(store.pk), "axes": ZYX_MESH_AXES}},
    )
    assert not result.errors, result.errors
    return await sync_to_async(models.MeshCollection.objects.get)(id=result.data["createMeshCollection"]["id"])


async def _scene_for(ctx: HttpContext, collection: models.MeshCollection) -> models.Scene:
    """A scene the collection is placed in, so the layer mutation's placement gate passes."""
    scene = await seed.create_scene(ctx, "Composition")

    def register() -> None:
        models.Transformation.objects.create(
            kind="IDENTITY",
            input=collection.coordinate_system,
            output=scene.world,
            params={},
            organization=ctx.request.organization,
        )

    await sync_to_async(register)()
    return scene


async def _table(ctx: HttpContext, name: str, columns: list[dict], **extra: object) -> str:
    store = await sync_to_async(models.ParquetStore.objects.create)(path=f"s3://parquet/{name}", bucket="parquet", key=name, organization=ctx.request.organization)
    result = await schema.execute(
        CREATE_TABLE,
        context_value=ctx,
        variable_values={"input": {"name": name, "data": str(store.pk), "columns": columns, **extra}},
    )
    assert not result.errors, result.errors
    return result.data["createTableDataset"]["id"]


async def _create_layer(ctx: HttpContext, scene: models.Scene, collection: models.MeshCollection, **extra: object):
    return await schema.execute(
        CREATE_LAYER,
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.pk), "meshCollection": str(collection.pk), **extra}},
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_mesh_layer_colours_by_a_keyed_table(authenticated_context: HttpContext):
    """The whole point of keying a table by a collection, seen from the renderer's end."""
    collection = await _collection(authenticated_context)
    scene = await _scene_for(authenticated_context, collection)
    table = await _table(authenticated_context, "shape-stats", SHAPE_COLUMNS, keyedBy=[{"kind": "MESH_COLLECTION", "meshCollection": str(collection.pk)}])

    result = await _create_layer(authenticated_context, scene, collection, colorBy={"table": table, "column": "volume", "colormap": "VIRIDIS"})
    assert not result.errors, result.errors

    layer = result.data["createMeshLayer"]
    assert layer["colorBy"] == {"table": table, "column": "volume", "colormap": "VIRIDIS", "classColors": None}
    assert layer["materialColor"] == [255, 255, 255, 255], "the material is still there; colouring by a column does not erase it"

    # The column stores the enum's *value*, which is the lowercase name the renderer uses;
    # the SDL reports the member. Asserted on both sides because the dump is what a
    # renderer reads and the response is what a client caches.
    stored = await models.Layer.objects.aget(id=layer["id"])
    assert stored.mesh_color_by == {"table": table, "column": "volume", "colormap": "viridis", "class_colors": None}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_mesh_layer_without_a_colour_by_reads_back_null(authenticated_context: HttpContext):
    """Null means the material colour is what is drawn, and is the shape every existing row has.

    `mesh_color_by` is a new column with no backfill, so every mesh layer written before it
    existed reads through this resolver. A default of `{}` rather than null would make each
    of those an empty ColorBy that a renderer would try to execute.
    """
    collection = await _collection(authenticated_context)
    scene = await _scene_for(authenticated_context, collection)

    result = await _create_layer(authenticated_context, scene, collection, materialColor=[10, 20, 30, 255])
    assert not result.errors, result.errors
    assert result.data["createMeshLayer"]["colorBy"] is None
    assert result.data["createMeshLayer"]["materialColor"] == [10, 20, 30, 255]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_mesh_layer_refuses_a_table_no_field_edge_reaches(authenticated_context: HttpContext):
    """A join nothing can execute is refused where it is written, not where it is drawn."""
    collection = await _collection(authenticated_context)
    scene = await _scene_for(authenticated_context, collection)
    unrelated = await _table(authenticated_context, "unrelated", SHAPE_COLUMNS)

    result = await _create_layer(authenticated_context, scene, collection, colorBy={"table": unrelated, "column": "volume", "colormap": "VIRIDIS"})
    assert result.errors
    message = str(result.errors[0])
    assert "not reachable from this collection by a FIELD edge" in message
    assert "keyedBy" in message, "point at the call that would make it reachable"
    assert not await sync_to_async(models.Layer.objects.exists)()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_mesh_layer_refuses_an_unknown_column(authenticated_context: HttpContext):
    """The table is reachable, but nothing in it is called that."""
    collection = await _collection(authenticated_context)
    scene = await _scene_for(authenticated_context, collection)
    table = await _table(authenticated_context, "shape-stats", SHAPE_COLUMNS, keyedBy=[{"kind": "MESH_COLLECTION", "meshCollection": str(collection.pk)}])

    result = await _create_layer(authenticated_context, scene, collection, colorBy={"table": table, "column": "sphericity", "colormap": "VIRIDIS"})
    assert result.errors
    assert "declares no column 'sphericity'" in str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_the_column_role_decides_which_colouring_applies(authenticated_context: HttpContext):
    """A measure column takes a colormap; a categorical one takes an explicit map, never both ways.

    The same rule label layers hold to, and it has to be checked here too rather than
    inherited: `colorBy` is validated against the table, and the table is the thing that
    knows which of the two a column is.
    """
    collection = await _collection(authenticated_context)
    scene = await _scene_for(authenticated_context, collection)
    table = await _table(authenticated_context, "shape-stats", SHAPE_COLUMNS, keyedBy=[{"kind": "MESH_COLLECTION", "meshCollection": str(collection.pk)}])

    measured_with_classes = await _create_layer(authenticated_context, scene, collection, colorBy={"table": table, "column": "volume", "classColors": {"1": [255, 0, 0, 255]}})
    assert measured_with_classes.errors
    assert "coloured by a `colormap` over their range" in str(measured_with_classes.errors[0])

    categorical_with_colormap = await _create_layer(authenticated_context, scene, collection, colorBy={"table": table, "column": "cell_type", "colormap": "VIRIDIS"})
    assert categorical_with_colormap.errors
    assert "impose an order they do not have" in str(categorical_with_colormap.errors[0])

    categorical_with_classes = await _create_layer(authenticated_context, scene, collection, colorBy={"table": table, "column": "cell_type", "classColors": {"nucleus": [255, 0, 0, 255]}})
    assert not categorical_with_classes.errors, categorical_with_classes.errors
    assert categorical_with_classes.data["createMeshLayer"]["colorBy"]["classColors"] == {"nucleus": [255, 0, 0, 255]}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_updating_the_colouring_keeps_everything_not_named(authenticated_context: HttpContext):
    """A patch, not a replacement: retuning the colouring must not drop the material.

    Without an update mutation the only way to recolour was to delete the layer and create
    it again, which loses its place in the scene's compositing order -- and a create-shaped
    update would quietly reset `materialColor` and `wireframe` to their defaults.
    """
    collection = await _collection(authenticated_context)
    scene = await _scene_for(authenticated_context, collection)
    table = await _table(authenticated_context, "shape-stats", SHAPE_COLUMNS, keyedBy=[{"kind": "MESH_COLLECTION", "meshCollection": str(collection.pk)}])

    created = await _create_layer(authenticated_context, scene, collection, materialColor=[10, 20, 30, 255], wireframe=True, opacity=0.5)
    assert not created.errors, created.errors
    layer_id = created.data["createMeshLayer"]["id"]

    result = await schema.execute(
        UPDATE_LAYER,
        context_value=authenticated_context,
        variable_values={"input": {"id": layer_id, "colorBy": {"table": table, "column": "volume", "colormap": "MAGMA"}}},
    )
    assert not result.errors, result.errors

    updated = result.data["updateMeshLayer"]
    assert updated["colorBy"] == {"table": table, "column": "volume", "colormap": "MAGMA", "classColors": None}
    assert updated["materialColor"] == [10, 20, 30, 255], "omitted, so unchanged"
    assert updated["wireframe"] is True, "omitted, so unchanged"
    assert updated["opacity"] == 0.5, "omitted, so unchanged"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_updating_a_layer_that_is_not_a_mesh_is_refused(authenticated_context: HttpContext):
    """The vocabulary is per-kind: an image layer has no material to set."""
    scene = await seed.create_scene(authenticated_context, "Composition")
    layer = await sync_to_async(models.Layer.objects.create)(kind=enums.LayerKindChoices.IMAGE.value, scene=scene)

    result = await schema.execute(
        UPDATE_LAYER,
        context_value=authenticated_context,
        variable_values={"input": {"id": str(layer.pk), "wireframe": True}},
    )
    assert result.errors
    assert "not a mesh layer" in str(result.errors[0])
