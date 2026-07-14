"""One call from a dataset to something a client can draw.

`createSceneFromDataset` is orchestration sugar, and these tests hold it to that: every
row it writes is an ordinary scene, lens, layer or edge that the existing machinery
(`ensure_registered`, the placement BFS, `pathToWorld`) then treats like any other.
There is deliberately no `Scene.dataset` column -- the dataset's `scenes` field is a walk
over its lenses' layers -- so the tests assert facts of the graph, never a stored anchor.

The load-bearing behaviors: a calibrated dataset renders at *physical* scale because the
assumed edge leaves the PHYSICAL system (whose axes the world mirrors), an uncalibrated
one falls back to the classic pixel-identity assumption, the default layer's recipe is
inferred from the axes (never LABEL), and a dataset whose derivation is UNMAPPABLE gets
its scene but no fabricated placement.
"""

import pytest
from asgiref.sync import sync_to_async
from kante.context import HttpContext

from core import enums, models
from core.logic import graph as graph_logic
from mikro_server.schema import schema
from tests import seed

BOOTSTRAP = """
mutation Bootstrap($input: CreateSceneFromDatasetInput!) {
  createSceneFromDataset(input: $input) {
    id
    name
    worldCoordinateSystem { id kind axes { name type unit } }
    coordinateTransformations { id kind name }
    layers {
      id
      kind
      pathToWorld {
        inverted
        transformation { id kind inputAxes outputAxes }
      }
    }
  }
}
"""

DATASET_SCENES = """
query DatasetScenes($id: ID!) {
  adataset(id: $id) { id scenes { id name } }
}
"""


async def _bootstrap(ctx: HttpContext, dataset: models.ADataset, **input) -> dict:
    result = await schema.execute(
        BOOTSTRAP,
        context_value=ctx,
        variable_values={"input": {"dataset": str(dataset.pk), **input}},
    )
    assert not result.errors, result.errors
    return result.data["createSceneFromDataset"]


def _layer_of(dataset: models.ADataset) -> models.Layer:
    return models.Layer.objects.get(lens__dataset=dataset)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_calibrated_dataset_is_placed_at_physical_scale(authenticated_context: HttpContext):
    """The world mirrors the calibration's navigable axes, and the placement path runs through it.

    That is the whole point of authoring the assumed edge from the PHYSICAL system rather
    than letting `ensure_registered` pin intrinsic: the calibration's scale is *on* the
    path, so the data renders in micrometres without anyone composing a unit conversion.
    """
    dataset = await seed.create_adataset(authenticated_context, "Calibrated", shapes=[[2, 64, 64]])
    await seed.create_calibration(
        authenticated_context,
        dataset,
        axes=[
            seed.calibrated_axis("c", enums.AxisType.CHANNEL, "a.u."),
            seed.calibrated_axis("y", enums.AxisType.SPACE, "micrometer"),
            seed.calibrated_axis("x", enums.AxisType.SPACE, "micrometer"),
        ],
        scale=[1.0, 0.325, 0.325],
    )

    scene = await _bootstrap(authenticated_context, dataset)

    # The world is the calibration's navigable subspace: y and x in micrometres. The
    # channel axis stays out -- a channel is sampled per layer, not a place in a world.
    axes = scene["worldCoordinateSystem"]["axes"]
    assert [(axis["name"], axis["unit"]) for axis in axes] == [("y", "micrometer"), ("x", "micrometer")]

    # One image layer, and it has a place: the path exists and walks the calibration's
    # SCALE edge on its way to the assumed BY_DIMENSION registration.
    (layer,) = scene["layers"]
    assert layer["kind"] == "IMAGE"
    kinds = [step["transformation"]["kind"] for step in layer["pathToWorld"]]
    assert "SCALE" in kinds, f"the calibration is not on the placement path: {kinds}"
    assert kinds[-1] == "BY_DIMENSION", f"the path should end at the assumed registration: {kinds}"

    # The assumed edge really leaves the PHYSICAL system, and wears its badge in the name.
    edge = await sync_to_async(lambda: models.Transformation.objects.select_related("input").get(output__scene__pk=scene["id"]))()
    assert edge.input.kind == enums.CoordinateSystemKindChoices.PHYSICAL.value
    assert edge.name.endswith("(assumed)")

    # And nothing anchored the scene to the dataset: finding it back is a graph walk.
    found = await schema.execute(DATASET_SCENES, context_value=authenticated_context, variable_values={"id": str(dataset.pk)})
    assert not found.errors, found.errors
    assert [entry["id"] for entry in found.data["adataset"]["scenes"]] == [scene["id"]]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_uncalibrated_dataset_falls_back_to_the_pixel_identity(authenticated_context: HttpContext):
    """No calibration: the world mirrors the pixel axes under default units, and `ensure_registered` pins intrinsic."""
    dataset = await seed.create_adataset(authenticated_context, "Bare", axes=seed.YX_AXES, shapes=[[64, 64]])

    scene = await _bootstrap(authenticated_context, dataset)

    axes = scene["worldCoordinateSystem"]["axes"]
    assert [(axis["name"], axis["unit"]) for axis in axes] == [("y", "micrometer"), ("x", "micrometer")]

    (layer,) = scene["layers"]
    assert layer["pathToWorld"] is not None
    edge = await sync_to_async(lambda: models.Transformation.objects.select_related("input").get(output__scene__pk=scene["id"]))()
    assert edge.input.kind == enums.CoordinateSystemKindChoices.INTRINSIC.value


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_three_flat_channels_infer_rgb(authenticated_context: HttpContext):
    """A 2D dataset with exactly three channels reads as a photograph: one additive red/green/blue blend."""
    dataset = await seed.create_adataset(authenticated_context, "Slide", shapes=[[3, 64, 64]])

    await _bootstrap(authenticated_context, dataset)

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

    await _bootstrap(authenticated_context, dataset)

    layer = await sync_to_async(_layer_of)(dataset)
    root = layer.render_graph["root"]
    (projection,) = root["children"]
    assert projection["kind"] == "projection"
    assert projection["mode"] == "mip"
    # Not red/green/blue: these are fluorescence channels, in distinguishable hues.
    assert [child["transfer"]["colormap"] for child in projection["children"]] == ["green", "magenta", "cyan"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_label_is_override_only(authenticated_context: HttpContext):
    """Nothing structural distinguishes a label map from an image, so LABEL is chosen, never inferred."""
    dataset = await seed.create_adataset(authenticated_context, "Mask", axes=seed.YX_AXES, shapes=[[64, 64]])

    await _bootstrap(authenticated_context, dataset, kind="LABEL")

    layer = await sync_to_async(_layer_of)(dataset)
    (child,) = layer.render_graph["root"]["children"]
    assert child["transfer"]["categorical"] is True
    assert layer.blending == enums.Blending.NORMAL.value


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_unmappable_derivation_gets_a_scene_but_no_fabricated_placement(authenticated_context: HttpContext):
    """The scene exists and the layer renders in its own frame; no edge reaches the world.

    Even though the dataset has a calibration whose axes are called y and x -- exactly the
    name-coincidence `ensure_registered` refuses to turn into a placement -- the bootstrap
    must refuse it too, or it becomes the back door around that rule.
    """
    source = await seed.create_adataset(authenticated_context, "Source", shapes=[[2, 64, 64]])
    source_lens = await seed.create_lens(authenticated_context, source)

    derived = await seed.create_adataset(authenticated_context, "Phasorish", axes=seed.YX_AXES, shapes=[[64, 64]])
    await seed.create_calibration(
        authenticated_context,
        derived,
        axes=[
            seed.calibrated_axis("y", enums.AxisType.SPACE, "micrometer"),
            seed.calibrated_axis("x", enums.AxisType.SPACE, "micrometer"),
        ],
        scale=[0.5, 0.5],
    )

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

    scene = await _bootstrap(authenticated_context, derived)

    (layer,) = scene["layers"]
    assert layer["pathToWorld"] is None
    assert scene["coordinateTransformations"] == [], "no membership edge may exist: there is nothing true it could say"
    exists = await models.Transformation.objects.filter(output__scene__pk=scene["id"]).aexists()
    assert not exists, "an edge into this world fabricates the correspondence the derivation denies"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_rerunning_makes_a_second_ordinary_scene(authenticated_context: HttpContext):
    """No default-scene flag, no uniqueness: a rerun is just another composition, and both are found by the walk."""
    dataset = await seed.create_adataset(authenticated_context, "Twice", shapes=[[2, 64, 64]])

    first = await _bootstrap(authenticated_context, dataset)
    second = await _bootstrap(authenticated_context, dataset, name="Twice (again)")

    assert first["id"] != second["id"]
    found = await schema.execute(DATASET_SCENES, context_value=authenticated_context, variable_values={"id": str(dataset.pk)})
    assert not found.errors, found.errors
    assert {entry["id"] for entry in found.data["adataset"]["scenes"]} == {first["id"], second["id"]}


def test_ingest_carries_the_same_sugar():
    """`createAdataset` takes the bootstrap spec inline, so ingest is one round trip; the SDL is the contract."""
    sdl = schema.as_str()
    definition = sdl[sdl.find("input CreateADatasetInput ") : sdl.find("\n}", sdl.find("input CreateADatasetInput "))]
    assert "bootstrapScene: BootstrapSceneInput" in definition
