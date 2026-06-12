"""Filter tests for the files and tables queries (FileFilter, TableFilter)."""

import pytest
from asgiref.sync import sync_to_async

from core.models import Table
from kante.context import HttpContext
from mikro_server.schema import schema

from tests.seed import create_dataset, create_file

FILE_QUERY = """
    query List($filters: FileFilter) {
        files(filters: $filters) { id name }
    }
"""

TABLE_QUERY = """
    query List($filters: TableFilter) {
        tables(filters: $filters) { id name }
    }
"""


async def file_names(ctx, filters):
    result = await schema.execute(FILE_QUERY, context_value=ctx, variable_values={"filters": filters})
    assert not result.errors, result.errors
    return {f["name"] for f in result.data["files"]}


async def table_names(ctx, filters):
    result = await schema.execute(TABLE_QUERY, context_value=ctx, variable_values={"filters": filters})
    assert not result.errors, result.errors
    return {t["name"] for t in result.data["tables"]}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_file_filter_by_dataset(db, authenticated_context: HttpContext):
    ds_a = await create_dataset(authenticated_context, "A")
    ds_b = await create_dataset(authenticated_context, "B")
    await create_file(authenticated_context, "InA", ds_a)
    await create_file(authenticated_context, "InB", ds_b)

    assert await file_names(authenticated_context, {"dataset": str(ds_a.id)}) == {"InA"}
    assert await file_names(authenticated_context, {"datasets": [str(ds_a.id), str(ds_b.id)]}) == {"InA", "InB"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_file_filter_by_size_and_content_type(db, authenticated_context: HttpContext):
    ds = await create_dataset(authenticated_context, "DS")
    await create_file(authenticated_context, "Small", ds, size=100, content_type="text/csv")
    await create_file(authenticated_context, "Big", ds, size=10_000, content_type="image/tiff")

    assert await file_names(authenticated_context, {"size": {"gte": 1000}}) == {"Big"}
    assert await file_names(authenticated_context, {"contentType": {"exact": "text/csv"}}) == {"Small"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_file_filter_by_not_derived(db, authenticated_context: HttpContext):
    ds = await create_dataset(authenticated_context, "DS")
    original = await create_file(authenticated_context, "Original", ds)
    derived = await create_file(authenticated_context, "Derived", ds)
    await sync_to_async(derived.origins.add)(original)

    assert await file_names(authenticated_context, {"notDerived": True}) == {"Original"}
    assert await file_names(authenticated_context, {"notDerived": False}) == {"Derived"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_file_filter_by_search(db, authenticated_context: HttpContext):
    ds = await create_dataset(authenticated_context, "DS")
    await create_file(authenticated_context, "measurements.csv", ds)
    await create_file(authenticated_context, "raw.tiff", ds)

    assert await file_names(authenticated_context, {"search": "MEASURE"}) == {"measurements.csv"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_table_filter_by_dataset_and_name(db, authenticated_context: HttpContext):
    ds_a = await create_dataset(authenticated_context, "A")
    ds_b = await create_dataset(authenticated_context, "B")
    ctx = authenticated_context
    await Table.objects.acreate(
        name="Localizations", dataset=ds_a, creator=ctx.request.user, organization=ctx.request.organization
    )
    await Table.objects.acreate(
        name="Metrics", dataset=ds_b, creator=ctx.request.user, organization=ctx.request.organization
    )

    assert await table_names(ctx, {"dataset": str(ds_a.id)}) == {"Localizations"}
    assert await table_names(ctx, {"name": {"iContains": "metric"}}) == {"Metrics"}
    assert await table_names(ctx, {"search": "Localizations"}) == {"Localizations"}
