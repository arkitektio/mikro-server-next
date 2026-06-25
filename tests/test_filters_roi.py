"""Filter tests for the rois query (ROIFilter)."""

import pytest
from asgiref.sync import sync_to_async

from core import enums
from core.models import ROI
from kante.context import HttpContext
from mikro_server.schema import schema

from tests.seed import create_dataset, create_image

QUERY = """
    query List($filters: ROIFilter) {
        rois(filters: $filters) { id }
    }
"""


async def roi_ids(ctx, filters):
    result = await schema.execute(QUERY, context_value=ctx, variable_values={"filters": filters})
    assert not result.errors, result.errors
    return {r["id"] for r in result.data["rois"]}


async def create_roi(ctx, image, **kwargs):
    return await ROI.objects.acreate(
        image=image,
        creator=ctx.request.user,
        vectors=kwargs.pop("vectors", []),
        **kwargs,
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_filter_by_kind(db, authenticated_context: HttpContext):
    ds = await create_dataset(authenticated_context, "DS")
    img = await create_image(authenticated_context, "Img", ds)
    rect = await create_roi(authenticated_context, img, kind=enums.RoiKindChoices.RECTANGLE.value)
    await create_roi(authenticated_context, img, kind=enums.RoiKindChoices.POLYGON.value)

    assert await roi_ids(authenticated_context, {"kind": "RECTANGLE"}) == {str(rect.id)}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_filter_by_image_and_images(db, authenticated_context: HttpContext):
    ds = await create_dataset(authenticated_context, "DS")
    img_a = await create_image(authenticated_context, "A", ds)
    img_b = await create_image(authenticated_context, "B", ds)
    img_c = await create_image(authenticated_context, "C", ds)
    on_a = await create_roi(authenticated_context, img_a)
    on_b = await create_roi(authenticated_context, img_b)
    await create_roi(authenticated_context, img_c)

    assert await roi_ids(authenticated_context, {"image": str(img_a.id)}) == {str(on_a.id)}
    assert await roi_ids(authenticated_context, {"images": [str(img_a.id), str(img_b.id)]}) == {
        str(on_a.id),
        str(on_b.id),
    }


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_filter_by_label_lookup(db, authenticated_context: HttpContext):
    ds = await create_dataset(authenticated_context, "DS")
    img = await create_image(authenticated_context, "Img", ds)
    cell = await create_roi(authenticated_context, img, label="cell-1")
    await create_roi(authenticated_context, img, label="nucleus-1")

    assert await roi_ids(authenticated_context, {"label": {"startsWith": "cell"}}) == {str(cell.id)}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_filter_by_bbox(db, authenticated_context: HttpContext):
    ds = await create_dataset(authenticated_context, "DS")
    img = await create_image(authenticated_context, "Img", ds)
    left = await create_roi(authenticated_context, img, min_x=0, max_x=10)
    right = await create_roi(authenticated_context, img, min_x=100, max_x=200)

    assert await roi_ids(authenticated_context, {"minX": {"gte": 50}}) == {str(right.id)}
    assert await roi_ids(authenticated_context, {"maxX": {"lte": 50}}) == {str(left.id)}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_filter_by_pinned_and_search(db, authenticated_context: HttpContext):
    ds = await create_dataset(authenticated_context, "DS")
    alpha = await create_image(authenticated_context, "Alpha", ds)
    beta = await create_image(authenticated_context, "Beta", ds)
    pinned = await create_roi(authenticated_context, alpha)
    await create_roi(authenticated_context, beta)
    await sync_to_async(pinned.pinned_by.add)(authenticated_context.request.user)

    assert await roi_ids(authenticated_context, {"pinned": True}) == {str(pinned.id)}
    # ROI search matches on the image name (case-insensitive).
    assert await roi_ids(authenticated_context, {"search": "alpha"}) == {str(pinned.id)}
