"""Tests for the polymorphic layer subtypes backed by non-array sources.

Each subtype (ShapeLayer, PointLayer, TrackLayer, MeshLayer) is a concrete
implementation of the ``Layer`` interface, placed in a scene and returned
heterogeneously through ``Scene.layers``. Every source must already have a
path to the scene's world -- a layer mutation checks the placement, it never
writes one -- so each seed helper hands back the coordinate system to register.
"""

import pytest

from asgiref.sync import sync_to_async
from core import models, enums
from core.logic import graph as graph_logic
from kante.context import HttpContext
from mikro_server.schema import schema
from tests import seed


async def _seed_scene(ctx: HttpContext) -> models.Scene:
    return await seed.create_scene(ctx)


def _seed_table_dataset_sync(ctx: HttpContext, key: str, *, with_track: bool = False) -> models.TableDataset:
    """A table dataset with declared coordinate columns -- the only table a layer draws from.

    The dataset is the whole mapping: coordinate columns are its axes, its own system is
    the space, and the roles are the identities. No layer binds a column by name.
    """
    store = models.ParquetStore.objects.create(path=f"s3://parquet/{key}", bucket="parquet", key=key, organization=ctx.request.organization)
    dataset = models.TableDataset.objects.create(name=key, store=store, organization=ctx.request.organization)
    columns = [
        {"name": "y", "role": enums.TableColumnRoleChoices.COORDINATE.value, "axis_type": enums.AxisTypeChoices.SPACE.value},
        {"name": "x", "role": enums.TableColumnRoleChoices.COORDINATE.value, "axis_type": enums.AxisTypeChoices.SPACE.value},
        {"name": "photons", "role": enums.TableColumnRoleChoices.ATTRIBUTE.value, "axis_type": None},
    ]
    if with_track:
        columns.append({"name": "track", "role": enums.TableColumnRoleChoices.TRACK_ID.value, "axis_type": None})
    for order, column in enumerate(columns):
        models.TableColumn.objects.create(table=dataset, order=order, dtype="DOUBLE", **column)
    graph_logic.create_collection_system(
        name=f"{key}/table",
        axes=[seed.axis("y", enums.AxisType.SPACE), seed.axis("x", enums.AxisType.SPACE)],
        owner_field="table_dataset",
        owner=dataset,
        ctx=seed._creation(ctx),
    )
    return dataset


async def _seed_table_dataset(ctx: HttpContext, key: str, *, with_track: bool = False) -> tuple[models.TableDataset, models.CoordinateSystem]:
    dataset = await sync_to_async(_seed_table_dataset_sync)(ctx, key, with_track=with_track)
    system = await sync_to_async(lambda: dataset.coordinate_system)()
    return dataset, system


def _seed_mesh_collection_sync(ctx: HttpContext) -> models.MeshCollection:
    collection = models.MeshCollection.objects.create(
        version="v1",
        spec_version="1.0",
        catalog=models.ParquetStore.objects.create(path="s3://parquet/mesh-catalog", bucket="parquet", key="mesh-catalog", organization=ctx.request.organization),
        organization=ctx.request.organization,
    )
    graph_logic.create_collection_system(
        name=f"{collection.version}/mesh",
        axes=[seed.axis("y", enums.AxisType.SPACE), seed.axis("x", enums.AxisType.SPACE)],
        owner_field="mesh_collection",
        owner=collection,
        ctx=seed._creation(ctx),
    )
    return collection


async def _seed_mesh_collection(ctx: HttpContext) -> tuple[models.MeshCollection, models.CoordinateSystem]:
    collection = await sync_to_async(_seed_mesh_collection_sync)(ctx)
    system = await sync_to_async(lambda: collection.coordinate_system)()
    return collection, system


async def _seed_dataroi(ctx: HttpContext) -> models.DataRoi:
    # An ROI is drawn in a coordinate system, not "on a dataset": that is what lets
    # it outlive the scene it happened to be viewed in.
    dataset = await seed.create_adataset(ctx, "RoiDS", axes=seed.YX_AXES, shapes=[[32, 32]])
    system = await sync_to_async(lambda: dataset.intrinsic_coordinate_system)()
    return await models.DataRoi.objects.acreate(
        coordinate_system=system,
        name="Roi",
        kind=enums.RoiKindChoices.POLYGON.value,
        vectors=[[0.0, 0.0], [0.0, 10.0], [10.0, 10.0]],
        creator=ctx.request.user,
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_shape_layer(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    scene = await _seed_scene(ctx)
    roi = await _seed_dataroi(ctx)
    await seed.register_into_scene(ctx, scene, system=roi.coordinate_system)

    mutation = """
        mutation Create($input: CreateShapeLayerInput!) {
            createShapeLayer(input: $input) {
                id
                __typename
                blending
                opacity
                strokeWidth
                filled
                strokeColor
                dataRoi { id kind }
            }
        }
    """
    result = await schema.execute(
        mutation,
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "dataRoi": str(roi.id), "strokeWidth": 2.5, "filled": True}},
    )
    assert not result.errors, result.errors
    data = result.data["createShapeLayer"]
    assert data["__typename"] == "ShapeLayer"
    assert data["blending"] == "NORMAL"
    assert data["strokeWidth"] == 2.5
    assert data["filled"] is True
    assert data["strokeColor"] == [255, 255, 255, 255]
    assert data["dataRoi"]["id"] == str(roi.id)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_unregistered_shape_layer_is_rejected(db, authenticated_context: HttpContext):
    """The ROI's system has no path to this world, so the layer is refused with the fix named."""
    ctx = authenticated_context
    scene = await _seed_scene(ctx)
    roi = await _seed_dataroi(ctx)

    result = await schema.execute(
        "mutation Create($input: CreateShapeLayerInput!) { createShapeLayer(input: $input) { id } }",
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "dataRoi": str(roi.id)}},
    )
    assert result.errors, "an unplaced ROI system must be refused"
    assert "createTransformation" in str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_shape_layer_appears_in_scene_layers(db, authenticated_context: HttpContext):
    """A ShapeLayer is returned polymorphically through Scene.layers."""
    ctx = authenticated_context
    scene = await _seed_scene(ctx)
    roi = await _seed_dataroi(ctx)
    await seed.register_into_scene(ctx, scene, system=roi.coordinate_system)

    create = "mutation Create($input: CreateShapeLayerInput!) { createShapeLayer(input: $input) { id } }"
    result = await schema.execute(
        create,
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "dataRoi": str(roi.id)}},
    )
    assert not result.errors, result.errors

    query = """
        query Scene($id: ID!) {
            scene(id: $id) {
                layers {
                    __typename
                    id
                    ... on ShapeLayer { strokeWidth dataRoi { id } }
                }
            }
        }
    """
    result = await schema.execute(query, context_value=ctx, variable_values={"id": str(scene.id)})
    assert not result.errors, result.errors
    layers = result.data["scene"]["layers"]
    assert len(layers) == 1
    assert layers[0]["__typename"] == "ShapeLayer"
    assert layers[0]["dataRoi"]["id"] == str(roi.id)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_point_layer(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    scene = await _seed_scene(ctx)
    dataset, system = await _seed_table_dataset(ctx, "points")
    await seed.register_into_scene(ctx, scene, system=system)

    mutation = """
        mutation Create($input: CreatePointLayerInput!) {
            createPointLayer(input: $input) {
                id
                __typename
                blending
                pointSize
                xColumn
                yColumn
                colormap
                tableDataset { id }
            }
        }
    """
    result = await schema.execute(
        mutation,
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "tableDataset": str(dataset.id), "pointSize": 5.0}},
    )
    assert not result.errors, result.errors
    data = result.data["createPointLayer"]
    assert data["__typename"] == "PointLayer"
    assert data["blending"] == "NORMAL"
    assert data["pointSize"] == 5.0
    assert data["xColumn"] == "x", "the coordinate columns come from the dataset's declared schema, never a per-layer binding"
    assert data["colormap"] == "VIRIDIS"
    assert data["tableDataset"]["id"] == str(dataset.id)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_track_layer_needs_a_track_id_column(db, authenticated_context: HttpContext):
    """The track identity is the dataset's TRACK_ID role: a table without one has no tracks to draw."""
    ctx = authenticated_context
    scene = await _seed_scene(ctx)
    dataset, system = await _seed_table_dataset(ctx, "trackless")
    await seed.register_into_scene(ctx, scene, system=system)

    result = await schema.execute(
        "mutation Create($input: CreateTrackLayerInput!) { createTrackLayer(input: $input) { id } }",
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "tableDataset": str(dataset.id)}},
    )
    assert result.errors, "no TRACK_ID column, no tracks"
    assert "TRACK_ID" in str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_track_layer(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    scene = await _seed_scene(ctx)
    dataset, system = await _seed_table_dataset(ctx, "tracks", with_track=True)
    await seed.register_into_scene(ctx, scene, system=system)

    mutation = """
        mutation Create($input: CreateTrackLayerInput!) {
            createTrackLayer(input: $input) {
                id
                __typename
                trackIdColumn
                lineWidth
                tableDataset { id }
            }
        }
    """
    result = await schema.execute(
        mutation,
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "tableDataset": str(dataset.id)}},
    )
    assert not result.errors, result.errors
    data = result.data["createTrackLayer"]
    assert data["__typename"] == "TrackLayer"
    assert data["trackIdColumn"] == "track", "the track identity is the dataset's TRACK_ID column, resolved by role"
    assert data["lineWidth"] == 1.0
    assert data["tableDataset"]["id"] == str(dataset.id)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_mesh_layer(db, authenticated_context: HttpContext):
    """A mesh layer renders a mesh COLLECTION: the collection owns the space the check walks from."""
    ctx = authenticated_context
    scene = await _seed_scene(ctx)
    collection, system = await _seed_mesh_collection(ctx)
    await seed.register_into_scene(ctx, scene, system=system)

    mutation = """
        mutation Create($input: CreateMeshLayerInput!) {
            createMeshLayer(input: $input) {
                id
                __typename
                wireframe
                materialColor
                blending
                collection { id }
            }
        }
    """
    result = await schema.execute(
        mutation,
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "meshCollection": str(collection.id), "wireframe": True}},
    )
    assert not result.errors, result.errors
    data = result.data["createMeshLayer"]
    assert data["__typename"] == "MeshLayer"
    assert data["wireframe"] is True
    assert data["materialColor"] == [255, 255, 255, 255]
    assert data["blending"] == "NORMAL"
    assert data["collection"]["id"] == str(collection.id)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_unregistered_mesh_layer_is_rejected(db, authenticated_context: HttpContext):
    """The collection's own system has no path to this world, so the layer is refused."""
    ctx = authenticated_context
    scene = await _seed_scene(ctx)
    collection, _ = await _seed_mesh_collection(ctx)

    result = await schema.execute(
        "mutation Create($input: CreateMeshLayerInput!) { createMeshLayer(input: $input) { id } }",
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "meshCollection": str(collection.id)}},
    )
    assert result.errors, "an unplaced collection must be refused"
    assert "createTransformation" in str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_heterogeneous_scene_layers(db, authenticated_context: HttpContext):
    """A single scene holding several layer kinds returns them all through the polymorphic interface."""
    ctx = authenticated_context
    scene = await _seed_scene(ctx)
    roi = await _seed_dataroi(ctx)
    table_dataset, table_system = await _seed_table_dataset(ctx, "hetero", with_track=True)
    collection, mesh_system = await _seed_mesh_collection(ctx)
    await seed.register_into_scene(ctx, scene, system=roi.coordinate_system)
    await seed.register_into_scene(ctx, scene, system=table_system)
    await seed.register_into_scene(ctx, scene, system=mesh_system)

    for mutation, variables in [
        ("mutation M($i: CreateShapeLayerInput!){ createShapeLayer(input:$i){ id } }", {"i": {"scene": str(scene.id), "dataRoi": str(roi.id)}}),
        ("mutation M($i: CreatePointLayerInput!){ createPointLayer(input:$i){ id } }", {"i": {"scene": str(scene.id), "tableDataset": str(table_dataset.id)}}),
        ("mutation M($i: CreateTrackLayerInput!){ createTrackLayer(input:$i){ id } }", {"i": {"scene": str(scene.id), "tableDataset": str(table_dataset.id)}}),
        ("mutation M($i: CreateMeshLayerInput!){ createMeshLayer(input:$i){ id } }", {"i": {"scene": str(scene.id), "meshCollection": str(collection.id)}}),
    ]:
        made = await schema.execute(mutation, context_value=ctx, variable_values=variables)
        assert not made.errors, made.errors

    query = """
        query Scene($id: ID!) {
            scene(id: $id) {
                layers {
                    __typename
                    ... on ShapeLayer { dataRoi { id } }
                    ... on PointLayer { pointSize tableDataset { id } }
                    ... on TrackLayer { trackIdColumn tableDataset { id } }
                    ... on MeshLayer { wireframe collection { id } }
                }
            }
        }
    """
    result = await schema.execute(query, context_value=ctx, variable_values={"id": str(scene.id)})
    assert not result.errors, result.errors
    typenames = {layer["__typename"] for layer in result.data["scene"]["layers"]}
    assert typenames == {"ShapeLayer", "PointLayer", "TrackLayer", "MeshLayer"}
