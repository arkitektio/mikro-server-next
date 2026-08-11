"""Filter tests for acquisition-context and render queries
(Stage, Era, Instrument, Snapshot)."""

import pytest

from core.models import Era, Instrument, RGBRenderContext, Snapshot, Stage
from kante.context import HttpContext
from mikro_server.schema import schema

from tests.seed import create_folder, create_image


async def execute(ctx, query, filters):
    result = await schema.execute(query, context_value=ctx, variable_values={"filters": filters})
    assert not result.errors, result.errors
    return result.data


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_stage_filter_by_instrument_and_search(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    scope = await Instrument.objects.acreate(
        name="Confocal", serial_number="SN-1", organization=ctx.request.organization
    )
    other = await Instrument.objects.acreate(
        name="Widefield", serial_number="SN-2", organization=ctx.request.organization
    )
    await Stage.objects.acreate(
        name="StageOne", kind="xyz", instrument=scope, creator=ctx.request.user, organization=ctx.request.organization
    )
    await Stage.objects.acreate(
        name="StageTwo", kind="xyz", instrument=other, creator=ctx.request.user, organization=ctx.request.organization
    )

    query = """
        query List($filters: StageFilter) {
            stages(filters: $filters) { id name }
        }
    """
    data = await execute(ctx, query, {"instrument": str(scope.id)})
    assert {s["name"] for s in data["stages"]} == {"StageOne"}

    data = await execute(ctx, query, {"search": "two"})
    assert {s["name"] for s in data["stages"]} == {"StageTwo"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_era_filter_by_instrument(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    scope = await Instrument.objects.acreate(
        name="Confocal", serial_number="SN-1", organization=ctx.request.organization
    )
    await Era.objects.acreate(name="WithScope", instrument=scope, creator=ctx.request.user, organization=ctx.request.organization)
    await Era.objects.acreate(name="NoScope", creator=ctx.request.user, organization=ctx.request.organization)

    query = """
        query List($filters: EraFilter) {
            eras(filters: $filters) { id name }
        }
    """
    data = await execute(ctx, query, {"instrument": str(scope.id)})
    assert {e["name"] for e in data["eras"]} == {"WithScope"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_instrument_filter_lookups(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    await Instrument.objects.acreate(
        name="Confocal", manufacturer="Zeiss", serial_number="SN-1", organization=ctx.request.organization
    )
    await Instrument.objects.acreate(
        name="Widefield", manufacturer="Nikon", serial_number="SN-2", organization=ctx.request.organization
    )

    query = """
        query List($filters: InstrumentFilter) {
            instruments(filters: $filters) { id name }
        }
    """
    data = await execute(ctx, query, {"manufacturer": {"iExact": "zeiss"}})
    assert {i["name"] for i in data["instruments"]} == {"Confocal"}

    data = await execute(ctx, query, {"serialNumber": {"exact": "SN-2"}})
    assert {i["name"] for i in data["instruments"]} == {"Widefield"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_snapshot_filter_by_image_and_context(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    ds = await create_folder(ctx, "DS")
    alpha = await create_image(ctx, "Alpha", ds)
    beta = await create_image(ctx, "Beta", ds)
    rgb_context = await RGBRenderContext.objects.acreate(image=alpha, name="Ctx")
    await Snapshot.objects.acreate(name="OfAlpha", image=alpha, context=rgb_context, creator=ctx.request.user)
    await Snapshot.objects.acreate(name="OfBeta", image=beta, creator=ctx.request.user)

    query = """
        query List($filters: SnapshotFilter) {
            snapshots(filters: $filters) { id name }
        }
    """
    data = await execute(ctx, query, {"image": str(alpha.id)})
    assert {s["name"] for s in data["snapshots"]} == {"OfAlpha"}

    data = await execute(ctx, query, {"context": str(rgb_context.id)})
    assert {s["name"] for s in data["snapshots"]} == {"OfAlpha"}

    data = await execute(ctx, query, {"search": "beta"})
    assert {s["name"] for s in data["snapshots"]} == {"OfBeta"}

