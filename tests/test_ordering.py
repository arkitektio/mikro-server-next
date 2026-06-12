"""Ordering tests for the new order_type classes (ordering: [XOrder!] argument)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import FileView, Image, RenderTree
from kante.context import HttpContext
from mikro_server.schema import schema

from tests.seed import create_dataset, create_file, create_image


async def execute(ctx, query, ordering):
    result = await schema.execute(query, context_value=ctx, variable_values={"ordering": ordering})
    assert not result.errors, result.errors
    return result.data


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_images_order_by_created_at(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    ds = await create_dataset(ctx, "DS")
    first = await create_image(ctx, "First", ds)
    await create_image(ctx, "Second", ds)
    await Image.objects.filter(id=first.id).aupdate(created_at=timezone.now() - timedelta(days=1))

    query = """
        query List($ordering: [ImageOrder!]!) {
            images(ordering: $ordering) { name }
        }
    """
    data = await execute(ctx, query, [{"createdAt": "DESC"}])
    assert [img["name"] for img in data["images"]] == ["Second", "First"]

    data = await execute(ctx, query, [{"createdAt": "ASC"}])
    assert [img["name"] for img in data["images"]] == ["First", "Second"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_images_order_by_name(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    ds = await create_dataset(ctx, "DS")
    for name in ["Charlie", "Alpha", "Bravo"]:
        await create_image(ctx, name, ds)

    query = """
        query List($ordering: [ImageOrder!]!) {
            images(ordering: $ordering) { name }
        }
    """
    data = await execute(ctx, query, [{"name": "ASC"}])
    assert [img["name"] for img in data["images"]] == ["Alpha", "Bravo", "Charlie"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_files_order_by_size_then_name(db, authenticated_context: HttpContext):
    """Multiple ordering keys apply in list order."""
    ctx = authenticated_context
    ds = await create_dataset(ctx, "DS")
    await create_file(ctx, "b.bin", ds, size=100)
    await create_file(ctx, "a.bin", ds, size=100)
    await create_file(ctx, "big.bin", ds, size=900)

    query = """
        query List($ordering: [FileOrder!]!) {
            files(ordering: $ordering) { name }
        }
    """
    data = await execute(ctx, query, [{"size": "DESC"}, {"name": "ASC"}])
    assert [f["name"] for f in data["files"]] == ["big.bin", "a.bin", "b.bin"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_datasets_order_by_name(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    for name in ["Zeta", "Alpha", "Mid"]:
        await create_dataset(ctx, name)

    query = """
        query List($ordering: [DatasetOrder!]!) {
            datasets(ordering: $ordering) { name }
        }
    """
    data = await execute(ctx, query, [{"name": "DESC"}])
    assert [d["name"] for d in data["datasets"]] == ["Zeta", "Mid", "Alpha"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_render_trees_order_by_name(db, authenticated_context: HttpContext):
    """RenderTreeOrder previously ordered on a nonexistent created_at field."""
    ctx = authenticated_context
    await RenderTree.objects.acreate(name="TreeB", tree={}, organization=ctx.request.organization)
    await RenderTree.objects.acreate(name="TreeA", tree={}, organization=ctx.request.organization)

    query = """
        query List($ordering: [RenderTreeOrder!]!) {
            renderTrees(ordering: $ordering) { name }
        }
    """
    data = await execute(ctx, query, [{"name": "ASC"}])
    assert [t["name"] for t in data["renderTrees"]] == ["TreeA", "TreeB"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_file_views_order_by_id(db, authenticated_context: HttpContext):
    """FileViewOrder previously ordered on a nonexistent created_at field."""
    ctx = authenticated_context
    ds = await create_dataset(ctx, "DS")
    img = await create_image(ctx, "Img", ds)
    file = await create_file(ctx, "f.tiff", ds)
    first = await FileView.objects.acreate(image=img, file=file)
    second = await FileView.objects.acreate(image=img, file=file)

    query = """
        query List($ordering: [FileViewOrder!]!) {
            fileViews(ordering: $ordering) { id }
        }
    """
    data = await execute(ctx, query, [{"id": "DESC"}])
    assert [v["id"] for v in data["fileViews"]] == [str(second.id), str(first.id)]
