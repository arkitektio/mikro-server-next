"""Scenes rooted directly at an owned coordinate system (RFC-6, resolved open question).

With walk-time choice gone, an owned root is correctness-safe: a scene can compose
straight over a dataset's INTRINSIC pixel grid or a PHYSICAL calibration, and nothing is
authored to make that work. The container's data is placed *by construction* (its fact tree
reaches its own space), only that container's tree can ever compose there (registrations land
exclusively on SHARED spaces), and the lifecycle is RESTRICT: the container is undeletable
while a scene is rooted in its space, exactly as a shared space is.

This is now the *only* way a dataset is staged. `createSceneFromDataset` used to mint a world
whose axes copied the dataset's physical space and author an identity edge into it -- a copy
of a space the dataset was already in. It is gone; the tests it carried live at the bottom of
this file.
"""

import pytest
from asgiref.sync import sync_to_async
from django.db.models import RestrictedError
from django.db.models.deletion import ProtectedError
from kante.context import HttpContext

from core import enums, models
from core.logic import graph as graph_logic
from mikro_server.schema import schema
from tests import seed


CREATE_SCENE = """
mutation CreateScene($input: CreateSceneInput!) {
  createScene(input: $input) {
    id name
    worldCoordinateSystem { id  residents { __typename } }
  }
}
"""

FROM_SYSTEM = """
mutation FromCS($input: CreateSceneFromCoordinateSystemInput!) {
  createSceneFromCoordinateSystem(input: $input) {
    id
    worldCoordinateSystem { id residents { __typename } registrations { id } }
    layers { id }
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
    assert [r["__typename"] for r in scene["worldCoordinateSystem"]["residents"]] == ["ADataset", "DataArray", "Lens"], "the scene roots in the space the dataset, its level 0 and its unsliced lens all live in"

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
    sliced_system = await sync_to_async(lambda: str(sliced.coordinate_system.pk))()
    hops = [(step["transformation"]["input"]["id"], step["transformation"]["output"]["id"]) for step in sliced_layer["pathToWorld"]]
    assert hops == [(sliced_system, str(intrinsic.pk))], "one hop: the lens' crop into the grid it slices"

    assert await sync_to_async(models.Transformation.objects.filter(output=intrinsic, input__lenses__isnull=True).count)() == 0, "no registration was authored anywhere"


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
    assert scene["worldCoordinateSystem"]["registrations"] == [], "nothing was registered into the grid: the data is in it by definition"
    assert await sync_to_async(models.Transformation.objects.count)() == before, "and the bootstrap authored no edge"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_scene_over_a_calibration_renders_at_physical_scale(authenticated_context: HttpContext):
    """Adopt the PHYSICAL space: the path is the calibration edge, forward, and nothing else.

    Nothing is minted and nothing is authored: pixel -> physical is the
    dataset's own fact, so the layer renders at physical scale with zero authored
    registrations.
    """
    dataset = await seed.create_adataset(authenticated_context, "Staged")
    physical = await seed.create_physical_space(
        authenticated_context,
        dataset,
        axes=[
            seed.physical_axis("c", enums.AxisType.CHANNEL, unit="a.u."),
            seed.physical_axis("y", enums.AxisType.SPACE, unit="micrometer"),
            seed.physical_axis("x", enums.AxisType.SPACE, unit="micrometer"),
        ],
        scale=[1.0, 0.325, 0.325],
    )
    lens = await seed.create_lens(authenticated_context, dataset, slices=[])

    scene = await _adopt(authenticated_context, physical, "PhysicalSpace")
    assert scene["worldCoordinateSystem"]["residents"] == [], "a calibrated space holds nothing; the scene roots in a frame"

    made = await schema.execute(MAKE_LAYER, context_value=authenticated_context, variable_values={"input": {"scene": scene["id"], "lens": str(lens.pk), "intensityAxis": "c"}})
    assert not made.errors, made.errors

    result = await schema.execute(LAYER_PATHS, context_value=authenticated_context, variable_values={"id": scene["id"]})
    assert not result.errors, result.errors
    (layer,) = result.data["scene"]["layers"]

    assert layer["placement"] == "PLACED"
    intrinsic_id = await sync_to_async(lambda: str(dataset.coordinate_system.pk))()
    hops = [(step["transformation"]["input"]["id"], step["transformation"]["output"]["id"]) for step in layer["pathToWorld"]]
    assert hops == [(intrinsic_id, str(physical.pk))], "the calibration edge is the whole path"
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
        return graph_logic.placeable_lens_dataset_ids(models.Scene.objects.get(pk=scene_data["id"]).world)

    dataset_ids = await sync_to_async(placeable)()
    assert parent.pk in dataset_ids, "the container itself seeds the placeable set"
    assert child.pk in dataset_ids, "its derivation child arrives through the fact chain"
    assert stranger.pk not in dataset_ids


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_the_container_is_undeletable_while_a_scene_is_rooted_in_its_space(authenticated_context: HttpContext):
    """The space a scene roots in is undeletable; the data that lives there is not.

    RFC-9 splits a guarantee that used to be one thing. `Scene.world` is still RESTRICT, so a
    space a scene composes over cannot be deleted -- and now `ADataset.coordinate_system` is
    PROTECT, so it cannot be deleted while the dataset lives there either. What is *gone* is
    the transitivity: deleting the dataset no longer cascades into the space, so it no longer
    trips the scene's RESTRICT.

    That is the honest outcome rather than a regression papered over. A scene is rooted in a
    *space*, not in a dataset; the space survives its residents, and a scene left composing
    over an emptied space is exactly what "the space outlives the data" means.
    """
    dataset = await seed.create_adataset(authenticated_context, "Pinned")
    intrinsic = await sync_to_async(lambda: dataset.coordinate_system)()

    await _adopt(authenticated_context, intrinsic, "Holder")

    # The space itself is pinned from both sides.
    with pytest.raises((RestrictedError, ProtectedError)):
        await sync_to_async(intrinsic.delete)()

    # The dataset is not: it moves out, and the space stays for the scene that roots in it.
    await sync_to_async(dataset.delete)()
    assert await sync_to_async(models.CoordinateSystem.objects.filter(pk=intrinsic.pk).exists)(), "the space outlives the data that lived in it"


# --- What a scene over a dataset's own space renders -------------------------------
#
# These moved here when `createSceneFromDataset` was deleted. They used to run against a
# minted world whose axes copied the dataset's; they now run against the space the dataset
# is already in, which is the whole point of the deletion -- the recipes never depended on
# the copy, only on the data's axes.

FROM_SYSTEM_GRAPH = """
mutation FromCS($input: CreateSceneFromCoordinateSystemInput!) {
  createSceneFromCoordinateSystem(input: $input) {
    id
    layers { id placement placementValidity pathToWorld { transformation { id } } }
  }
}
"""

DATASET_SCENES = """
query DatasetScenes($id: ID!) {
  adataset(id: $id) { id scenes { id name } }
}
"""


def _layer_of(dataset: models.ADataset) -> models.Layer:
    return models.Layer.objects.get(lens__dataset=dataset)


async def _stage_in_own_grid(ctx: HttpContext, dataset: models.ADataset, **policy) -> dict:
    """A scene over the dataset's own pixel grid -- the replacement for the deleted bootstrap."""
    intrinsic = await sync_to_async(lambda: dataset.intrinsic_coordinate_system)()
    result = await schema.execute(
        FROM_SYSTEM_GRAPH,
        context_value=ctx,
        variable_values={"input": {"coordinateSystem": str(intrinsic.pk), "policy": policy}},
    )
    assert not result.errors, result.errors
    return result.data["createSceneFromCoordinateSystem"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_data_in_its_own_space_is_placed_exactly(authenticated_context: HttpContext):
    """The inversion the mirror world used to hide: an empty path is VALIDATED, not UNKNOWN.

    Staging an uncalibrated dataset used to mint a world under assumed micrometre units and
    author an identity edge into it, which honestly wore UNKNOWN -- the units were a guess.
    Over the dataset's own grid there is no guess and no edge: the data is in that space by
    definition, the path is empty, and an empty path is exact by construction.
    """
    dataset = await seed.create_adataset(authenticated_context, "Uncalibrated")
    before = await sync_to_async(models.Transformation.objects.count)()

    scene = await _stage_in_own_grid(authenticated_context, dataset)

    (layer,) = scene["layers"]
    assert layer["placement"] == "PLACED"
    assert layer["pathToWorld"] == [], "the lens' space IS the world: there is nothing to compose"
    assert layer["placementValidity"] == "VALIDATED", "nothing was assumed, so nothing wears UNKNOWN"
    assert await sync_to_async(models.Transformation.objects.count)() == before, "and no edge was invented to say so"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_three_flat_channels_infer_rgb(authenticated_context: HttpContext):
    """A 2D dataset with exactly three channels reads as a photograph: one additive red/green/blue blend."""
    dataset = await seed.create_adataset(authenticated_context, "Slide", shapes=[[3, 64, 64]])

    await _stage_in_own_grid(authenticated_context, dataset)

    layer = await sync_to_async(_layer_of)(dataset)
    root = layer.render_graph["root"]
    assert root["label"] == "rgb"
    assert [child["transfer"]["colormap"] for child in root["children"]] == ["red", "green", "blue"]
    assert layer.blending == enums.Blending.NORMAL.value, "a photograph composites over the scene, it does not sum into it"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_z_stack_infers_a_volume_and_channels_get_distinct_hues(authenticated_context: HttpContext):
    """Depth wins over channel count: a 3-channel confocal stack is a volume, not a photograph."""
    dataset = await seed.create_adataset(
        authenticated_context,
        "Stack",
        axes=[
            seed.axis("c", enums.AxisType.CHANNEL),
            seed.axis("z", enums.AxisType.SPACE),
            seed.axis("y", enums.AxisType.SPACE),
            seed.axis("x", enums.AxisType.SPACE),
        ],
        shapes=[[3, 16, 64, 64]],
    )

    await _stage_in_own_grid(authenticated_context, dataset)

    layer = await sync_to_async(_layer_of)(dataset)
    root = layer.render_graph["root"]
    (projection,) = root["children"]
    assert projection["kind"] == "projection"
    assert projection["mode"] == "mip"
    # Not red/green/blue: these are fluorescence channels, in distinguishable hues.
    assert [child["transfer"]["colormap"] for child in projection["children"]] == ["green", "magenta", "cyan"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_the_policy_names_the_recipe_inference_cannot_reach(authenticated_context: HttpContext):
    """LABEL is chosen, never inferred from structure -- and `policy.kind` is where it is chosen.

    Nothing about an array distinguishes a label map from an image, so inference reaches
    LABEL only through a derivation declared CATEGORIZED. An imported mask has no such
    derivation, and this is its one-call path.
    """
    dataset = await seed.create_adataset(authenticated_context, "Mask", axes=seed.YX_AXES, shapes=[[64, 64]])

    await _stage_in_own_grid(authenticated_context, dataset, kind="LABEL")

    layer = await sync_to_async(_layer_of)(dataset)
    (child,) = layer.render_graph["root"]["children"]
    assert child["transfer"]["categorical"] is True
    assert layer.blending == enums.Blending.NORMAL.value


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_dataset_finds_its_scenes_by_walking_the_graph(authenticated_context: HttpContext):
    """`ADataset.scenes` is a layers->lens->dataset walk, never a column.

    There is deliberately no `Scene.dataset` FK: which scenes show a dataset is already
    answerable from the graph, and a stored copy would be free to disagree with it.
    """
    dataset = await seed.create_adataset(authenticated_context, "Shown")
    scene = await _stage_in_own_grid(authenticated_context, dataset)

    result = await schema.execute(DATASET_SCENES, context_value=authenticated_context, variable_values={"id": str(dataset.pk)})
    assert not result.errors, result.errors
    assert [s["id"] for s in result.data["adataset"]["scenes"]] == [scene["id"]]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_unmappable_derivation_still_composes_over_its_own_space(authenticated_context: HttpContext):
    """An UNMAPPABLE derivation denies correspondence with its *source*, not with its own space.

    A phasor-like reduction has no point correspondence with the image it came from, so no
    walk may cross that edge. It is still perfectly placeable in the space its own pixels
    live in -- by construction, with nothing authored either way.
    """
    source = await seed.create_adataset(authenticated_context, "Source", shapes=[[2, 64, 64]])
    source_lens = await seed.create_lens(authenticated_context, source)
    derived = await seed.create_adataset(authenticated_context, "Phasorish", axes=seed.YX_AXES, shapes=[[64, 64]])

    def derivation() -> None:
        # `space`, not `coordinate_system`: an unsliced lens owns no system, its space
        # is the source dataset's intrinsic system.
        graph_logic.write_relation_edge(
            name="Phasorish <- Source",
            input_system=derived.intrinsic_coordinate_system,
            output_system=source_lens.space,
            kind=enums.TransformKindChoices.UNMAPPABLE.value,
            reason="the geometry does not survive the reduction",
            ctx=seed._creation(authenticated_context),
        )

    await sync_to_async(derivation)()

    scene = await _stage_in_own_grid(authenticated_context, derived)

    (layer,) = scene["layers"]
    assert layer["pathToWorld"] == [], "its own space places it; the refused edge is not on the way"
    intrinsic = await sync_to_async(lambda: derived.intrinsic_coordinate_system)()
    assert await models.Transformation.objects.filter(output=intrinsic).acount() == 0, "nothing was registered into the grid"
    assert await models.Transformation.objects.filter(input=intrinsic, kind=enums.TransformKindChoices.UNMAPPABLE.value).aexists(), "and the derivation edge is untouched"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_staging_a_physical_space_reaches_the_data_through_the_calibration(authenticated_context: HttpContext):
    """The other half of the documented staging path: point the builder at a *physical* space.

    Over the intrinsic grid the builder takes its `residents_exist` branch -- the data is
    right there. A calibrated space holds nothing, so it takes the *registrations* branch and
    has to reach the dataset by following the calibration edge back (`dataset_behind`). Both
    are named in `createSceneFromCoordinateSystem`'s description as the way to stage a
    dataset, so both need to work; only the first was covered.
    """
    dataset = await seed.create_adataset(authenticated_context, "Staged")
    physical = await seed.create_physical_space(
        authenticated_context,
        dataset,
        axes=[
            seed.physical_axis("c", enums.AxisType.CHANNEL, unit="a.u."),
            seed.physical_axis("y", enums.AxisType.SPACE, unit="micrometer"),
            seed.physical_axis("x", enums.AxisType.SPACE, unit="micrometer"),
        ],
        scale=[1.0, 0.325, 0.325],
    )
    before = await sync_to_async(models.Transformation.objects.count)()

    result = await schema.execute(FROM_SYSTEM_GRAPH, context_value=authenticated_context, variable_values={"input": {"coordinateSystem": str(physical.pk), "policy": {}}})
    assert not result.errors, result.errors
    scene = result.data["createSceneFromCoordinateSystem"]

    (layer,) = scene["layers"]
    assert layer["placement"] == "PLACED"
    assert len(layer["pathToWorld"]) == 1, "the calibration edge is the whole path -- the data renders at physical scale"
    assert await sync_to_async(models.Transformation.objects.count)() == before, "and nothing was authored to make that true"
