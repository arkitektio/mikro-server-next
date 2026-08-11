"""Cross-organization scoping: one org must not see or mutate another org's rows.

Single-object queries, mutations and subscriptions all go through
core.scoping (see that module); these tests pin the behaviour with a user
from a second organization (the "othertest" static token).
"""

from types import SimpleNamespace

import pytest
from django.core.exceptions import PermissionDenied
from kante.context import HttpContext

from core.models import Camera, Folder, Era, ROI
from core import subscriptions
from mikro_server.schema import schema
from tests.seed import create_folder, create_image


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_single_image_query_is_org_scoped(db, authenticated_context: HttpContext, other_org_context: HttpContext):
    folder = await create_folder(authenticated_context, "Org A Folder")
    image = await create_image(authenticated_context, "Org A Image", folder)

    query = """
        query($id: ID!) {
            image(id: $id) { id }
        }
    """

    mine = await schema.execute(query, variable_values={"id": str(image.pk)}, context_value=authenticated_context)
    assert mine.data, mine.errors

    other = await schema.execute(query, variable_values={"id": str(image.pk)}, context_value=other_org_context)
    assert other.errors, "a user from another organization could read the image"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_delete_folder_is_org_scoped(db, authenticated_context: HttpContext, other_org_context: HttpContext):
    folder = await create_folder(authenticated_context, "Org A Folder")

    mutation = """
        mutation($id: ID!) {
            deleteFolder(input: {id: $id})
        }
    """

    denied = await schema.execute(mutation, variable_values={"id": str(folder.pk)}, context_value=other_org_context)
    assert denied.errors, "a user from another organization could delete the folder"
    assert await Folder.objects.filter(id=folder.pk).aexists()

    allowed = await schema.execute(mutation, variable_values={"id": str(folder.pk)}, context_value=authenticated_context)
    assert not allowed.errors, allowed.errors
    assert not await Folder.objects.filter(id=folder.pk).aexists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_delete_roi_is_org_scoped(db, authenticated_context: HttpContext, other_org_context: HttpContext):
    folder = await create_folder(authenticated_context, "Org A Folder")
    image = await create_image(authenticated_context, "Org A Image", folder)
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
    folder = await create_folder(authenticated_context, "Org A Folder")
    image = await create_image(authenticated_context, "Org A Image", folder)

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
    folder = await create_folder(authenticated_context, "Org A Folder")
    image = await create_image(authenticated_context, "Org A Image", folder)

    # The resolver only touches info.context, so a thin stand-in is enough to
    # exercise the pre-join organization check without a websocket stack.
    foreign_info = SimpleNamespace(context=other_org_context)

    generator = subscriptions.rois(None, foreign_info, image=str(image.id))
    with pytest.raises(PermissionDenied):
        await anext(generator)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_pin_folder_toggles_and_is_org_scoped(db, authenticated_context: HttpContext, other_org_context: HttpContext):
    folder = await create_folder(authenticated_context, "Org A Folder")

    mutation = """
        mutation($id: ID!, $pin: Boolean!) {
            pinFolder(input: {id: $id, pin: $pin}) { id }
        }
    """

    pinned = await schema.execute(mutation, variable_values={"id": str(folder.id), "pin": True}, context_value=authenticated_context)
    assert not pinned.errors, pinned.errors
    assert await folder.pinned_by.acount() == 1

    unpinned = await schema.execute(mutation, variable_values={"id": str(folder.id), "pin": False}, context_value=authenticated_context)
    assert not unpinned.errors, unpinned.errors
    assert await folder.pinned_by.acount() == 0

    denied = await schema.execute(mutation, variable_values={"id": str(folder.id), "pin": True}, context_value=other_org_context)
    assert denied.errors, "a user from another organization could pin the folder"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_pin_camera_toggles_and_is_org_scoped(db, authenticated_context: HttpContext, other_org_context: HttpContext):
    """pin_camera was a NotImplementedError stub until the pinned_by field was added."""
    camera = await Camera.objects.acreate(
        serial_number="cam-org-a",
        name="Org A Camera",
        organization=authenticated_context.request.organization,
    )

    mutation = """
        mutation($id: ID!, $pin: Boolean!) {
            pinCamera(input: {id: $id, pin: $pin}) { id }
        }
    """

    pinned = await schema.execute(mutation, variable_values={"id": str(camera.id), "pin": True}, context_value=authenticated_context)
    assert not pinned.errors, pinned.errors
    assert await camera.pinned_by.acount() == 1

    unpinned = await schema.execute(mutation, variable_values={"id": str(camera.id), "pin": False}, context_value=authenticated_context)
    assert not unpinned.errors, unpinned.errors
    assert await camera.pinned_by.acount() == 0

    denied = await schema.execute(mutation, variable_values={"id": str(camera.id), "pin": True}, context_value=other_org_context)
    assert denied.errors, "a user from another organization could pin the camera"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_delete_era_is_org_scoped(db, authenticated_context: HttpContext, other_org_context: HttpContext):
    """Era only recently grew an organization FK — pin that it is enforced."""
    era = await Era.objects.acreate(name="Org A Era", organization=authenticated_context.request.organization)

    mutation = """
        mutation($id: ID!) {
            deleteEra(input: {id: $id})
        }
    """

    denied = await schema.execute(mutation, variable_values={"id": str(era.id)}, context_value=other_org_context)
    assert denied.errors, "a user from another organization could delete the era"
    assert await Era.objects.filter(id=era.id).aexists()

    allowed = await schema.execute(mutation, variable_values={"id": str(era.id)}, context_value=authenticated_context)
    assert not allowed.errors, allowed.errors
    assert not await Era.objects.filter(id=era.id).aexists()
