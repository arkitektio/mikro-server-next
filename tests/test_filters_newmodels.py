"""Filter tests for the multi-dimensional data system queries
(ADataset, Scene, Layer, Lens, DataRoi)."""

import pytest

from core import enums
from core.models import ADataset, DataRoi, Layer, Lens, Scene
from kante.context import HttpContext
from mikro_server.schema import schema

from tests.seed import create_other_user


async def execute(ctx, query, filters):
    result = await schema.execute(query, context_value=ctx, variable_values={"filters": filters})
    assert not result.errors, result.errors
    return result.data


async def create_adataset(ctx, name, **kwargs):
    return await ADataset.objects.acreate(
        name=name,
        shape=[1, 1, 1, 100, 100],
        dims=["t", "c", "z", "x", "y"],
        creator=kwargs.pop("creator", ctx.request.user),
        organization=ctx.request.organization,
        **kwargs,
    )


async def create_lens(dataset):
    return await Lens.objects.acreate(
        dataset=dataset,
        shape=[1, 1, 1, 100, 100],
        dims=["t", "c", "z", "x", "y"],
        dim_descriptors=[],
    )


async def create_scene(name, **kwargs):
    return await Scene.objects.acreate(
        name=name,
        spatial_unit="micrometers",
        temporal_unit="seconds",
        **kwargs,
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_adataset_filters(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    other = await create_other_user(ctx)
    await create_adataset(ctx, "Acquisition", description="raw stack")
    await create_adataset(ctx, "Processed", creator=other)

    query = """
        query List($filters: ADatasetFilter) {
            adatasets(filters: $filters) { id name }
        }
    """

    data = await execute(ctx, query, {"search": "acq"})
    assert {d["name"] for d in data["adatasets"]} == {"Acquisition"}

    data = await execute(ctx, query, {"owner": "2"})
    assert {d["name"] for d in data["adatasets"]} == {"Processed"}

    data = await execute(ctx, query, {"description": {"iContains": "raw"}})
    assert {d["name"] for d in data["adatasets"]} == {"Acquisition"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_scene_filters(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    root = await create_scene("RootScene")
    await create_scene("SubScene", parent=root)

    query = """
        query List($filters: SceneFilter) {
            scenes(filters: $filters) { id name }
        }
    """

    data = await execute(ctx, query, {"search": "sub"})
    assert {s["name"] for s in data["scenes"]} == {"SubScene"}

    data = await execute(ctx, query, {"parentless": True})
    assert {s["name"] for s in data["scenes"]} == {"RootScene"}

    data = await execute(ctx, query, {"parent": str(root.id)})
    assert {s["name"] for s in data["scenes"]} == {"SubScene"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_layer_filters(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    adataset = await create_adataset(ctx, "ADS")
    lens_a = await create_lens(adataset)
    lens_b = await create_lens(adataset)
    scene_a = await create_scene("SceneA")
    scene_b = await create_scene("SceneB")

    active = await Layer.objects.acreate(
        scene=scene_a, lens=lens_a, x_dim="x", y_dim="y", status=enums.PlacementStatus.ACTIVE.value
    )
    archived = await Layer.objects.acreate(
        scene=scene_b, lens=lens_b, x_dim="x", y_dim="y", status=enums.PlacementStatus.ARCHIVED.value
    )

    query = """
        query List($filters: LayerFilter) {
            layers(filters: $filters) { id }
        }
    """

    data = await execute(ctx, query, {"status": "ACTIVE"})
    assert {layer["id"] for layer in data["layers"]} == {str(active.id)}

    data = await execute(ctx, query, {"scene": str(scene_b.id)})
    assert {layer["id"] for layer in data["layers"]} == {str(archived.id)}

    data = await execute(ctx, query, {"lens": str(lens_a.id)})
    assert {layer["id"] for layer in data["layers"]} == {str(active.id)}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_lens_filter_by_dataset(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    ds_a = await create_adataset(ctx, "A")
    ds_b = await create_adataset(ctx, "B")
    lens_a = await create_lens(ds_a)
    await create_lens(ds_b)

    query = """
        query List($filters: LensFilter) {
            lenses(filters: $filters) { id }
        }
    """
    data = await execute(ctx, query, {"dataset": str(ds_a.id)})
    assert {lens["id"] for lens in data["lenses"]} == {str(lens_a.id)}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_data_roi_filters(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    ds_a = await create_adataset(ctx, "A")
    ds_b = await create_adataset(ctx, "B")
    await DataRoi.objects.acreate(
        dataset=ds_a,
        name="LeftRect",
        x_dim="x",
        y_dim="y",
        x_min=0,
        x_max=10,
        kind=enums.RoiKindChoices.RECTANGLE.value,
    )
    await DataRoi.objects.acreate(
        dataset=ds_b,
        name="RightPoly",
        x_dim="x",
        y_dim="y",
        x_min=100,
        x_max=200,
        kind=enums.RoiKindChoices.POLYGON.value,
    )

    query = """
        query List($filters: DataRoiFilter) {
            dataRois(filters: $filters) { id name }
        }
    """

    data = await execute(ctx, query, {"kind": "RECTANGLE"})
    assert {r["name"] for r in data["dataRois"]} == {"LeftRect"}

    data = await execute(ctx, query, {"dataset": str(ds_a.id)})
    assert {r["name"] for r in data["dataRois"]} == {"LeftRect"}

    data = await execute(ctx, query, {"xMin": {"gte": 50}})
    assert {r["name"] for r in data["dataRois"]} == {"RightPoly"}

    data = await execute(ctx, query, {"search": "poly"})
    assert {r["name"] for r in data["dataRois"]} == {"RightPoly"}
