"""Scenes rooted directly at an owned coordinate system (RFC-6, resolved open question).

With walk-time choice gone, an owned root is correctness-safe: a scene can compose
straight over a dataset's INTRINSIC pixel grid or a PHYSICAL calibration -- no mirror
world, no authored edge. The container's data is placed *by construction* (its fact
tree reaches its own space), only that container's tree can ever compose there
(registrations land exclusively on SHARED spaces), and the lifecycle is RESTRICT:
the container is undeletable while a scene is rooted in its space, exactly as a shared space is.
"""

import pytest
from asgiref.sync import sync_to_async
from django.db.models import RestrictedError
from kante.context import HttpContext

from core import enums, models
from core.logic import graph as graph_logic
from mikro_server.schema import schema
from tests import seed


CREATE_SCENE = """
mutation CreateScene($input: CreateSceneInput!) {
  createScene(input: $input) {
    id name
    worldCoordinateSystem { id  }
  }
}
"""

FROM_SYSTEM = """
mutation FromCS($input: CreateSceneFromCoordinateSystemInput!) {
  createSceneFromCoordinateSystem(input: $input) {
    id
    worldCoordinateSystem { id  }
    layers { id }
    registrations { id }
  }
}
"""

MAKE_LAYER = """
mutation Make($input: CreateIntensityLayerInput!) {
  createIntensityLayer(input: $input) { id }
}
"""

LAYER_PATHS = """
query LayerPaths($id: ID!) {
  scene(id: $id) {
    layers {
      placement
      placementValidity
      pathToWorld {
        inverted
        transformation { input { id  } output { id  } }
      }
    }
  }
}
"""


async def _adopt(ctx: HttpContext, system: "models.CoordinateSystem", name: str) -> dict:
    result = await schema.execute(CREATE_SCENE, context_value=ctx, variable_values={"input": {"name": name, "coordinateSystem": str(system.pk)}})
    assert not result.errors, result.errors
    return result.data["createScene"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_scene_over_a_datasets_intrinsic_grid_places_by_construction(authenticated_context: HttpContext):
    """Adopt the pixel grid itself: the dataset's layer is placed with no edge anywhere.

    An unsliced lens' space IS the world, so its path is empty and exact; a sliced
    lens is one fact hop away. Zero transformations exist in the graph throughout.
    """
    dataset = await seed.create_adataset(authenticated_context, "Bare")  # (c, y, x)
    full = await seed.create_lens(authenticated_context, dataset, slices=[])
    intrinsic = await sync_to_async(lambda: dataset.intrinsic_coordinate_system)()

    scene = await _adopt(authenticated_context, intrinsic, "PixelSpace")
    assert scene["worldCoordinateSystem"]["id"] == str(intrinsic.pk)
    assert scene["worldCoordinateSystem"]["kind"] == "INTRINSIC"

    made = await schema.execute(MAKE_LAYER, context_value=authenticated_context, variable_values={"input": {"scene": scene["id"], "lens": str(full.pk), "intensityAxis": "c"}})
    assert not made.errors, made.errors

    sliced = await seed.create_lens(authenticated_context, dataset, slices=[{"axis": "y", "start": 8, "stop": 40}])
    made = await schema.execute(MAKE_LAYER, context_value=authenticated_context, variable_values={"input": {"scene": scene["id"], "lens": str(sliced.pk), "intensityAxis": "c"}})
    assert not made.errors, made.errors

    result = await schema.execute(LAYER_PATHS, context_value=authenticated_context, variable_values={"id": scene["id"]})
    assert not result.errors, result.errors
    full_layer, sliced_layer = result.data["scene"]["layers"]

    assert full_layer["placement"] == "PLACED"
    assert full_layer["pathToWorld"] == [], "the unsliced lens' space IS the world: nothing to compose"
    assert full_layer["placementValidity"] == "VALIDATED", "an empty path is exact by construction"

    assert sliced_layer["placement"] == "PLACED"
    hops = [(step["transformation"]["input"]["kind"], step["transformation"]["output"]["kind"]) for step in sliced_layer["pathToWorld"]]
    assert hops == [("ARRAY", "INTRINSIC")], "one fact hop: the lens' crop into the grid it slices"

    assert await sync_to_async(models.Transformation.objects.filter(output=intrinsic, input__lens__isnull=True).count)() == 0, "no registration was authored anywhere"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_bootstrap_from_an_intrinsic_system_materializes_the_container(authenticated_context: HttpContext):
    """createSceneFromCoordinateSystem over an owned root: the container becomes the layer, nothing is authored.

    This is the exact call that used to be refused with 'owned by a container, not an
    ownerless shared space'.
    """
    dataset = await seed.create_adataset(authenticated_context, "Owner")
    intrinsic = await sync_to_async(lambda: dataset.intrinsic_coordinate_system)()
    before = await sync_to_async(models.Transformation.objects.count)()

    result = await schema.execute(FROM_SYSTEM, context_value=authenticated_context, variable_values={"input": {"coordinateSystem": str(intrinsic.pk), "policy": {}}})
    assert not result.errors, result.errors
    scene = result.data["createSceneFromCoordinateSystem"]

    assert scene["worldCoordinateSystem"]["id"] == str(intrinsic.pk)
    assert len(scene["layers"]) == 1, "the container's own data is the one candidate"
    assert scene["registrations"] == [], "an owned space has no registrations: the data is in it by definition"
    assert await sync_to_async(models.Transformation.objects.count)() == before, "and the bootstrap authored no edge"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_scene_over_a_calibration_renders_at_physical_scale(authenticated_context: HttpContext):
    """Adopt the PHYSICAL space: the path is the calibration edge, forward, and nothing else.

    The no-mirror scene the design discussion asked for: pixel -> physical is the
    dataset's own fact, so the layer renders at physical scale with zero authored
    registrations.
    """
    dataset = await seed.create_adataset(authenticated_context, "Staged")
    physical = await seed.create_calibration(
        authenticated_context,
        dataset,
        axes=[
            seed.calibrated_axis("c", enums.AxisType.CHANNEL, unit="a.u."),
            seed.calibrated_axis("y", enums.AxisType.SPACE, unit="micrometer"),
            seed.calibrated_axis("x", enums.AxisType.SPACE, unit="micrometer"),
        ],
        scale=[1.0, 0.325, 0.325],
    )
    lens = await seed.create_lens(authenticated_context, dataset, slices=[])

    scene = await _adopt(authenticated_context, physical, "PhysicalSpace")
    assert scene["worldCoordinateSystem"]["kind"] == "PHYSICAL"

    made = await schema.execute(MAKE_LAYER, context_value=authenticated_context, variable_values={"input": {"scene": scene["id"], "lens": str(lens.pk), "intensityAxis": "c"}})
    assert not made.errors, made.errors

    result = await schema.execute(LAYER_PATHS, context_value=authenticated_context, variable_values={"id": scene["id"]})
    assert not result.errors, result.errors
    (layer,) = result.data["scene"]["layers"]

    assert layer["placement"] == "PLACED"
    hops = [(step["transformation"]["input"]["kind"], step["transformation"]["output"]["kind"]) for step in layer["pathToWorld"]]
    assert hops == [("INTRINSIC", "PHYSICAL")], "the calibration edge is the whole path"
    assert all(step["inverted"] is False for step in layer["pathToWorld"])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_only_the_containers_tree_composes_in_an_owned_space(authenticated_context: HttpContext):
    """A derived child places through its fact chain; an unrelated dataset has no way in.

    Registrations land exclusively on SHARED spaces, so an owned root composes exactly
    the container's fact tree -- foreign data is a category error there, and the
    `placeableIn` set agrees with the per-layer refusal.
    """
    parent = await seed.create_adataset(authenticated_context, "Parent")
    child = await seed.create_adataset(authenticated_context, "Crop")
    stranger = await seed.create_adataset(authenticated_context, "Stranger")

    def derive():
        # The child's primary (and only) derivation: a fact edge child -> parent.
        parent_intrinsic = parent.intrinsic_coordinate_system
        models.Transformation.objects.create(
            kind=enums.TransformKindChoices.IDENTITY.value,
            input=child.intrinsic_coordinate_system,
            output=parent_intrinsic,
            organization=authenticated_context.request.organization,
        )
        return parent_intrinsic

    parent_intrinsic = await sync_to_async(derive)()
    scene_data = await _adopt(authenticated_context, parent_intrinsic, "ParentSpace")

    child_lens = await seed.create_lens(authenticated_context, child, slices=[])
    made = await schema.execute(MAKE_LAYER, context_value=authenticated_context, variable_values={"input": {"scene": scene_data["id"], "lens": str(child_lens.pk), "intensityAxis": "c"}})
    assert not made.errors, made.errors

    stranger_lens = await seed.create_lens(authenticated_context, stranger, slices=[])
    refused = await schema.execute(MAKE_LAYER, context_value=authenticated_context, variable_values={"input": {"scene": scene_data["id"], "lens": str(stranger_lens.pk), "intensityAxis": "c"}})
    assert refused.errors, "nothing relates the stranger to this space, so its layer is refused"

    def placeable() -> set[int]:
        return graph_logic.placeable_lens_dataset_ids(models.Scene.objects.get(pk=scene_data["id"]))

    dataset_ids = await sync_to_async(placeable)()
    assert parent.pk in dataset_ids, "the container itself seeds the placeable set"
    assert child.pk in dataset_ids, "its derivation child arrives through the fact chain"
    assert stranger.pk not in dataset_ids


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_the_container_is_undeletable_while_a_scene_is_rooted_in_its_space(authenticated_context: HttpContext):
    """Scene.world is RESTRICT for owned roots exactly as for shared spaces: delete the scene first."""
    dataset = await seed.create_adataset(authenticated_context, "Pinned")
    intrinsic = await sync_to_async(lambda: dataset.intrinsic_coordinate_system)()

    scene_data = await _adopt(authenticated_context, intrinsic, "Holder")

    with pytest.raises(RestrictedError):
        await sync_to_async(dataset.delete)()

    def release_and_delete() -> None:
        models.Scene.objects.get(pk=scene_data["id"]).delete()
        dataset.delete()

    await sync_to_async(release_and_delete)()
    assert not await sync_to_async(models.CoordinateSystem.objects.filter(pk=intrinsic.pk).exists)()
