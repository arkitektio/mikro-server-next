"""Filter tests for the images query (ImageFilter)."""

from datetime import timedelta

import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone

from core import enums
from core.models import DerivedView, ROI
from kante.context import HttpContext
from mikro_server.schema import schema

from tests.seed import create_dataset, create_image, create_other_user

QUERY = """
    query List($filters: ImageFilter) {
        images(filters: $filters) { id name }
    }
"""


async def names(ctx, filters):
    result = await schema.execute(QUERY, context_value=ctx, variable_values={"filters": filters})
    assert not result.errors, result.errors
    return {img["name"] for img in result.data["images"]}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_filter_by_kind(db, authenticated_context: HttpContext):
    ds = await create_dataset(authenticated_context, "DS")
    await create_image(authenticated_context, "Voxel", ds, kind=enums.ImageKind.VOXEL.value)
    await create_image(authenticated_context, "Mask", ds, kind=enums.ImageKind.MASK.value)

    assert await names(authenticated_context, {"kind": "VOXEL"}) == {"Voxel"}
    assert await names(authenticated_context, {"kind": "MASK"}) == {"Mask"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_filter_by_tags(db, authenticated_context: HttpContext):
    ds = await create_dataset(authenticated_context, "DS")
    tagged = await create_image(authenticated_context, "Tagged", ds)
    await create_image(authenticated_context, "Plain", ds)
    await sync_to_async(tagged.tags.add)("nucleus", "dapi")

    assert await names(authenticated_context, {"tags": ["nucleus"]}) == {"Tagged"}
    # Matching several tags of the same image must not duplicate it.
    result = await schema.execute(
        QUERY,
        context_value=authenticated_context,
        variable_values={"filters": {"tags": ["nucleus", "dapi"]}},
    )
    assert not result.errors, result.errors
    assert [img["name"] for img in result.data["images"]] == ["Tagged"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_filter_by_pinned(db, authenticated_context: HttpContext):
    ds = await create_dataset(authenticated_context, "DS")
    pinned = await create_image(authenticated_context, "Pinned", ds)
    await create_image(authenticated_context, "Unpinned", ds)
    await sync_to_async(pinned.pinned_by.add)(authenticated_context.request.user)

    assert await names(authenticated_context, {"pinned": True}) == {"Pinned"}
    assert await names(authenticated_context, {"pinned": False}) == {"Unpinned"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_filter_by_owner_and_scope(db, authenticated_context: HttpContext):
    other = await create_other_user(authenticated_context)
    ds = await create_dataset(authenticated_context, "DS")
    await create_image(authenticated_context, "Mine", ds)
    await create_image(authenticated_context, "Theirs", ds, creator=other)

    # Without any owner/scope filter both org images are visible.
    assert await names(authenticated_context, None) == {"Mine", "Theirs"}
    assert await names(authenticated_context, {"owner": "2"}) == {"Theirs"}
    assert await names(authenticated_context, {"scope": "ME"}) == {"Mine"}
    assert await names(authenticated_context, {"scope": "ORG"}) == {"Mine", "Theirs"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_filter_by_created_range(db, authenticated_context: HttpContext):
    ds = await create_dataset(authenticated_context, "DS")
    old = await create_image(authenticated_context, "Old", ds)
    await create_image(authenticated_context, "New", ds)
    from core.models import Image

    await Image.objects.filter(id=old.id).aupdate(created_at=timezone.now() - timedelta(days=10))
    cutoff = (timezone.now() - timedelta(days=5)).isoformat()

    assert await names(authenticated_context, {"createdAfter": cutoff}) == {"New"}
    assert await names(authenticated_context, {"createdBefore": cutoff}) == {"Old"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_filter_by_datasets(db, authenticated_context: HttpContext):
    ds_a = await create_dataset(authenticated_context, "A")
    ds_b = await create_dataset(authenticated_context, "B")
    ds_c = await create_dataset(authenticated_context, "C")
    await create_image(authenticated_context, "InA", ds_a)
    await create_image(authenticated_context, "InB", ds_b)
    await create_image(authenticated_context, "InC", ds_c)

    assert await names(authenticated_context, {"datasets": [str(ds_a.id), str(ds_b.id)]}) == {"InA", "InB"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_filter_by_not_derived(db, authenticated_context: HttpContext):
    ds = await create_dataset(authenticated_context, "DS")
    original = await create_image(authenticated_context, "Original", ds)
    derived = await create_image(authenticated_context, "Derived", ds)
    await DerivedView.objects.acreate(image=derived, origin_image=original, operation="max-projection")

    assert await names(authenticated_context, {"notDerived": True}) == {"Original"}
    assert await names(authenticated_context, {"notDerived": False}) == {"Derived"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_filter_by_has_rois(db, authenticated_context: HttpContext):
    ds = await create_dataset(authenticated_context, "DS")
    with_roi = await create_image(authenticated_context, "WithRoi", ds)
    await create_image(authenticated_context, "WithoutRoi", ds)
    await ROI.objects.acreate(image=with_roi, creator=authenticated_context.request.user, vectors=[])

    assert await names(authenticated_context, {"hasRois": True}) == {"WithRoi"}
    assert await names(authenticated_context, {"hasRois": False}) == {"WithoutRoi"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_filter_by_description(db, authenticated_context: HttpContext):
    ds = await create_dataset(authenticated_context, "DS")
    await create_image(authenticated_context, "First", ds, description="stained with DAPI")
    await create_image(authenticated_context, "Second", ds, description="brightfield")

    assert await names(authenticated_context, {"description": {"iContains": "dapi"}}) == {"First"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_filter_composition_or(db, authenticated_context: HttpContext):
    """The new filter API composes via AND/OR/NOT."""
    ds = await create_dataset(authenticated_context, "DS")
    await create_image(authenticated_context, "Alpha", ds)
    await create_image(authenticated_context, "Beta", ds)
    await create_image(authenticated_context, "Gamma", ds)

    filters = {
        "name": {"exact": "Alpha"},
        "OR": {"name": {"exact": "Beta"}},
    }
    assert await names(authenticated_context, filters) == {"Alpha", "Beta"}
