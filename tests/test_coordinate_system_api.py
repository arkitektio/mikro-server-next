"""The coordinate system's own API surface: what a system says about itself, and a shared space's lifecycle.

``isAdoptableWorld`` answers "may a scene compose over this?" (everything but an ARRAY
slice), and ``owner`` says *which* container a system hangs off where ``kind`` only said
what sort -- a SHARED space has no owner at all: scenes adopt one as their world but
never own it, so no scene's deletion ever removes a space. That is why the explicit
lifecycle lives here: without ``deleteCoordinateSystem`` an ownerless space outlived
every correction anyone could make to it.

Every delete here runs as ``bot_context``, not the admin fixture: ``assert_can_delete`` waves
org admins through before it ever reads the ownership callable, so an admin-only test cannot
tell a working guard from one that raises AttributeError on a column the model does not have.
"""

import pytest
from asgiref.sync import sync_to_async
from kante.context import HttpContext

from core import enums, models
from mikro_server.schema import schema
from tests import seed
# The collection fixtures live with the layer-kind tests, which is where a mesh or table
# collection is otherwise built; the owner union is the only other thing that needs one.
from tests.test_layer_kinds import _seed_mesh_collection_sync, _seed_table_dataset_sync


CREATE_CS = """
mutation CreateCS($input: CreateCoordinateSystemInput!) {
  createCoordinateSystem(input: $input) { id kind name isAdoptableWorld }
}
"""

UPDATE_CS = """
mutation UpdateCS($input: UpdateCoordinateSystemInput!) {
  updateCoordinateSystem(input: $input) { id name epoch }
}
"""

DELETE_CS = """
mutation DeleteCS($input: DeleteCoordinateSystemInput!) {
  deleteCoordinateSystem(input: $input)
}
"""

SYSTEM = """
query System($id: ID!) {
  coordinateSystem(id: $id) {
    id kind isAdoptableWorld
    creator { id }
    owner {
      __typename
      ... on ADataset { id name }
      ... on Lens { id }
      ... on MeshCollection { id version }
      ... on TableDataset { id name }
    }
  }
}
"""

LIST_SYSTEMS = """
query Systems($kind: CoordinateSystemKind!) {
  coordinateSystems(filters: { kind: $kind }) { id kind }
}
"""

ATLAS_AXES = [
    {"name": "y", "type": "SPACE", "unit": "micrometer"},
    {"name": "x", "type": "SPACE", "unit": "micrometer"},
]


async def _create_space(ctx: HttpContext, name: str = "Atlas", axes=None, registrations=None) -> dict:
    result = await schema.execute(
        CREATE_CS,
        context_value=ctx,
        variable_values={"input": {"name": name, "axes": axes if axes is not None else ATLAS_AXES, "registrations": registrations or []}},
    )
    assert not result.errors, result.errors
    return result.data["createCoordinateSystem"]


async def _system(ctx: HttpContext, system_id: str) -> dict:
    result = await schema.execute(SYSTEM, context_value=ctx, variable_values={"id": str(system_id)})
    assert not result.errors, result.errors
    return result.data["coordinateSystem"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_scenes_world_is_an_ordinary_shared_space(authenticated_context: HttpContext):
    """One kind of shared space: a world created alongside a scene is the same thing as an atlas.

    Scenes never own a space, so the space a bare `createScene` makes is SHARED,
    adoptable by other scenes, and outlives them all -- exactly like a space created
    directly with `createCoordinateSystem`.
    """
    atlas = await _create_space(authenticated_context, "Atlas")
    assert atlas["kind"] == "SHARED"
    assert atlas["isAdoptableWorld"] is True

    scene = await seed.create_scene(authenticated_context, "Bare")
    world = await sync_to_async(lambda: scene.world)()
    shared = await _system(authenticated_context, world.pk)

    assert shared["kind"] == "SHARED"
    assert shared["isAdoptableWorld"] is True, "another scene may compose over the same space"
    assert shared["owner"] is None, "a scene adopts its world, it never owns it"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_owned_system_is_adoptable_but_a_slice_of_one_is_not(authenticated_context: HttpContext):
    """`isAdoptableWorld` tracks the one refusal in the model, not the kind."""
    dataset = await seed.create_adataset(authenticated_context, "A", axes=seed.YX_AXES, shapes=[[64, 64]])
    intrinsic = await sync_to_async(lambda: dataset.coordinate_system)()

    # A dataset's own pixel grid: not a shared space (the dataset owns it), but a scene may root there.
    owned = await _system(authenticated_context, intrinsic.pk)
    assert owned["kind"] == "INTRINSIC"
    assert owned["isAdoptableWorld"] is True

    # A lens' cropped grid is a slice *of* a space, not a space to compose in.
    lens = await seed.create_lens(authenticated_context, dataset, slices=[{"axis": "y", "start": 8, "stop": 40}])
    lens_system = await sync_to_async(lambda: lens.coordinate_system)()
    sliced = await _system(authenticated_context, lens_system.pk)
    assert sliced["kind"] == "ARRAY"
    assert sliced["isAdoptableWorld"] is False


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_owner_names_the_container_where_kind_only_named_the_sort(authenticated_context: HttpContext):
    """`owner` resolves to the container itself; a shared space has none."""
    dataset = await seed.create_adataset(authenticated_context, "Owned", axes=seed.YX_AXES, shapes=[[64, 64]])
    intrinsic = await sync_to_async(lambda: dataset.coordinate_system)()

    owner = (await _system(authenticated_context, intrinsic.pk))["owner"]
    assert owner["__typename"] == "ADataset"
    assert owner["name"] == "Owned"

    # A calibration hangs off the same dataset by a different FK -- `kind` is what tells the
    # two relationships apart, and it still does.
    calibration = await seed.create_calibration(
        authenticated_context,
        dataset,
        axes=[seed.calibrated_axis("y", enums.AxisType.SPACE, "micrometer"), seed.calibrated_axis("x", enums.AxisType.SPACE, "micrometer")],
        scale=[0.325, 0.325],
    )
    physical = await _system(authenticated_context, calibration.pk)
    assert physical["kind"] == "PHYSICAL"
    assert physical["owner"]["__typename"] == "ADataset"
    assert physical["owner"]["id"] == str(dataset.pk)

    scene = await seed.create_scene(authenticated_context, "Bare")
    world = await sync_to_async(lambda: scene.world)()
    assert (await _system(authenticated_context, world.pk))["owner"] is None, "a scene's world is owned by nobody"

    atlas = await _create_space(authenticated_context, "Atlas")
    assert (await _system(authenticated_context, atlas["id"]))["owner"] is None, "a shared space is owned by nobody"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_collection_owns_its_space_and_owner_says_so(authenticated_context: HttpContext):
    """The two arms a dataset-shaped test never reaches.

    A collection's native space is INTRINSIC exactly like a dataset's pixel grid, so `kind`
    cannot tell the three apart -- `owner` is the field that can.
    """
    collection = await sync_to_async(_seed_mesh_collection_sync)(authenticated_context)
    mesh_system = await sync_to_async(lambda: collection.coordinate_system)()
    mesh = await _system(authenticated_context, mesh_system.pk)
    assert mesh["kind"] == "INTRINSIC"
    assert mesh["owner"]["__typename"] == "MeshCollection"
    assert mesh["owner"]["version"] == "v1"

    table = await sync_to_async(_seed_table_dataset_sync)(authenticated_context, "localizations")
    table_system = await sync_to_async(lambda: table.coordinate_system)()
    resolved = await _system(authenticated_context, table_system.pk)
    assert resolved["kind"] == "INTRINSIC"
    assert resolved["owner"]["__typename"] == "TableDataset"
    assert resolved["owner"]["name"] == "localizations"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_kind_shared_lists_every_registrable_space(authenticated_context: HttpContext):
    """`kind: SHARED` is THE predicate for registrable spaces -- a scene's world included.

    There is no second kind of shared space: the world a bare scene gets and an atlas
    created directly are the same thing, so one filter finds them both, and owned
    systems stay out.
    """
    atlas = await _create_space(authenticated_context, "Atlas")
    scene = await seed.create_scene(authenticated_context, "Bare")
    world = await sync_to_async(lambda: scene.world)()
    dataset = await seed.create_adataset(authenticated_context, "A", axes=seed.YX_AXES, shapes=[[64, 64]])

    result = await schema.execute(LIST_SYSTEMS, context_value=authenticated_context, variable_values={"kind": "SHARED"})
    assert not result.errors, result.errors
    shared = {system["id"] for system in result.data["coordinateSystems"]}
    assert shared == {atlas["id"], str(world.pk)}, "every ownerless space is SHARED, scene worlds included"

    result = await schema.execute(LIST_SYSTEMS, context_value=authenticated_context, variable_values={"kind": "INTRINSIC"})
    assert not result.errors, result.errors
    intrinsic = await sync_to_async(lambda: dataset.coordinate_system)()
    owned = {system["id"] for system in result.data["coordinateSystems"]}
    assert str(intrinsic.pk) in owned and atlas["id"] not in owned


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_shared_space_can_be_renamed_and_its_clock_anchored(authenticated_context: HttpContext):
    """The fields that describe the space itself. Where its data sits stays an edge."""
    space = await _create_space(authenticated_context, "Atals")  # the typo this mutation exists for

    result = await schema.execute(
        UPDATE_CS,
        context_value=authenticated_context,
        variable_values={"input": {"id": space["id"], "name": "Atlas", "epoch": "2026-07-16T00:00:00+00:00"}},
    )
    assert not result.errors, result.errors
    assert result.data["updateCoordinateSystem"]["name"] == "Atlas"
    assert result.data["updateCoordinateSystem"]["epoch"] is not None

    # Partial: a rename does not clear the clock someone just anchored.
    result = await schema.execute(UPDATE_CS, context_value=authenticated_context, variable_values={"input": {"id": space["id"], "name": "Atlas v2"}})
    assert not result.errors, result.errors
    assert result.data["updateCoordinateSystem"]["epoch"] is not None


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_owned_system_cannot_be_renamed_or_deleted_directly(authenticated_context: HttpContext):
    """Both shared-space mutations refuse an owned system: it is named and removed by its container."""
    dataset = await seed.create_adataset(authenticated_context, "A", axes=seed.YX_AXES, shapes=[[64, 64]])
    intrinsic = await sync_to_async(lambda: dataset.coordinate_system)()

    renamed = await schema.execute(UPDATE_CS, context_value=authenticated_context, variable_values={"input": {"id": str(intrinsic.pk), "name": "nope"}})
    assert renamed.errors and "owned by a container" in str(renamed.errors[0])

    deleted = await schema.execute(DELETE_CS, context_value=authenticated_context, variable_values={"input": {"id": str(intrinsic.pk)}})
    assert deleted.errors and "owned by a container" in str(deleted.errors[0])
    assert await sync_to_async(models.CoordinateSystem.objects.filter(pk=intrinsic.pk).exists)(), "the dataset's spatial graph survives"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_unused_space_is_deletable_by_its_creator(bot_context: HttpContext):
    """The whole point: a space created by mistake can be taken back.

    Runs as a non-admin, so `assert_can_delete` actually consults the ownership callable
    rather than short-circuiting -- which is what would have caught `self_owner` reading a
    `created_through_by` column the coordinate graph does not have.
    """
    space = await _create_space(bot_context, "Mistake")

    result = await schema.execute(DELETE_CS, context_value=bot_context, variable_values={"input": {"id": space["id"]}})
    assert not result.errors, result.errors
    assert result.data["deleteCoordinateSystem"] == space["id"]
    assert not await sync_to_async(models.CoordinateSystem.objects.filter(pk=space["id"]).exists)()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_space_someone_else_created_is_not_yours_to_delete(authenticated_context: HttpContext, bot_context: HttpContext):
    """The ownership guard, reached only because the caller is not an org admin."""
    space = await _create_space(authenticated_context, "Theirs")

    result = await schema.execute(DELETE_CS, context_value=bot_context, variable_values={"input": {"id": space["id"]}})
    assert result.errors and "Only the creator or assignee can delete this" in str(result.errors[0])
    assert await sync_to_async(models.CoordinateSystem.objects.filter(pk=space["id"]).exists)()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_space_in_use_is_refused_rather_than_cascaded_away(bot_context: HttpContext):
    """Each refusal guards a CASCADE that would take something the caller never named."""
    dataset = await seed.create_adataset(bot_context, "A", axes=seed.YX_AXES, shapes=[[64, 64]])
    registration = {"dataset": str(dataset.pk), "kind": "BY_DIMENSION", "inputAxes": ["y", "x"], "outputAxes": ["y", "x"]}
    space = await _create_space(bot_context, "Populated", registrations=[registration])

    # An edge registered into it: deleting the space would delete a placement someone authored.
    result = await schema.execute(DELETE_CS, context_value=bot_context, variable_values={"input": {"id": space["id"]}})
    assert result.errors and "transformation edge" in str(result.errors[0])

    # Remove the registration, and the same space goes.
    edge = await sync_to_async(models.Transformation.objects.get)(output__pk=space["id"], parent__isnull=True)
    await sync_to_async(edge.delete)()
    result = await schema.execute(DELETE_CS, context_value=bot_context, variable_values={"input": {"id": space["id"]}})
    assert not result.errors, result.errors


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_space_a_scene_composes_over_is_refused(bot_context: HttpContext):
    """Scene.world is RESTRICT; the mutation names the scenes instead of raising an IntegrityError."""
    space = await _create_space(bot_context, "Adopted")
    created = await schema.execute(
        "mutation ($input: CreateSceneFromCoordinateSystemInput!) { createSceneFromCoordinateSystem(input: $input) { id } }",
        context_value=bot_context,
        variable_values={"input": {"coordinateSystem": space["id"]}},
    )
    assert not created.errors, created.errors

    result = await schema.execute(DELETE_CS, context_value=bot_context, variable_values={"input": {"id": space["id"]}})
    assert result.errors and "is the world of" in str(result.errors[0])
    assert await sync_to_async(models.CoordinateSystem.objects.filter(pk=space["id"]).exists)()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_refining_an_edge_leaves_a_readable_audit_trail(authenticated_context: HttpContext):
    """RFC-6 Rule 1 is only true if a client can read it.

    "updateTransformation refines an edge in place; koherent provenance holds the history"
    -- a refinement rewrites the row, so the audit trail is the *only* place the placement's
    earlier states exist. The field is on the Transformation interface, so a concrete kind
    (here SCALE) inherits it.
    """
    dataset = await seed.create_adataset(authenticated_context, "A", axes=seed.YX_AXES, shapes=[[64, 64]])
    intrinsic = await sync_to_async(lambda: dataset.coordinate_system)()
    space = await _create_space(authenticated_context, "Atlas")

    created = await schema.execute(
        "mutation ($input: CreateTransformationInput!) { createTransformation(input: $input) { id version } }",
        context_value=authenticated_context,
        variable_values={"input": {"input": str(intrinsic.pk), "output": space["id"], "kind": "SCALE", "scale": [0.5, 0.5]}},
    )
    assert not created.errors, created.errors
    edge_id = created.data["createTransformation"]["id"]

    refined = await schema.execute(
        "mutation ($input: UpdateTransformationInput!) { updateTransformation(input: $input) { id version } }",
        context_value=authenticated_context,
        variable_values={"input": {"id": edge_id, "scale": [0.51, 0.51]}},
    )
    assert not refined.errors, refined.errors
    assert refined.data["updateTransformation"]["version"] == 2

    result = await schema.execute(
        """
        query ($id: ID!) {
          transformation(id: $id) {
            id version creator { id }
            ... on ScaleTransformation { scale }
            provenanceEntries { kind }
          }
        }
        """,
        context_value=authenticated_context,
        variable_values={"id": edge_id},
    )
    assert not result.errors, result.errors
    edge = result.data["transformation"]

    assert edge["scale"] == [0.51, 0.51], "the row itself carries only the current truth"
    # Two states of one placement, sequentially, in the audit trail: the create and the refine.
    kinds = [entry["kind"] for entry in edge["provenanceEntries"]]
    assert len(kinds) == 2, f"expected a CREATE and an UPDATE entry, got {kinds}"
    assert edge["creator"] is not None


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_shared_space_must_have_ordered_axes(authenticated_context: HttpContext):
    """The one axis-writing path that skipped the RFC-5 type-order check.

    A scrambled space does not fail on use -- the render-axis derivation reads x/y/z off the
    *position* of the spatial axes, so it silently renders wrong. That is why the guard has
    to be at the door.
    """
    scrambled = await schema.execute(
        CREATE_CS,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "name": "Scrambled",
                "axes": [
                    {"name": "x", "type": "SPACE", "unit": "micrometer"},
                    {"name": "t", "type": "TIME", "unit": "second"},
                ],
                "registrations": [],
            }
        },
    )
    assert scrambled.errors, "space-before-time must be refused"

    empty = await schema.execute(
        CREATE_CS,
        context_value=authenticated_context,
        variable_values={"input": {"name": "Empty", "axes": [], "registrations": []}},
    )
    assert empty.errors and "no axes" in str(empty.errors[0])
    assert not await sync_to_async(models.CoordinateSystem.objects.filter(name="Empty").exists)(), "the rollback leaves no permanent zero-axis space"
