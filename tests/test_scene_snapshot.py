"""A snapshot is a picture of a composition, and it belongs to the scene it depicts.

There is no picture of a dataset -- only pictures of scenes. A dataset can still be
previewed from one, but only where the scene's *only* placed dataset is that dataset,
because then the picture shows it and nothing else. That rule (`sole occupancy`) is what
these pin hardest: without it `latestSnapshot` quietly becomes "some composition this
appears in", which is a tile showing mostly other people's data.

These also pin the three places this deliberately departs from the legacy `Snapshot` it
mirrors, each of which is a live bug there: the row records its creator (so the delete
guard has someone to match), the store is non-null (so the non-null `store` field cannot
fail at runtime), and the list query is organization-scoped (so it cannot serve another
org's thumbnails).
"""

import pytest
from asgiref.sync import sync_to_async
from kante.context import HttpContext

from core import models
from datalayer.models import MediaStore
from mikro_server.schema import schema
from tests import seed

CREATE = """
mutation Create($input: SceneSnapshotInput!) {
  createSceneSnapshot(input: $input) {
    id
    name
    scene { id }
    store { id }
  }
}
"""

DELETE = """
mutation Delete($input: DeleteSceneSnapshotInput!) {
  deleteSceneSnapshot(input: $input)
}
"""

PIN = """
mutation Pin($input: PinSceneSnapshotInput!) {
  pinSceneSnapshot(input: $input) { id }
}
"""

LIST = """
query List($filters: SceneSnapshotFilter) {
  sceneSnapshots(filters: $filters) { id name }
}
"""

LATEST = """
query Latest($dataset: ID!, $lens: ID!, $scene: ID!) {
  adataset(id: $dataset) { latestSnapshot { name } }
  lens(id: $lens) { latestSnapshot { name } }
  scene(id: $scene) { latestSnapshot { name } }
}
"""


async def _media_store(ctx: HttpContext, key: str) -> MediaStore:
    """A populated media store, as `finishMediaUpload` would leave it."""
    return await MediaStore.objects.acreate(
        organization=ctx.request.organization,
        path=f"s3://media/{key}",
        key=key,
        bucket="media",
        content_type="image/png",
        populated=True,
    )


async def _snapshot(ctx: HttpContext, scene, key: str, name=None):
    store = await _media_store(ctx, key)
    payload = {"file": str(store.pk), "scene": str(scene.pk)}
    if name is not None:
        payload["name"] = name
    result = await schema.execute(CREATE, context_value=ctx, variable_values={"input": payload})
    assert not result.errors, result.errors
    return result.data["createSceneSnapshot"]


async def _names(ctx: HttpContext, filters: dict) -> set[str]:
    result = await schema.execute(LIST, context_value=ctx, variable_values={"filters": filters})
    assert not result.errors, result.errors
    return {row["name"] for row in result.data["sceneSnapshots"]}


async def _latest(ctx: HttpContext, dataset, lens, scene):
    """(adataset.latestSnapshot, lens.latestSnapshot, scene.latestSnapshot) names, or None.

    The sole-occupancy map is per-request state, cached on the context's loader store
    because building it walks the placement graph once per scene. Production builds a
    fresh HttpContext per request; this fixture hands the *same* one to every execute(),
    so the store is dropped here to make each call a real request. Without this a test
    that changes placement between two calls would read the first call's map and pass
    while proving nothing.
    """
    ctx._loaders.pop("scenes_by_sole_dataset", None)
    ctx._loaders.pop("latest_snapshot_by_scene", None)
    result = await schema.execute(
        LATEST,
        context_value=ctx,
        variable_values={"dataset": str(dataset.pk), "lens": str(lens.pk), "scene": str(scene.pk)},
    )
    assert not result.errors, result.errors
    return tuple((result.data[key]["latestSnapshot"] or {}).get("name") for key in ("adataset", "lens", "scene"))


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    scene = await seed.create_scene(ctx, "Composition")
    created = await _snapshot(ctx, scene, "shot.png", name="Shot")
    assert created["scene"]["id"] == str(scene.pk)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_records_its_creator(db, authenticated_context: HttpContext):
    """The legacy `create_snapshot` never sets `creator`, which leaves its own delete guard
    matching nobody but admins. This one sets it, and that is what makes the guard real."""
    ctx = authenticated_context
    scene = await seed.create_scene(ctx, "Composition")
    created = await _snapshot(ctx, scene, "creator.png")

    row = await models.SceneSnapshot.objects.aget(pk=created["id"])
    assert row.creator_id == ctx.request.user.id
    assert row.organization_id == ctx.request.organization.id


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_deleting_the_scene_deletes_its_pictures(db, authenticated_context: HttpContext):
    """A picture of a composition depicts nothing once the composition is gone."""
    ctx = authenticated_context
    scene = await seed.create_scene(ctx, "Composition")
    created = await _snapshot(ctx, scene, "gone.png")

    await sync_to_async(scene.delete)()
    assert not await models.SceneSnapshot.objects.filter(pk=created["id"]).aexists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_filters(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    first = await seed.create_scene(ctx, "First")
    second = await seed.create_scene(ctx, "Second")
    third = await seed.create_scene(ctx, "Third")

    await _snapshot(ctx, first, "a.png", name="A")
    await _snapshot(ctx, second, "b.png", name="B")
    await _snapshot(ctx, third, "c.png", name="C")

    assert await _names(ctx, {"scene": str(first.pk)}) == {"A"}
    assert await _names(ctx, {"scenes": [str(first.pk), str(second.pk)]}) == {"A", "B"}
    assert await _names(ctx, {"search": "a"}) == {"A"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_pin_toggles_both_ways(db, authenticated_context: HttpContext):
    ctx = authenticated_context
    scene = await seed.create_scene(ctx, "Composition")
    created = await _snapshot(ctx, scene, "pin.png", name="Pinned")

    result = await schema.execute(PIN, context_value=ctx, variable_values={"input": {"id": created["id"], "pin": True}})
    assert not result.errors, result.errors
    assert await _names(ctx, {"pinned": True}) == {"Pinned"}

    result = await schema.execute(PIN, context_value=ctx, variable_values={"input": {"id": created["id"], "pin": False}})
    assert not result.errors, result.errors
    assert await _names(ctx, {"pinned": True}) == set()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_delete_guard(db, authenticated_context: HttpContext, bot_context: HttpContext):
    """Run as the bot, not the default context.

    `assert_can_delete` returns early for org admins, and `authenticated_context` is one --
    so a delete test written with it exercises the short-circuit and never the guard.
    """
    ctx = authenticated_context
    scene = await seed.create_scene(ctx, "Composition")

    mine = await _snapshot(bot_context, scene, "mine.png", name="Mine")
    result = await schema.execute(DELETE, context_value=bot_context, variable_values={"input": {"id": mine["id"]}})
    assert not result.errors, result.errors
    assert not await models.SceneSnapshot.objects.filter(pk=mine["id"]).aexists()

    theirs = await _snapshot(ctx, scene, "theirs.png", name="Theirs")
    result = await schema.execute(DELETE, context_value=bot_context, variable_values={"input": {"id": theirs["id"]}})
    assert result.errors, "a non-admin must not delete another user's snapshot"
    assert await models.SceneSnapshot.objects.filter(pk=theirs["id"]).aexists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_the_list_is_scoped_to_the_organization(db, authenticated_context: HttpContext, other_org_context: HttpContext):
    """Without get_queryset a bare list field returns every row in the table.

    The legacy `snapshots` field has exactly that hole. It needs two organizations to see,
    and the rest of the suite is single-org -- so nothing else here would catch it.
    """
    ctx = authenticated_context
    await _snapshot(ctx, await seed.create_scene(ctx, "Ours"), "ours.png", name="Ours")
    await _snapshot(other_org_context, await seed.create_scene(other_org_context, "Theirs"), "theirs.png", name="Theirs")

    assert await _names(ctx, {}) == {"Ours"}
    assert await _names(other_org_context, {}) == {"Theirs"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_latest_snapshot_of_a_sole_occupant(db, authenticated_context: HttpContext):
    """The dataset is the scene's only placed dataset, so the picture shows it and nothing else."""
    ctx = authenticated_context
    dataset = await seed.create_adataset(ctx, "DS")
    lens = await seed.create_lens(ctx, dataset, slices=[])
    scene = await seed.create_scene(ctx, "Composition")
    await seed.register_into_scene(ctx, scene, dataset)

    assert await _latest(ctx, dataset, lens, scene) == (None, None, None), "nothing snapshotted yet"

    await _snapshot(ctx, scene, "old.png", name="Old")
    await _snapshot(ctx, scene, "new.png", name="New")

    assert await _latest(ctx, dataset, lens, scene) == ("New", "New", "New")


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_latest_snapshot_spans_the_datasets_scenes(db, authenticated_context: HttpContext):
    """Sole-placed in two scenes, the dataset answers with the newest picture of either.

    The per-request map holds one latest snapshot *per scene*; the dataset's answer is
    the max across its sole scenes. A picture of the second scene taken after the first
    scene's must win, even though each scene keeps its own latest.
    """
    ctx = authenticated_context
    dataset = await seed.create_adataset(ctx, "DS")
    lens = await seed.create_lens(ctx, dataset, slices=[])
    first = await seed.create_scene(ctx, "First")
    second = await seed.create_scene(ctx, "Second")
    await seed.register_into_scene(ctx, first, dataset)
    await seed.register_into_scene(ctx, second, dataset)

    await _snapshot(ctx, first, "earlier.png", name="Earlier")
    await _snapshot(ctx, second, "later.png", name="Later")

    assert await _latest(ctx, dataset, lens, first) == ("Later", "Later", "Earlier")
    assert await _latest(ctx, dataset, lens, second) == ("Later", "Later", "Later")


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_deleting_the_latest_falls_back_to_the_previous(db, authenticated_context: HttpContext):
    """Latest is recomputed per request, never stored -- deleting it needs no invalidation."""
    ctx = authenticated_context
    dataset = await seed.create_adataset(ctx, "DS")
    lens = await seed.create_lens(ctx, dataset, slices=[])
    scene = await seed.create_scene(ctx, "Composition")
    await seed.register_into_scene(ctx, scene, dataset)

    await _snapshot(ctx, scene, "old.png", name="Old")
    newest = await _snapshot(ctx, scene, "new.png", name="New")
    assert await _latest(ctx, dataset, lens, scene) == ("New", "New", "New")

    result = await schema.execute(DELETE, context_value=ctx, variable_values={"input": {"id": newest["id"]}})
    assert not result.errors, result.errors
    assert await _latest(ctx, dataset, lens, scene) == ("Old", "Old", "Old")


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_unregistered_dataset_has_no_latest_snapshot(db, authenticated_context: HttpContext):
    """A scene it is not placed in is not a picture of it, snapshot or no snapshot."""
    ctx = authenticated_context
    dataset = await seed.create_adataset(ctx, "Unplaced")
    lens = await seed.create_lens(ctx, dataset, slices=[])
    scene = await seed.create_scene(ctx, "Composition")
    await _snapshot(ctx, scene, "elsewhere.png", name="Elsewhere")

    dataset_latest, lens_latest, scene_latest = await _latest(ctx, dataset, lens, scene)
    assert dataset_latest is None
    assert lens_latest is None
    assert scene_latest == "Elsewhere", "the scene still has its own picture"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_sole_occupancy_a_second_dataset_blinds_both(db, authenticated_context: HttpContext):
    """The load-bearing rule: a picture of two datasets is a preview of neither.

    This is what separates this design from "the latest picture of any scene it appears
    in". Without the sole-occupancy check both datasets would answer with a composite
    that is mostly the *other* one -- so if this test ever passes with the check removed,
    the check has stopped working.
    """
    ctx = authenticated_context
    first = await seed.create_adataset(ctx, "First")
    second = await seed.create_adataset(ctx, "Second")
    first_lens = await seed.create_lens(ctx, first, slices=[])
    second_lens = await seed.create_lens(ctx, second, slices=[])
    scene = await seed.create_scene(ctx, "Shared")

    await seed.register_into_scene(ctx, scene, first)
    await _snapshot(ctx, scene, "alone.png", name="Alone")
    assert await _latest(ctx, first, first_lens, scene) == ("Alone", "Alone", "Alone")

    # A second dataset joins the composition: the picture is now of both.
    await seed.register_into_scene(ctx, scene, second)
    assert await _latest(ctx, first, first_lens, scene) == (None, None, "Alone")
    assert await _latest(ctx, second, second_lens, scene) == (None, None, "Alone")


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_two_lenses_of_one_dataset_keep_sole_occupancy(db, authenticated_context: HttpContext):
    """Sole occupancy counts datasets, not lenses -- two views of one dataset is still one dataset."""
    ctx = authenticated_context
    dataset = await seed.create_adataset(ctx, "DS")
    whole = await seed.create_lens(ctx, dataset, slices=[])
    cropped = await seed.create_lens(ctx, dataset, slices=[{"axis": "y", "start": 8, "stop": 40}])
    scene = await seed.create_scene(ctx, "Composition")
    await seed.register_into_scene(ctx, scene, dataset)
    await _snapshot(ctx, scene, "both.png", name="Both")

    # Every lens of the dataset answers alike: the picture is of the scene, not the lens.
    assert await _latest(ctx, dataset, whole, scene) == ("Both", "Both", "Both")
    assert await _latest(ctx, dataset, cropped, scene) == ("Both", "Both", "Both")


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_placed_but_never_drawn_still_counts(db, authenticated_context: HttpContext):
    """The accepted caveat, pinned so nobody "fixes" it.

    Resolution goes through the coordinate systems -- placed, not drawn. A dataset
    registered into a scene's world with no layer anywhere is still that scene's only
    placed dataset, and the scene's picture may show nothing at all. This is the known
    cost of the placeable route over the layers route, and it was chosen deliberately.
    """
    ctx = authenticated_context
    dataset = await seed.create_adataset(ctx, "Registered")
    lens = await seed.create_lens(ctx, dataset, slices=[])
    scene = await seed.create_scene(ctx, "Empty")
    await seed.register_into_scene(ctx, scene, dataset)
    await _snapshot(ctx, scene, "empty.png", name="Empty")

    assert not await models.Layer.objects.filter(scene=scene).aexists(), "nothing is drawn in this scene"
    assert await _latest(ctx, dataset, lens, scene) == ("Empty", "Empty", "Empty")


LIST_WITH_LATEST = """
query {
  adatasets { id latestSnapshot { id store { key } } }
  scenes { id latestSnapshot { id store { key } } }
}
"""


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_latest_snapshot_page_is_constant_queries(db, authenticated_context: HttpContext, monkeypatch):
    """A page of datasets and scenes must not pay per row for its tiles.

    The regression this pins: `latestSnapshot` once walked the placement graph per org
    scene (~15 queries each -- 8 datasets cost ~130) and fetched one snapshot per row.
    The map is now two flat queries plus one DISTINCT ON, so the whole page stays under
    a bound no per-scene cost could. Counted by patching the cursor, not
    `CaptureQueriesContext`, because resolvers run on executor threads with their own
    connections.
    """
    ctx = authenticated_context
    for i in range(8):
        dataset = await seed.create_adataset(ctx, f"DS{i}")
        scene = await seed.create_scene(ctx, f"Scene{i}")
        await seed.register_into_scene(ctx, scene, dataset)
        await _snapshot(ctx, scene, f"shot{i}.png", name=f"Shot{i}")

    from django.db.backends import utils as db_utils

    queries: list[str] = []
    original = db_utils.CursorWrapper.execute

    def counting_execute(cursor_self, sql, params=None):
        queries.append(sql)
        return original(cursor_self, sql, params)

    monkeypatch.setattr(db_utils.CursorWrapper, "execute", counting_execute)
    ctx._loaders.clear()

    result = await schema.execute(LIST_WITH_LATEST, context_value=ctx)
    assert not result.errors, result.errors
    tiles = {row["latestSnapshot"]["id"] for row in result.data["adatasets"] if row["latestSnapshot"]}
    assert len(tiles) == 8, "every dataset must report its own tile"
    assert len(queries) < 30, f"page ran {len(queries)} queries -- a per-row or per-scene cost is back:\n" + "\n".join(queries)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_latest_snapshot_does_not_cross_organizations(db, authenticated_context: HttpContext, other_org_context: HttpContext):
    """The candidate scenes are org-scoped, so another org's composition is never the answer."""
    ctx = authenticated_context
    dataset = await seed.create_adataset(ctx, "Ours")
    lens = await seed.create_lens(ctx, dataset, slices=[])
    scene = await seed.create_scene(ctx, "Ours")
    await seed.register_into_scene(ctx, scene, dataset)

    their_scene = await seed.create_scene(other_org_context, "Theirs")
    await _snapshot(other_org_context, their_scene, "theirs.png", name="Theirs")

    assert await _latest(ctx, dataset, lens, scene) == (None, None, None)
