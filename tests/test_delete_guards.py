"""Ownership guards on delete mutations.

Deletion of user-owned rows is guarded (``core.mutations._generic``): a caller
may delete a row only if they are its ``creator`` or its ``created_through_by``
assigner, unless they hold the ``admin`` role in the organization.

Because every static test token defaults to ``roles=["admin"]``, the denial
path is exercised through ``bot_context`` — a same-org user holding only the
``bot`` role, which passes the admin/bot mutation gate but is not an admin, so
the guard applies to it.
"""

import pytest

from core import models
from kante.context import HttpContext
from mikro_server.schema import schema
from tests import seed
from tests.seed import create_dataset, create_image, create_other_user


# --- creator / assignee / admin guard on a self-owned model (Dataset) --------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_creator_can_delete_own_dataset(db, authenticated_context: HttpContext):
    dataset = await create_dataset(authenticated_context, "Mine")

    mutation = "mutation($id: ID!) { deleteDataset(input: {id: $id}) }"
    result = await schema.execute(mutation, variable_values={"id": str(dataset.pk)}, context_value=authenticated_context)

    assert not result.errors, result.errors
    assert not await models.Dataset.objects.filter(id=dataset.pk).aexists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_non_owner_non_admin_cannot_delete_dataset(db, authenticated_context: HttpContext, bot_context: HttpContext):
    # Owned by the admin user (sub 1); the bot user (sub 2, same org) is neither
    # creator nor assignee nor admin.
    dataset = await create_dataset(authenticated_context, "NotYours")

    mutation = "mutation($id: ID!) { deleteDataset(input: {id: $id}) }"
    denied = await schema.execute(mutation, variable_values={"id": str(dataset.pk)}, context_value=bot_context)

    assert denied.errors, "a non-owner non-admin user could delete the dataset"
    assert await models.Dataset.objects.filter(id=dataset.pk).aexists()

    # The creator can still delete it.
    allowed = await schema.execute(mutation, variable_values={"id": str(dataset.pk)}, context_value=authenticated_context)
    assert not allowed.errors, allowed.errors
    assert not await models.Dataset.objects.filter(id=dataset.pk).aexists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_org_admin_can_delete_other_users_dataset(db, authenticated_context: HttpContext):
    # Created by a second user (sub 2); deleted by the admin user (sub 1).
    bot_user = await create_other_user(authenticated_context)
    dataset = await create_dataset(authenticated_context, "BotsDataset", creator=bot_user)

    mutation = "mutation($id: ID!) { deleteDataset(input: {id: $id}) }"
    result = await schema.execute(mutation, variable_values={"id": str(dataset.pk)}, context_value=authenticated_context)

    assert not result.errors, result.errors
    assert not await models.Dataset.objects.filter(id=dataset.pk).aexists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_assignee_can_delete_dataset(db, authenticated_context: HttpContext, bot_context: HttpContext):
    # Creator is the admin user, but the bot user is the assigner
    # (created_through_by): the assignee path lets the bot delete it.
    bot_user = await create_other_user(authenticated_context)
    dataset = await create_dataset(authenticated_context, "Assigned", created_through_by=bot_user)

    mutation = "mutation($id: ID!) { deleteDataset(input: {id: $id}) }"
    result = await schema.execute(mutation, variable_values={"id": str(dataset.pk)}, context_value=bot_context)

    assert not result.errors, result.errors
    assert not await models.Dataset.objects.filter(id=dataset.pk).aexists()


# --- guard inherited from the parent image (views) ---------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_view_delete_guarded_by_parent_image(db, authenticated_context: HttpContext, bot_context: HttpContext):
    dataset = await create_dataset(authenticated_context, "DS")
    image = await create_image(authenticated_context, "Img", dataset)
    view = await models.ChannelView.objects.acreate(image=image, name="DAPI")

    mutation = "mutation($id: ID!) { deleteChannelView(input: {id: $id}) }"

    denied = await schema.execute(mutation, variable_values={"id": str(view.pk)}, context_value=bot_context)
    assert denied.errors, "a non-owner deleted a view of someone else's image"
    assert await models.ChannelView.objects.filter(id=view.pk).aexists()

    allowed = await schema.execute(mutation, variable_values={"id": str(view.pk)}, context_value=authenticated_context)
    assert not allowed.errors, allowed.errors
    assert not await models.ChannelView.objects.filter(id=view.pk).aexists()


# --- newly added delete mutations (wired + delete) ---------------------------


async def _seed_adataset(ctx: HttpContext, *, creator=None) -> models.ADataset:
    dataset = await seed.create_adataset(ctx, "ADS", shapes=[[1, 32, 32]])
    if creator is None:
        dataset.creator = None
        await dataset.asave(update_fields=["creator"])
    return dataset


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_delete_adataset(db, authenticated_context: HttpContext):
    adataset = await _seed_adataset(authenticated_context, creator=authenticated_context.request.user)

    mutation = "mutation($id: ID!) { deleteAdataset(input: {id: $id}) }"
    result = await schema.execute(mutation, variable_values={"id": str(adataset.pk)}, context_value=authenticated_context)

    assert not result.errors, result.errors
    assert not await models.ADataset.objects.filter(id=adataset.pk).aexists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_delete_adataset_denied_for_non_owner(db, authenticated_context: HttpContext, bot_context: HttpContext):
    adataset = await _seed_adataset(authenticated_context, creator=authenticated_context.request.user)

    mutation = "mutation($id: ID!) { deleteAdataset(input: {id: $id}) }"
    denied = await schema.execute(mutation, variable_values={"id": str(adataset.pk)}, context_value=bot_context)

    assert denied.errors, "a non-owner non-admin user could delete the array dataset"
    assert await models.ADataset.objects.filter(id=adataset.pk).aexists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_delete_data_array(db, authenticated_context: HttpContext):
    adataset = await _seed_adataset(authenticated_context, creator=authenticated_context.request.user)
    # Level 1, not 0: the seed already created level 0, and (dataset, level) is
    # unique -- two arrays claiming the same level would make "the level-0 array"
    # ambiguous everywhere.
    data_array = await models.DataArray.objects.acreate(
        level=1, dataset=adataset, shape=[1, 32, 32], chunk_shape=[1, 32, 32]
    )

    mutation = "mutation($id: ID!) { deleteDataArray(input: {id: $id}) }"
    result = await schema.execute(mutation, variable_values={"id": str(data_array.pk)}, context_value=authenticated_context)

    assert not result.errors, result.errors
    assert not await models.DataArray.objects.filter(id=data_array.pk).aexists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_delete_lens(db, authenticated_context: HttpContext):
    adataset = await _seed_adataset(authenticated_context, creator=authenticated_context.request.user)
    lens = await models.Lens.objects.acreate(dataset=adataset, slices=[])

    mutation = "mutation($id: ID!) { deleteLens(input: {id: $id}) }"
    result = await schema.execute(mutation, variable_values={"id": str(lens.pk)}, context_value=authenticated_context)

    assert not result.errors, result.errors
    assert not await models.Lens.objects.filter(id=lens.pk).aexists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_delete_scene(db, authenticated_context: HttpContext):
    scene = await seed.create_scene(authenticated_context)

    mutation = "mutation($id: ID!) { deleteScene(input: {id: $id}) }"
    result = await schema.execute(mutation, variable_values={"id": str(scene.pk)}, context_value=authenticated_context)

    assert not result.errors, result.errors
    assert not await models.Scene.objects.filter(id=scene.pk).aexists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_delete_layer(db, authenticated_context: HttpContext):
    scene = await seed.create_scene(authenticated_context)
    layer = await models.Layer.objects.acreate(scene=scene)

    mutation = "mutation($id: ID!) { deleteLayer(input: {id: $id}) }"
    result = await schema.execute(mutation, variable_values={"id": str(layer.pk)}, context_value=authenticated_context)

    assert not result.errors, result.errors
    assert not await models.Layer.objects.filter(id=layer.pk).aexists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_delete_render_tree(db, authenticated_context: HttpContext):
    tree = await models.RenderTree.objects.acreate(
        name="Tree", tree={}, organization=authenticated_context.request.organization,
    )

    mutation = "mutation($id: ID!) { deleteRenderTree(input: {id: $id}) }"
    result = await schema.execute(mutation, variable_values={"id": str(tree.pk)}, context_value=authenticated_context)

    assert not result.errors, result.errors
    assert not await models.RenderTree.objects.filter(id=tree.pk).aexists()
