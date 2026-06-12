"""Regression and parity tests for view creation.

The standalone ``create*View`` mutations and the bulk ``fromArrayLike`` path
share one implementation in ``core.logic.views``; these tests pin the bugs the
old duplicated code had (``createTimepointView`` crashed whenever ``era`` was
set, ``createChannelView`` read a nonexistent ``channel`` field,
``createRgbView`` passed the many-to-many ``contexts`` as a create kwarg) and
assert the two paths produce equivalent rows.
"""

import pytest

from asgiref.sync import sync_to_async
from core.models import (
    ChannelView,
    Dataset,
    Era,
    Image,
    RGBRenderContext,
    Stage,
    TimepointView,
)
from kante.context import HttpContext
from mikro_server.schema import schema


async def _seed_image(ctx: HttpContext, name: str) -> Image:
    dataset = await Dataset.objects.acreate(
        name=f"DS for {name}",
        creator=ctx.request.user,
        organization=ctx.request.organization,  # type: ignore[arg-type]
        membership=ctx.request.membership,  # type: ignore[arg-type]
    )
    return await Image.objects.acreate(
        name=name,
        dataset=dataset,
        creator=ctx.request.user,
        organization=ctx.request.organization,  # type: ignore[arg-type]
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_timepoint_view_with_existing_era(db, authenticated_context: HttpContext):
    """Regression: this crashed reading ``input.fluorophore`` whenever era was set."""
    image = await _seed_image(authenticated_context, "Timepointed")
    era = await Era.objects.acreate(name="My Era", organization=authenticated_context.request.organization)

    mutation = """
        mutation Create($input: TimepointViewInput!) {
            createTimepointView(input: $input) { id era { id name } msSinceStart }
        }
    """
    result = await schema.execute(
        mutation,
        context_value=authenticated_context,
        variable_values={"input": {"image": str(image.id), "era": str(era.id), "msSinceStart": 1500}},
    )

    assert not result.errors, result.errors
    assert result.data["createTimepointView"]["era"]["id"] == str(era.id)
    view = await TimepointView.objects.select_related("era").aget(id=result.data["createTimepointView"]["id"])
    assert view.ms_since_start == 1500


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_timepoint_view_creates_fallback_era(db, authenticated_context: HttpContext):
    """Without an era, an organization-stamped fallback Era is auto-created."""
    image = await _seed_image(authenticated_context, "Timepointed")

    mutation = """
        mutation Create($input: TimepointViewInput!) {
            createTimepointView(input: $input) { id era { id name } }
        }
    """
    result = await schema.execute(
        mutation,
        context_value=authenticated_context,
        variable_values={"input": {"image": str(image.id)}},
    )

    assert not result.errors, result.errors
    era = await Era.objects.aget(id=result.data["createTimepointView"]["era"]["id"])
    assert era.organization_id == authenticated_context.request.organization.id


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_channel_view(db, authenticated_context: HttpContext):
    """Regression: this crashed reading the nonexistent ``input.channel`` field."""
    image = await _seed_image(authenticated_context, "Channeled")

    mutation = """
        mutation Create($input: ChannelViewInput!) {
            createChannelView(input: $input) { id name excitationWavelength }
        }
    """
    result = await schema.execute(
        mutation,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "image": str(image.id),
                "name": "DAPI",
                "excitationWavelength": 405.0,
                "emissionWavelength": 461.0,
                "cMin": 0,
                "cMax": 1,
            }
        },
    )

    assert not result.errors, result.errors
    view = await ChannelView.objects.aget(id=result.data["createChannelView"]["id"])
    assert view.name == "DAPI"
    assert view.excitation_wavelength == 405.0
    assert view.c_min == 0 and view.c_max == 1
    assert view.is_global is False


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_rgb_view_attaches_to_context(db, authenticated_context: HttpContext):
    """Regression: this crashed passing the ``contexts`` many-to-many as a create kwarg."""
    image = await _seed_image(authenticated_context, "Rendered")
    context = await RGBRenderContext.objects.acreate(name="Ctx", image=image)

    mutation = """
        mutation Create($input: RGBViewInput!) {
            createRgbView(input: $input) { id }
        }
    """
    result = await schema.execute(
        mutation,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "image": str(image.id),
                "context": str(context.id),
                "colorMap": "RED",
                "cMin": 0,
                "cMax": 1,
            }
        },
    )

    assert not result.errors, result.errors
    view_ids = await sync_to_async(lambda: list(context.views.values_list("id", flat=True)))()
    assert view_ids == [int(result.data["createRgbView"]["id"])]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_affine_transformation_view_creates_fallback_stage(db, authenticated_context: HttpContext):
    """Without a stage, an organization-stamped fallback Stage is auto-created (parity with the bulk path)."""
    image = await _seed_image(authenticated_context, "Transformed")

    mutation = """
        mutation Create($input: AffineTransformationViewInput!) {
            createAffineTransformationView(input: $input) { id stage { id } }
        }
    """
    matrix = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    result = await schema.execute(
        mutation,
        context_value=authenticated_context,
        variable_values={"input": {"image": str(image.id), "affineMatrix": matrix}},
    )

    assert not result.errors, result.errors
    stage = await Stage.objects.aget(id=result.data["createAffineTransformationView"]["stage"]["id"])
    assert stage.organization_id == authenticated_context.request.organization.id


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_bulk_and_single_channel_view_parity(db, authenticated_context: HttpContext):
    """The bulk fromArrayLike path and createChannelView produce equivalent rows."""
    from unittest.mock import patch

    from datalayer.models import ZarrStore

    store = await ZarrStore.objects.acreate(
        organization=authenticated_context.request.organization,
        key="parity-zarr",
        bucket="zarr",
        shape=[1, 1, 1, 64, 64],
        chunks=[1, 1, 1, 64, 64],
        version="3",
        dtype="uint8",
        populated=True,
    )

    channel_input = {
        "name": "GFP",
        "excitationWavelength": 488.0,
        "emissionWavelength": 507.0,
        "cMin": 0,
        "cMax": 1,
    }

    bulk = """
        mutation Create($input: FromArrayLikeInput!) {
            fromArrayLike(input: $input) { id }
        }
    """
    with patch("datalayer.models.ZarrStore.fill_info", return_value=None):
        result = await schema.execute(
            bulk,
            context_value=authenticated_context,
            variable_values={"input": {"array": str(store.id), "name": "Bulk", "channelViews": [channel_input]}},
        )
    assert not result.errors, result.errors
    bulk_view = await ChannelView.objects.aget(image_id=result.data["fromArrayLike"]["id"])

    image = await _seed_image(authenticated_context, "Single")
    single = """
        mutation Create($input: ChannelViewInput!) {
            createChannelView(input: $input) { id }
        }
    """
    result = await schema.execute(
        single,
        context_value=authenticated_context,
        variable_values={"input": {"image": str(image.id), **channel_input}},
    )
    assert not result.errors, result.errors
    single_view = await ChannelView.objects.aget(id=result.data["createChannelView"]["id"])

    for field in ("name", "excitation_wavelength", "emission_wavelength", "acquisition_mode", "c_min", "c_max", "is_global", "collection_id"):
        assert getattr(bulk_view, field) == getattr(single_view, field), field
