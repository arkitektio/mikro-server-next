"""Tests for the polymorphic layer subtypes backed by non-array sources.

Each subtype (ShapeLayer, PointLayer, TrackLayer, MeshLayer) is a concrete
implementation of the ``Layer`` interface, placed in a scene and returned
heterogeneously through ``Scene.layers``.
"""

import pytest

from core import models, enums
from kante.context import HttpContext
from mikro_server.schema import schema


async def _seed_scene(ctx: HttpContext) -> models.Scene:
    return await models.Scene.objects.acreate(
        name="Scene",
        organization=ctx.request.organization,  # type: ignore[arg-type]
        spatial_unit="micrometers",
        temporal_unit="seconds",
    )


async def _seed_table(ctx: HttpContext) -> models.Table:
    return await models.Table.objects.acreate(
        name="Localisations",
        organization=ctx.request.organization,  # type: ignore[arg-type]
    )


async def _seed_mesh(ctx: HttpContext) -> models.Mesh:
    return await models.Mesh.objects.acreate(
        name="Surface",
        organization=ctx.request.organization,  # type: ignore[arg-type]
    )


async def _seed_dataroi(ctx: HttpContext) -> models.DataRoi:
    dataset = await models.ADataset.objects.acreate(
        name="RoiDS",
        shape=[32, 32],
        dims=["y", "x"],
        dim_descriptors=[{"key": "y", "kind": "space"}, {"key": "x", "kind": "space"}],
        organization=ctx.request.organization,  # type: ignore[arg-type]
    )
    return await models.DataRoi.objects.acreate(
        dataset=dataset,
        name="Roi",
        kind=enums.RoiKindChoices.POLYGON.value,
        x_dim="x",
        y_dim="y",
        vectors=[[0.0, 0.0], [0.0, 10.0], [10.0, 10.0]],
        constraints={},
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_shape_layer(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    scene = await _seed_scene(ctx)
    roi = await _seed_dataroi(ctx)

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
async def test_shape_layer_appears_in_scene_layers(db, authenticated_context: HttpContext):
    """A ShapeLayer is returned polymorphically through Scene.layers."""
    ctx = authenticated_context
    scene = await _seed_scene(ctx)
    roi = await _seed_dataroi(ctx)

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
    table = await _seed_table(ctx)

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
                table { id }
            }
        }
    """
    result = await schema.execute(
        mutation,
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "table": str(table.id), "xColumn": "x", "yColumn": "y", "pointSize": 5.0}},
    )
    assert not result.errors, result.errors
    data = result.data["createPointLayer"]
    assert data["__typename"] == "PointLayer"
    assert data["blending"] == "NORMAL"
    assert data["pointSize"] == 5.0
    assert data["xColumn"] == "x"
    assert data["colormap"] == "VIRIDIS"
    assert data["table"]["id"] == str(table.id)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_track_layer(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    scene = await _seed_scene(ctx)
    table = await _seed_table(ctx)

    mutation = """
        mutation Create($input: CreateTrackLayerInput!) {
            createTrackLayer(input: $input) {
                id
                __typename
                trackIdColumn
                lineWidth
                table { id }
            }
        }
    """
    result = await schema.execute(
        mutation,
        context_value=ctx,
        variable_values={
            "input": {"scene": str(scene.id), "table": str(table.id), "trackIdColumn": "track", "xColumn": "x", "yColumn": "y", "tColumn": "t"}
        },
    )
    assert not result.errors, result.errors
    data = result.data["createTrackLayer"]
    assert data["__typename"] == "TrackLayer"
    assert data["trackIdColumn"] == "track"
    assert data["lineWidth"] == 1.0
    assert data["table"]["id"] == str(table.id)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_mesh_layer(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    scene = await _seed_scene(ctx)
    mesh = await _seed_mesh(ctx)

    mutation = """
        mutation Create($input: CreateMeshLayerInput!) {
            createMeshLayer(input: $input) {
                id
                __typename
                wireframe
                materialColor
                blending
                mesh { id name }
            }
        }
    """
    result = await schema.execute(
        mutation,
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "mesh": str(mesh.id), "wireframe": True}},
    )
    assert not result.errors, result.errors
    data = result.data["createMeshLayer"]
    assert data["__typename"] == "MeshLayer"
    assert data["wireframe"] is True
    assert data["materialColor"] == [255, 255, 255, 255]
    assert data["blending"] == "NORMAL"
    assert data["mesh"]["id"] == str(mesh.id)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_heterogeneous_scene_layers(db, authenticated_context: HttpContext):
    """A single scene holding several layer kinds returns them all through the polymorphic interface."""
    ctx = authenticated_context
    scene = await _seed_scene(ctx)
    roi = await _seed_dataroi(ctx)
    table = await _seed_table(ctx)
    mesh = await _seed_mesh(ctx)

    await schema.execute(
        "mutation M($i: CreateShapeLayerInput!){ createShapeLayer(input:$i){ id } }",
        context_value=ctx,
        variable_values={"i": {"scene": str(scene.id), "dataRoi": str(roi.id)}},
    )
    await schema.execute(
        "mutation M($i: CreatePointLayerInput!){ createPointLayer(input:$i){ id } }",
        context_value=ctx,
        variable_values={"i": {"scene": str(scene.id), "table": str(table.id), "xColumn": "x", "yColumn": "y"}},
    )
    await schema.execute(
        "mutation M($i: CreateTrackLayerInput!){ createTrackLayer(input:$i){ id } }",
        context_value=ctx,
        variable_values={"i": {"scene": str(scene.id), "table": str(table.id), "trackIdColumn": "t", "xColumn": "x", "yColumn": "y"}},
    )
    await schema.execute(
        "mutation M($i: CreateMeshLayerInput!){ createMeshLayer(input:$i){ id } }",
        context_value=ctx,
        variable_values={"i": {"scene": str(scene.id), "mesh": str(mesh.id)}},
    )

    query = """
        query Scene($id: ID!) {
            scene(id: $id) {
                layers {
                    __typename
                    ... on ShapeLayer { dataRoi { id } }
                    ... on PointLayer { pointSize table { id } }
                    ... on TrackLayer { trackIdColumn table { id } }
                    ... on MeshLayer { wireframe mesh { id } }
                }
            }
        }
    """
    result = await schema.execute(query, context_value=ctx, variable_values={"id": str(scene.id)})
    assert not result.errors, result.errors
    typenames = {layer["__typename"] for layer in result.data["scene"]["layers"]}
    assert typenames == {"ShapeLayer", "PointLayer", "TrackLayer", "MeshLayer"}
