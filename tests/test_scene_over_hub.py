"""Scenes composing over a shared hub: adoption, one truth per space, and lifecycles.

A scene's ``world`` says WHICH space it composes over; it stops being ownership the
moment the space is an adopted hub. Under RFC-6 there is no membership set: a
registration into a shared space is unique per data-tree and places in *every* scene
over that space -- a rival alignment is a claim into a different space, never a second
row in this one. These tests pin the consequences: the collision guard refusing the
rival, two truths living in two hubs, deletion of the claim genuinely un-placing, and
the hub outliving every scene over it while a minted world still dies with its own.
"""

import pytest
from asgiref.sync import sync_to_async
from django.db.models import RestrictedError
from kante.context import HttpContext, UniversalRequest
from strawberry.http.temporal_response import TemporalResponse

from core import enums, models
from core.logic import graph as graph_logic
from mikro_server.schema import schema
from tests import seed


CREATE_SCENE = """
mutation CreateScene($input: CreateSceneInput!) {
  createScene(input: $input) {
    id name
    worldCoordinateSystem { id kind epoch }
  }
}
"""

SCENE_LAYERS = """
query SceneLayers($id: ID!) {
  scene(id: $id) {
    layers {
      id
      placement
      pathToWorld { transformation { id } }
    }
  }
}
"""

DELETE_SCENE = """
mutation Delete($input: DeleteSceneInput!) {
  deleteScene(input: $input)
}
"""

#: A 2-axis identity and a y-shifted rival, rows N_out x (N_in + 1).
IDENTITY_2D = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
SHIFTED_2D = [[1.0, 0.0, 500.0], [0.0, 1.0, 0.0]]


def _fresh_request(ctx: HttpContext) -> HttpContext:
    """A new request for the same identity, so the scene-graph memo cannot go stale."""
    request = UniversalRequest(
        _extensions={"token": "test"},
        _client=ctx.request._client,
        _user=ctx.request._user,
        _organization=ctx.request._organization,
    )
    request.set_membership(ctx.request._membership)  # type: ignore[arg-type]
    return HttpContext(request=request, response=TemporalResponse(), headers=ctx.headers, type="http")


def _make_hub(ctx: HttpContext, name: str = "hub", axis_type: str = enums.AxisTypeChoices.SPACE.value) -> "models.CoordinateSystem":
    """An ownerless hub with calibrated y/x axes (or a deliberately non-navigable pair)."""
    hub = models.CoordinateSystem.objects.create(name=name, organization=ctx.request.organization)
    for index, axis_name in enumerate(["y", "x"]):
        models.Axis.objects.create(coordinate_system=hub, order=index, name=axis_name, type=axis_type, unit="micrometer" if axis_type == enums.AxisTypeChoices.SPACE.value else "a.u.")
    return hub


async def _adopt(ctx: HttpContext, hub: "models.CoordinateSystem", name: str) -> dict:
    result = await schema.execute(CREATE_SCENE, context_value=ctx, variable_values={"input": {"name": name, "coordinateSystem": str(hub.pk)}})
    assert not result.errors, result.errors
    return result.data["createScene"]


def _register_into(ctx: HttpContext, source: "models.CoordinateSystem", hub: "models.CoordinateSystem", affine: list) -> "models.Transformation":
    """One authored registration source -> hub: the space's one truth for this data.

    Through the real writer, so the one-claim-per-space guard runs exactly as it
    would for a client.
    """
    return graph_logic.build_registration_edge(
        input_system=source,
        output_system=hub,
        kind=enums.TransformKind.AFFINE,
        affine=affine,
        ctx=seed._creation(ctx),
    )


def _image_layer(scene_pk: str, lens: "models.Lens") -> "models.Layer":
    return models.Layer.objects.create(kind=enums.LayerKindChoices.IMAGE.value, scene_id=scene_pk, lens=lens)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_rival_registration_into_one_shared_world_is_refused(authenticated_context: HttpContext):
    """One truth per space: the second claim of one dataset into one hub collides.

    The refusal is the design: within a world, where data sits has exactly one current
    answer, and an alternative is not a rival row but a claim into a *different* space.
    Every scene over the hub sees the surviving claim -- there is no membership to
    disagree through.
    """
    dataset = await seed.create_adataset(authenticated_context, "Shared", axes=seed.YX_AXES, shapes=[[64, 64]])
    lens = await seed.create_lens(authenticated_context, dataset, slices=[])

    hub = await sync_to_async(_make_hub)(authenticated_context)
    scene_a = await _adopt(authenticated_context, hub, "A")
    scene_b = await _adopt(authenticated_context, hub, "B")
    assert scene_a["worldCoordinateSystem"]["id"] == scene_b["worldCoordinateSystem"]["id"] == str(hub.pk)

    def setup():
        intrinsic = dataset.intrinsic_coordinate_system
        edge = _register_into(authenticated_context, intrinsic, hub, IDENTITY_2D)
        _image_layer(scene_a["id"], lens)
        _image_layer(scene_b["id"], lens)
        return intrinsic, edge

    intrinsic, edge = await sync_to_async(setup)()

    with pytest.raises(ValueError, match="One truth per space"):
        await sync_to_async(_register_into)(authenticated_context, intrinsic, hub, SHIFTED_2D)

    for scene in (scene_a, scene_b):
        result = await schema.execute(SCENE_LAYERS, context_value=_fresh_request(authenticated_context), variable_values={"id": scene["id"]})
        assert not result.errors, result.errors
        (layer,) = result.data["scene"]["layers"]
        assert layer["placement"] == "PLACED"
        assert layer["pathToWorld"][-1]["transformation"]["id"] == str(edge.pk), "every scene over one space composes the same, single claim"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_two_truths_live_in_two_spaces(authenticated_context: HttpContext):
    """The rival that the one hub refused is at home in a fork of the space.

    registration1 and registration2 are claims into different worlds: two hubs, two
    scenes, and each scene's layer ends in its own space's truth.
    """
    dataset = await seed.create_adataset(authenticated_context, "Forked", axes=seed.YX_AXES, shapes=[[64, 64]])
    lens = await seed.create_lens(authenticated_context, dataset, slices=[])

    hub_v1 = await sync_to_async(_make_hub)(authenticated_context, name="hub-v1")
    hub_v2 = await sync_to_async(_make_hub)(authenticated_context, name="hub-v2")
    scene_a = await _adopt(authenticated_context, hub_v1, "A")
    scene_b = await _adopt(authenticated_context, hub_v2, "B")

    def setup():
        intrinsic = dataset.intrinsic_coordinate_system
        edge_a = _register_into(authenticated_context, intrinsic, hub_v1, IDENTITY_2D)
        edge_b = _register_into(authenticated_context, intrinsic, hub_v2, SHIFTED_2D)
        _image_layer(scene_a["id"], lens)
        _image_layer(scene_b["id"], lens)
        return edge_a, edge_b

    edge_a, edge_b = await sync_to_async(setup)()

    for scene, expected in ((scene_a, edge_a), (scene_b, edge_b)):
        result = await schema.execute(SCENE_LAYERS, context_value=_fresh_request(authenticated_context), variable_values={"id": scene["id"]})
        assert not result.errors, result.errors
        (layer,) = result.data["scene"]["layers"]
        assert layer["placement"] == "PLACED"
        assert layer["pathToWorld"][-1]["transformation"]["id"] == str(expected.pk), "each scene's layer must end in its own space's claim, never the other's"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_deleting_the_registration_unplaces_the_layer(authenticated_context: HttpContext):
    """The claim is what places: deleting it un-places the layer in every scene over the space.

    There is no membership to withdraw -- un-registering IS deleting the edge, and the
    layer degrades to UNREGISTERED rather than being deleted with it."""
    dataset = await seed.create_adataset(authenticated_context, "Removable", axes=seed.YX_AXES, shapes=[[64, 64]])
    lens = await seed.create_lens(authenticated_context, dataset, slices=[])
    hub = await sync_to_async(_make_hub)(authenticated_context)
    scene = await _adopt(authenticated_context, hub, "Removal")

    def setup():
        edge = _register_into(authenticated_context, dataset.intrinsic_coordinate_system, hub, IDENTITY_2D)
        _image_layer(scene["id"], lens)
        return edge

    edge = await sync_to_async(setup)()

    placed = await schema.execute(SCENE_LAYERS, context_value=_fresh_request(authenticated_context), variable_values={"id": scene["id"]})
    assert placed.data["scene"]["layers"][0]["placement"] == "PLACED"

    await sync_to_async(edge.delete)()

    after = await schema.execute(SCENE_LAYERS, context_value=_fresh_request(authenticated_context), variable_values={"id": scene["id"]})
    (layer,) = after.data["scene"]["layers"]
    assert layer["pathToWorld"] is None, "a deleted claim must not place its layer"
    assert layer["placement"] == "UNREGISTERED"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_scene_adopts_a_hub_and_rejects_slices_and_minted_worlds(authenticated_context: HttpContext):
    """Adoption composes over the space as it is: axes and epoch come from the system.

    Since RFC-6's resolution, owned systems are adoptable too (a calibration, an
    intrinsic grid -- see test_scene_over_owned_system.py); the refusals that remain
    are an ARRAY system (a slice of a grid, not a space) and another scene's minted
    world (it cascades with that scene)."""
    hub = await sync_to_async(_make_hub)(authenticated_context)

    scene = await _adopt(authenticated_context, hub, "Adopted")
    assert scene["worldCoordinateSystem"]["id"] == str(hub.pk)
    assert scene["worldCoordinateSystem"]["kind"] == "SHARED"

    # axes or epoch alongside coordinateSystem: the space already has both.
    for extra in ({"axes": [{"name": "y", "type": "SPACE", "unit": "micrometer"}]}, {"epoch": "2026-07-15T12:00:00Z"}):
        result = await schema.execute(CREATE_SCENE, context_value=authenticated_context, variable_values={"input": {"name": "nope", "coordinateSystem": str(hub.pk), **extra}})
        assert result.errors and "takes its axes and epoch from it" in str(result.errors[0])

    # Another scene's minted world cascades with that scene: never adoptable.
    minted = await seed.create_scene(authenticated_context, "Minted")
    minted_world = await sync_to_async(lambda: minted.world)()
    rejected = await schema.execute(CREATE_SCENE, context_value=authenticated_context, variable_values={"input": {"name": "nope", "coordinateSystem": str(minted_world.pk)}})
    assert rejected.errors and "cannot be a scene's world" in str(rejected.errors[0])

    # An ARRAY system (a lens' cropped grid) is a slice of a space, not a space.
    dataset = await seed.create_adataset(authenticated_context, "Cropped", axes=seed.YX_AXES, shapes=[[64, 64]])
    sliced = await seed.create_lens(authenticated_context, dataset, slices=[{"axis": "y", "start": 8, "stop": 40}])
    lens_system = await sync_to_async(lambda: sliced.coordinate_system)()
    rejected = await schema.execute(CREATE_SCENE, context_value=authenticated_context, variable_values={"input": {"name": "nope", "coordinateSystem": str(lens_system.pk)}})
    assert rejected.errors and "slice of its container's grid" in str(rejected.errors[0])

    # A hub with no navigable axis has nowhere to put anything.
    flat = await sync_to_async(_make_hub)(authenticated_context, name="channels-only", axis_type=enums.AxisTypeChoices.CHANNEL.value)
    rejected = await schema.execute(CREATE_SCENE, context_value=authenticated_context, variable_values={"input": {"name": "nope", "coordinateSystem": str(flat.pk)}})
    assert rejected.errors and "navigable" in str(rejected.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_deleting_a_scene_leaves_the_hub_and_its_sibling_standing(authenticated_context: HttpContext):
    """The hub outlives every scene over it; a minted world still dies with its own scene."""
    dataset = await seed.create_adataset(authenticated_context, "Survivor", axes=seed.YX_AXES, shapes=[[64, 64]])
    lens = await seed.create_lens(authenticated_context, dataset, slices=[])
    hub = await sync_to_async(_make_hub)(authenticated_context)
    scene_a = await _adopt(authenticated_context, hub, "Doomed")
    scene_b = await _adopt(authenticated_context, hub, "Survivor")

    def setup():
        edge = _register_into(authenticated_context, dataset.intrinsic_coordinate_system, hub, IDENTITY_2D)
        _image_layer(scene_a["id"], lens)
        _image_layer(scene_b["id"], lens)
        return edge

    edge = await sync_to_async(setup)()

    deleted = await schema.execute(DELETE_SCENE, context_value=authenticated_context, variable_values={"input": {"id": scene_a["id"]}})
    assert not deleted.errors, deleted.errors

    assert await sync_to_async(models.CoordinateSystem.objects.filter(pk=hub.pk).exists)(), "an adopted hub is referenced, never owned"
    assert await sync_to_async(models.Transformation.objects.filter(pk=edge.pk).exists)(), "the registration is a fact about the hub, not about the dead scene"
    survivor = await schema.execute(SCENE_LAYERS, context_value=_fresh_request(authenticated_context), variable_values={"id": scene_b["id"]})
    assert survivor.data["scene"]["layers"][0]["placement"] == "PLACED", "the sibling scene's composition is untouched"

    # A minted world still cascades with its scene: ownership is unchanged.
    minted = await seed.create_scene(authenticated_context, "Owned")
    minted_world_pk = await sync_to_async(lambda: minted.world_id)()
    deleted = await schema.execute(DELETE_SCENE, context_value=authenticated_context, variable_values={"input": {"id": str(minted.pk)}})
    assert not deleted.errors, deleted.errors
    assert not await sync_to_async(models.CoordinateSystem.objects.filter(pk=minted_world_pk).exists)()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_hub_cannot_be_deleted_out_from_under_a_scene(authenticated_context: HttpContext):
    """Scene.world is RESTRICT: a space is never deleted while a scene composes over it --
    but the restriction yields when the whole organization goes (the RESTRICT-vs-PROTECT trap)."""
    hub = await sync_to_async(_make_hub)(authenticated_context)
    await _adopt(authenticated_context, hub, "Holder")

    with pytest.raises(RestrictedError):
        await sync_to_async(hub.delete)()

    # An org cascade collects the scenes too, so the restriction clears against the
    # deletion set instead of raising -- exactly what PROTECT would get wrong.
    organization = authenticated_context.request.organization
    await sync_to_async(organization.delete)()
    assert not await sync_to_async(models.CoordinateSystem.objects.filter(pk=hub.pk).exists)()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_builder_over_a_hub_of_unrenderable_sources_makes_no_layers(authenticated_context: HttpContext):
    """A source too small to render becomes no layer -- and its claim is untouched.

    The registration is a fact about the *space*, not about the scene the builder is
    making: skipping the layer does not unmake it, and the scene's `registrations`
    field (the space's claims) still reports it."""
    tiny = await seed.create_adataset(authenticated_context, "Tiny", axes=seed.YX_AXES, shapes=[[64, 1]])
    hub = await sync_to_async(_make_hub)(authenticated_context)

    def register():
        return graph_logic.build_registration_edge(
            input_system=tiny.intrinsic_coordinate_system,
            output_system=hub,
            kind=enums.TransformKind.BY_DIMENSION,
            name=None,
            scale=None,
            translation=None,
            affine=None,
            input_axes=["y", "x"],
            output_axes=["y", "x"],
            store=None,
            reason=None,
            validity=enums.PlacementValidity.VALIDATED,
            ctx=seed._creation(authenticated_context),
        )

    await sync_to_async(register)()

    result = await schema.execute(
        """
        mutation FromCS($input: CreateSceneFromCoordinateSystemInput!) {
          createSceneFromCoordinateSystem(input: $input) {
            id
            registrations { id }
            layers { id }
          }
        }
        """,
        context_value=authenticated_context,
        variable_values={"input": {"coordinateSystem": str(hub.pk), "policy": {}}},
    )
    assert not result.errors, result.errors
    scene = result.data["createSceneFromCoordinateSystem"]
    assert scene["layers"] == []
    assert len(scene["registrations"]) == 1, "the claim is the space's fact; a skipped layer does not unmake it"
