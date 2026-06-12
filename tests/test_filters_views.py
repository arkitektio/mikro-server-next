"""Filter tests for the view queries (RGBView, FileView, WellPositionView, TimepointView)."""

import pytest
from asgiref.sync import sync_to_async

from core import enums
from core.models import (
    Era,
    FileView,
    MultiWellPlate,
    RGBRenderContext,
    RGBView,
    TimepointView,
    WellPositionView,
)
from kante.context import HttpContext
from mikro_server.schema import schema

from tests.seed import create_dataset, create_file, create_image


async def execute(ctx, query, filters):
    result = await schema.execute(query, context_value=ctx, variable_values={"filters": filters})
    assert not result.errors, result.errors
    return result.data


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_rgb_view_filters(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    ds = await create_dataset(ctx, "DS")
    alpha = await create_image(ctx, "Alpha", ds)
    beta = await create_image(ctx, "Beta", ds)
    context_a = await RGBRenderContext.objects.acreate(image=alpha, name="CtxA")
    context_b = await RGBRenderContext.objects.acreate(image=beta, name="CtxB")

    view_a = await RGBView.objects.acreate(image=alpha, color_map=enums.ColorMapChoices.VIRIDIS.value, active=True)
    view_b = await RGBView.objects.acreate(image=beta, color_map=enums.ColorMapChoices.RED.value, active=False)
    await sync_to_async(view_a.contexts.add)(context_a)
    await sync_to_async(view_b.contexts.add)(context_b)

    query = """
        query List($filters: RGBViewFilter) {
            rgbViews(filters: $filters) { id }
        }
    """

    data = await execute(ctx, query, {"image": str(alpha.id)})
    assert {v["id"] for v in data["rgbViews"]} == {str(view_a.id)}

    data = await execute(ctx, query, {"contexts": [str(context_b.id)]})
    assert {v["id"] for v in data["rgbViews"]} == {str(view_b.id)}

    data = await execute(ctx, query, {"colorMap": "RED"})
    assert {v["id"] for v in data["rgbViews"]} == {str(view_b.id)}

    data = await execute(ctx, query, {"active": True})
    assert {v["id"] for v in data["rgbViews"]} == {str(view_a.id)}

    # The shared view mixin searches on the image name.
    data = await execute(ctx, query, {"search": "alph"})
    assert {v["id"] for v in data["rgbViews"]} == {str(view_a.id)}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_file_view_filters(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    ds = await create_dataset(ctx, "DS")
    img = await create_image(ctx, "Img", ds)
    file_a = await create_file(ctx, "a.tiff", ds)
    file_b = await create_file(ctx, "b.tiff", ds)
    view_a = await FileView.objects.acreate(image=img, file=file_a, series_identifier="series-1")
    view_b = await FileView.objects.acreate(image=img, file=file_b, series_identifier="series-2")

    query = """
        query List($filters: FileViewFilter) {
            fileViews(filters: $filters) { id }
        }
    """

    data = await execute(ctx, query, {"file": str(file_a.id)})
    assert {v["id"] for v in data["fileViews"]} == {str(view_a.id)}

    data = await execute(ctx, query, {"seriesIdentifier": {"exact": "series-2"}})
    assert {v["id"] for v in data["fileViews"]} == {str(view_b.id)}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_well_position_view_filters(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    ds = await create_dataset(ctx, "DS")
    img = await create_image(ctx, "Img", ds)
    plate = await MultiWellPlate.objects.acreate(name="Plate96", rows=8, columns=12)
    other_plate = await MultiWellPlate.objects.acreate(name="Plate384", rows=16, columns=24)
    view_a = await WellPositionView.objects.acreate(image=img, well=plate, row=1, column=2)
    view_b = await WellPositionView.objects.acreate(image=img, well=other_plate, row=3, column=4)

    query = """
        query List($filters: WellPositionViewFilter) {
            wellPositionViews(filters: $filters) { id }
        }
    """

    data = await execute(ctx, query, {"well": {"ids": [str(plate.id)]}})
    assert {v["id"] for v in data["wellPositionViews"]} == {str(view_a.id)}

    data = await execute(ctx, query, {"row": 3, "column": 4})
    assert {v["id"] for v in data["wellPositionViews"]} == {str(view_b.id)}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_timepoint_view_filters(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    ds = await create_dataset(ctx, "DS")
    img = await create_image(ctx, "Img", ds)
    era_a = await Era.objects.acreate(name="EraA", creator=ctx.request.user)
    era_b = await Era.objects.acreate(name="EraB", creator=ctx.request.user)
    view_a = await TimepointView.objects.acreate(image=img, era=era_a, ms_since_start=10)
    view_b = await TimepointView.objects.acreate(image=img, era=era_b, ms_since_start=2000)

    query = """
        query List($filters: TimepointViewFilter) {
            timepointViews(filters: $filters) { id }
        }
    """

    # Nested era filter resolves through the relation prefix (era__id__in).
    data = await execute(ctx, query, {"era": {"ids": [str(era_a.id)]}})
    assert {v["id"] for v in data["timepointViews"]} == {str(view_a.id)}

    data = await execute(ctx, query, {"msSinceStart": 2000})
    assert {v["id"] for v in data["timepointViews"]} == {str(view_b.id)}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_view_is_global_filter(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    ds = await create_dataset(ctx, "DS")
    img = await create_image(ctx, "Img", ds)
    era = await Era.objects.acreate(name="Era", creator=ctx.request.user)
    global_view = await TimepointView.objects.acreate(image=img, era=era, is_global=True)
    await TimepointView.objects.acreate(image=img, era=era, is_global=False)

    query = """
        query List($filters: TimepointViewFilter) {
            timepointViews(filters: $filters) { id }
        }
    """
    data = await execute(ctx, query, {"isGlobal": True})
    assert {v["id"] for v in data["timepointViews"]} == {str(global_view.id)}
