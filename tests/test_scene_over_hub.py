"""Scenes composing over a shared hub: adoption, membership gating, and lifecycles.

A scene's ``world`` says WHICH space it composes over; it stops being ownership the
moment the space is an adopted hub. That collapses the old per-scene disambiguation
(every scene its own world node), so the membership set carries it instead: an edge
into a shared space places only in the scenes that hold it. These tests pin the three
consequences -- rival registrations into ONE world coexisting scene-by-scene, removal
from a composition genuinely un-placing, and the hub outliving every scene over it
while a minted world still dies with its own.
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

REMOVE_REGISTRATION = """
mutation Remove($input: SceneRegistrationInput!) {
  removeRegistrationFromScene(input: $input) { id }
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


def _register_into(ctx: HttpContext, source: "models.CoordinateSystem", hub: "models.CoordinateSystem", scene_pk: str, affine: list) -> "models.Transformation":
    """One authored registration source -> hub, claimed by exactly one scene's membership."""
    edge = models.Transformation.objects.create(
        kind=enums.TransformKindChoices.AFFINE.value,
        input=source,
        output=hub,
        params={"affine": affine},
        organization=ctx.request.organization,
    )
    models.Scene.objects.get(pk=scene_pk).coordinate_transformations.add(edge)
    return edge


def _image_layer(scene_pk: str, lens: "models.Lens") -> "models.Layer":
    return models.Layer.objects.create(kind=enums.LayerKindChoices.IMAGE.value, scene_id=scene_pk, lens=lens)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_rival_registrations_in_one_shared_world_are_disambiguated_by_membership(authenticated_context: HttpContext):
    """Two scenes over ONE hub hold rival registrations of the same dataset, and each
    layer resolves ITS scene's edge.

    This is the pivot the shared-world design rests on: both edges end in the very same
    world node, so the BFS target no longer separates them -- only the membership set
    does. A registration riding in the dataset's own edge bucket would leak across and
    make this nondeterministic by pk.
    """
    dataset = await seed.create_adataset(authenticated_context, "Shared", axes=seed.YX_AXES, shapes=[[64, 64]])
    lens = await seed.create_lens(authenticated_context, dataset, slices=[])

    hub = await sync_to_async(_make_hub)(authenticated_context)
    scene_a = await _adopt(authenticated_context, hub, "A")
    scene_b = await _adopt(authenticated_context, hub, "B")
    assert scene_a["worldCoordinateSystem"]["id"] == scene_b["worldCoordinateSystem"]["id"] == str(hub.pk)

    def setup():
        intrinsic = dataset.intrinsic_coordinate_system
        edge_a = _register_into(authenticated_context, intrinsic, hub, scene_a["id"], IDENTITY_2D)
        edge_b = _register_into(authenticated_context, intrinsic, hub, scene_b["id"], SHIFTED_2D)
        _image_layer(scene_a["id"], lens)
        _image_layer(scene_b["id"], lens)
        return edge_a, edge_b

    edge_a, edge_b = await sync_to_async(setup)()

    for scene, expected in ((scene_a, edge_a), (scene_b, edge_b)):
        result = await schema.execute(SCENE_LAYERS, context_value=_fresh_request(authenticated_context), variable_values={"id": scene["id"]})
        assert not result.errors, result.errors
        (layer,) = result.data["scene"]["layers"]
        assert layer["placement"] == "PLACED"
        assert layer["pathToWorld"][-1]["transformation"]["id"] == str(expected.pk), "each scene's layer must end in its own registration, never its rival"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_removing_a_registration_unplaces_the_layer(authenticated_context: HttpContext):
    """Membership is what places: removing the registration un-places the layer, while
    the edge itself survives as a fact about two coordinate systems."""
    dataset = await seed.create_adataset(authenticated_context, "Removable", axes=seed.YX_AXES, shapes=[[64, 64]])
    lens = await seed.create_lens(authenticated_context, dataset, slices=[])
    hub = await sync_to_async(_make_hub)(authenticated_context)
    scene = await _adopt(authenticated_context, hub, "Removal")

    def setup():
        edge = _register_into(authenticated_context, dataset.intrinsic_coordinate_system, hub, scene["id"], IDENTITY_2D)
        _image_layer(scene["id"], lens)
        return edge

    edge = await sync_to_async(setup)()

    placed = await schema.execute(SCENE_LAYERS, context_value=_fresh_request(authenticated_context), variable_values={"id": scene["id"]})
    assert placed.data["scene"]["layers"][0]["placement"] == "PLACED"

    removed = await schema.execute(REMOVE_REGISTRATION, context_value=_fresh_request(authenticated_context), variable_values={"input": {"scene": scene["id"], "transformation": str(edge.pk)}})
    assert not removed.errors, removed.errors

    after = await schema.execute(SCENE_LAYERS, context_value=_fresh_request(authenticated_context), variable_values={"id": scene["id"]})
    (layer,) = after.data["scene"]["layers"]
    assert layer["pathToWorld"] is None, "an edge the scene no longer holds must not place its layer"
    assert layer["placement"] == "UNREGISTERED"
    assert await sync_to_async(models.Transformation.objects.filter(pk=edge.pk).exists)(), "removal is a membership statement, not a delete"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_scene_adopts_a_hub_and_rejects_everything_else(authenticated_context: HttpContext):
    """Adoption composes over the space as it is: axes and epoch come from the hub, and
    only an ownerless hub qualifies."""
    hub = await sync_to_async(_make_hub)(authenticated_context)

    scene = await _adopt(authenticated_context, hub, "Adopted")
    assert scene["worldCoordinateSystem"]["id"] == str(hub.pk)
    assert scene["worldCoordinateSystem"]["kind"] == "SHARED"

    # axes or epoch alongside coordinateSystem: the space already has both.
    for extra in ({"axes": [{"name": "y", "type": "SPACE", "unit": "micrometer"}]}, {"epoch": "2026-07-15T12:00:00Z"}):
        result = await schema.execute(CREATE_SCENE, context_value=authenticated_context, variable_values={"input": {"name": "nope", "coordinateSystem": str(hub.pk), **extra}})
        assert result.errors and "takes its axes and epoch from it" in str(result.errors[0])

    # An owned system is not adoptable: another scene's minted world...
    minted = await seed.create_scene(authenticated_context, "Minted")
    minted_world = await sync_to_async(lambda: minted.world)()
    rejected = await schema.execute(CREATE_SCENE, context_value=authenticated_context, variable_values={"input": {"name": "nope", "coordinateSystem": str(minted_world.pk)}})
    assert rejected.errors and "ownerless hub" in str(rejected.errors[0])

    # ...or a dataset's PHYSICAL calibration.
    dataset = await seed.create_adataset(authenticated_context, "Cal", axes=seed.YX_AXES, shapes=[[64, 64]])
    await seed.create_calibration(
        authenticated_context,
        dataset,
        axes=[seed.calibrated_axis("y", enums.AxisType.SPACE, "micrometer"), seed.calibrated_axis("x", enums.AxisType.SPACE, "micrometer")],
        scale=[0.5, 0.5],
    )
    physical = await sync_to_async(lambda: dataset.calibrations.get())()
    rejected = await schema.execute(CREATE_SCENE, context_value=authenticated_context, variable_values={"input": {"name": "nope", "coordinateSystem": str(physical.pk)}})
    assert rejected.errors and "ownerless hub" in str(rejected.errors[0])

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
        edge = _register_into(authenticated_context, dataset.intrinsic_coordinate_system, hub, scene_a["id"], IDENTITY_2D)
        models.Scene.objects.get(pk=scene_b["id"]).coordinate_transformations.add(edge)
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
async def test_builder_over_a_hub_of_unrenderable_sources_claims_nothing(authenticated_context: HttpContext):
    """A skipped source's registration must not linger in the composition: the builder
    adds membership before materializing (the placement gate demands it) and takes it
    back when the layer is skipped."""
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
    assert scene["registrations"] == [], "a source that became no layer must leave no membership behind"
