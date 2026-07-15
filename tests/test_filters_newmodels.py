"""Filter tests for the multi-dimensional data system queries
(ADataset, Scene, Layer, Lens, DataRoi)."""

import pytest
from asgiref.sync import sync_to_async

from core import enums
from core.models import ADataset, DataRoi, Layer, Lens, Scene
from kante.context import HttpContext
from mikro_server.schema import schema

from tests import seed
from tests.seed import create_other_user

# Ordered by type -- time, then channel, then space -- which RFC-5 requires.
_TCZYX = [
    seed.axis("t", enums.AxisType.TIME),
    seed.axis("c", enums.AxisType.CHANNEL),
    seed.axis("z", enums.AxisType.SPACE),
    seed.axis("y", enums.AxisType.SPACE),
    seed.axis("x", enums.AxisType.SPACE),
]


async def execute(ctx, query, filters):
    result = await schema.execute(query, context_value=ctx, variable_values={"filters": filters})
    assert not result.errors, result.errors
    return result.data


async def create_adataset(ctx, name, **kwargs):
    creator = kwargs.pop("creator", None)
    dataset = await seed.create_adataset(ctx, name, shapes=[[1, 1, 1, 100, 100]], axes=_TCZYX)
    if creator is not None or kwargs:
        for field, value in {**kwargs, **({"creator": creator} if creator is not None else {})}.items():
            setattr(dataset, field, value)
        await dataset.asave()
    return dataset


async def create_lens(dataset):
    return await Lens.objects.acreate(dataset=dataset, slices=[])


async def create_scene(ctx, name, **kwargs):
    # Scene.world is non-null: mint a bare world the same way the seed helper does.
    from core.models import CoordinateSystem

    world = await CoordinateSystem.objects.acreate(name=f"{name}/world", organization=ctx.request.organization)
    scene = await Scene.objects.acreate(name=name, world=world, organization=ctx.request.organization, **kwargs)
    world.scene = scene
    await world.asave(update_fields=["scene"])
    return scene


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
    root = await create_scene(ctx, "RootScene")
    await create_scene(ctx, "SubScene", parent=root)

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
    scene_a = await create_scene(ctx, "SceneA")
    scene_b = await create_scene(ctx, "SceneB")

    additive = await Layer.objects.acreate(
        scene=scene_a, kind=enums.LayerKindChoices.IMAGE.value, lens=lens_a, blending=enums.BlendingChoices.ADDITIVE.value
    )
    overlaid = await Layer.objects.acreate(
        scene=scene_b, kind=enums.LayerKindChoices.IMAGE.value, lens=lens_b, blending=enums.BlendingChoices.NORMAL.value
    )

    query = """
        query List($filters: LayerFilter) {
            layers(filters: $filters) { id }
        }
    """

    data = await execute(ctx, query, {"blending": "NORMAL"})
    assert {layer["id"] for layer in data["layers"]} == {str(overlaid.id)}

    data = await execute(ctx, query, {"scene": str(scene_b.id)})
    assert {layer["id"] for layer in data["layers"]} == {str(overlaid.id)}

    data = await execute(ctx, query, {"lens": str(lens_a.id)})
    assert {layer["id"] for layer in data["layers"]} == {str(additive.id)}


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
    # An ROI is drawn in a coordinate system, not "on a dataset". The `dataset`
    # filter still works -- it resolves through coordinate_system__dataset_id.
    system_a = await sync_to_async(lambda: ds_a.intrinsic_coordinate_system)()
    system_b = await sync_to_async(lambda: ds_b.intrinsic_coordinate_system)()
    await DataRoi.objects.acreate(
        coordinate_system=system_a,
        name="LeftRect",
        vectors=[[0.0, 0.0, 0.0], [0.0, 10.0, 10.0]],
        kind=enums.RoiKindChoices.RECTANGLE.value,
    )
    await DataRoi.objects.acreate(
        coordinate_system=system_b,
        name="RightPoly",
        vectors=[[0.0, 100.0, 100.0], [0.0, 200.0, 200.0]],
        kind=enums.RoiKindChoices.POLYGON.value,
    )

    query = """
        query List($filters: DataRoiFilter) {
            dataRois(filters: $filters) { id name }
        }
    """

    data = await execute(ctx, query, {"kind": "RECTANGLE"})
    assert {r["name"] for r in data["dataRois"]} == {"LeftRect"}

    # `dataset` still filters, but now through the ROI's coordinate system.
    data = await execute(ctx, query, {"dataset": str(ds_a.id)})
    assert {r["name"] for r in data["dataRois"]} == {"LeftRect"}

    data = await execute(ctx, query, {"coordinateSystem": str(system_b.id)})
    assert {r["name"] for r in data["dataRois"]} == {"RightPoly"}

    data = await execute(ctx, query, {"search": "poly"})
    assert {r["name"] for r in data["dataRois"]} == {"RightPoly"}
