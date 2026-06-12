"""Cross-organization scoping: one org must not see or mutate another org's rows.

Single-object queries, mutations and subscriptions all go through
core.scoping (see that module); these tests pin the behaviour with a user
from a second organization (the "othertest" static token).
"""

from types import SimpleNamespace

import pytest
from django.core.exceptions import PermissionDenied
from kante.context import HttpContext

from core.models import Dataset, ROI
from core import subscriptions
from mikro_server.schema import schema
from tests.seed import create_dataset, create_image


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_single_image_query_is_org_scoped(db, authenticated_context: HttpContext, other_org_context: HttpContext):
    dataset = await create_dataset(authenticated_context, "Org A Dataset")
    image = await create_image(authenticated_context, "Org A Image", dataset)

    query = """
        query($id: ID!) {
            image(id: $id) { id }
        }
    """

    mine = await schema.execute(query, variable_values={"id": str(image.id)}, context_value=authenticated_context)
    assert mine.data, mine.errors

    other = await schema.execute(query, variable_values={"id": str(image.id)}, context_value=other_org_context)
    assert other.errors, "a user from another organization could read the image"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_delete_dataset_is_org_scoped(db, authenticated_context: HttpContext, other_org_context: HttpContext):
    dataset = await create_dataset(authenticated_context, "Org A Dataset")

    mutation = """
        mutation($id: ID!) {
            deleteDataset(input: {id: $id})
        }
    """

    denied = await schema.execute(mutation, variable_values={"id": str(dataset.id)}, context_value=other_org_context)
    assert denied.errors, "a user from another organization could delete the dataset"
    assert await Dataset.objects.filter(id=dataset.id).aexists()

    allowed = await schema.execute(mutation, variable_values={"id": str(dataset.id)}, context_value=authenticated_context)
    assert not allowed.errors, allowed.errors
    assert not await Dataset.objects.filter(id=dataset.id).aexists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_delete_roi_is_org_scoped(db, authenticated_context: HttpContext, other_org_context: HttpContext):
    dataset = await create_dataset(authenticated_context, "Org A Dataset")
    image = await create_image(authenticated_context, "Org A Image", dataset)
    roi = await ROI.objects.acreate(image=image, vectors=[], creator=authenticated_context.request.user)

    mutation = """
        mutation($id: ID!) {
            deleteRoi(input: {id: $id})
        }
    """

    denied = await schema.execute(mutation, variable_values={"id": str(roi.id)}, context_value=other_org_context)
    assert denied.errors, "a user from another organization could delete the ROI"
    assert await ROI.objects.filter(id=roi.id).aexists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_roi_on_foreign_image_denied(db, authenticated_context: HttpContext, other_org_context: HttpContext):
    dataset = await create_dataset(authenticated_context, "Org A Dataset")
    image = await create_image(authenticated_context, "Org A Image", dataset)

    mutation = """
        mutation($image: ID!) {
            createRoi(input: {image: $image, vectors: [], kind: RECTANGLE}) { id }
        }
    """

    denied = await schema.execute(mutation, variable_values={"image": str(image.id)}, context_value=other_org_context)
    assert denied.errors, "a user from another organization could attach a ROI to the image"
    assert not await ROI.objects.filter(image=image).aexists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_roi_subscription_denies_foreign_image(db, authenticated_context: HttpContext, other_org_context: HttpContext):
    dataset = await create_dataset(authenticated_context, "Org A Dataset")
    image = await create_image(authenticated_context, "Org A Image", dataset)

    # The resolver only touches info.context, so a thin stand-in is enough to
    # exercise the pre-join organization check without a websocket stack.
    foreign_info = SimpleNamespace(context=other_org_context)

    generator = subscriptions.rois(None, foreign_info, image=str(image.id))
    with pytest.raises(PermissionDenied):
        await anext(generator)
