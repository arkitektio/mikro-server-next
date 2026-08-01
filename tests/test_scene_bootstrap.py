"""One call from a dataset to something a client can draw.

`createSceneFromDataset` is orchestration sugar, and these tests hold it to that: every
row it writes is an ordinary scene, lens, layer or edge that the existing machinery
(the placement BFS, `pathToWorld`) then treats like any other. There is deliberately no
`Scene.dataset` column -- the dataset's `scenes` field is a walk over its lenses' layers
-- so the tests assert facts of the graph, never a stored anchor.

The load-bearing behaviors: a calibrated dataset renders at *physical* scale because the
mirror edge leaves the PHYSICAL system (whose axes the world mirrors) and is VALIDATED --
exact by construction; an uncalibrated one falls back to the classic pixel-identity
assumption (UNKNOWN); the default layer's recipe is inferred from the axes (never LABEL);
and a derived dataset -- UNMAPPABLE derivation included -- is placed in its *own* dedicated
scene, because the world was created to mirror its own axes and the derivation edge speaks
about the parent's space, not this one.
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
    worldCoordinateSystem { id  axes { name type unit } registrations { id kind name } }
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


def _anchor_facts(scene_id):
    """The scene's anchor edge, plus the two residence questions, resolved in one sync hop.

    `datasets.exists()` is a query, so it cannot be asked from the async test body -- and
    "does a dataset live in the space this edge sets out from" is exactly what used to be
    `kind == INTRINSIC` versus `PHYSICAL`.
    """
    edge = models.Transformation.objects.select_related("input").get(output__scenes__pk=scene_id)
    return edge, edge.input.datasets.exists(), edge.input.axes.filter(unit__isnull=False).exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_calibrated_dataset_is_placed_at_physical_scale(authenticated_context: HttpContext):
    """The world mirrors the calibration's navigable axes, and the placement path runs through it.

    That is the whole point of authoring the mirror edge from the PHYSICAL system rather
    than from intrinsic: the calibration's scale is *on* the path, so the data renders in
    micrometres without anyone composing a unit conversion. And because the world was
    built to mirror those very axes, the identity is exact by construction -- VALIDATED,
    not assumed.
    """
    dataset = await seed.create_adataset(authenticated_context, "Calibrated", shapes=[[2, 64, 64]])
    await seed.create_physical_space(
        authenticated_context,
        dataset,
        axes=[
            seed.physical_axis("c", enums.AxisType.CHANNEL, "a.u."),
            seed.physical_axis("y", enums.AxisType.SPACE, "micrometer"),
            seed.physical_axis("x", enums.AxisType.SPACE, "micrometer"),
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
    assert kinds[-1] == "BY_DIMENSION", f"the path should end at the mirror registration: {kinds}"

    # The mirror edge really leaves the PHYSICAL system, and is exact by construction:
    # the world was built to mirror those axes, so nothing about it is assumed.
    edge, anchored_in_dataset_space, anchor_has_units = await sync_to_async(_anchor_facts)(scene["id"])
    assert not anchored_in_dataset_space and anchor_has_units, "the mirror sets out from the calibrated space"
    assert edge.name.endswith("(mirror)")
    assert edge.validity == enums.PlacementValidityChoices.VALIDATED.value

    # And nothing anchored the scene to the dataset: finding it back is a graph walk.
    found = await schema.execute(DATASET_SCENES, context_value=authenticated_context, variable_values={"id": str(dataset.pk)})
    assert not found.errors, found.errors
    assert [entry["id"] for entry in found.data["adataset"]["scenes"]] == [scene["id"]]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_uncalibrated_dataset_falls_back_to_the_pixel_identity(authenticated_context: HttpContext):
    """No calibration: the world mirrors the pixel axes under default units, and the edge pins intrinsic.

    One pixel, one micrometre -- an assumed interpretation, not a measured one, so unlike
    the calibrated mirror this edge keeps the UNKNOWN badge.
    """
    dataset = await seed.create_adataset(authenticated_context, "Bare", axes=seed.YX_AXES, shapes=[[64, 64]])

    scene = await _bootstrap(authenticated_context, dataset)

    axes = scene["worldCoordinateSystem"]["axes"]
    assert [(axis["name"], axis["unit"]) for axis in axes] == [("y", "micrometer"), ("x", "micrometer")]

    (layer,) = scene["layers"]
    assert layer["pathToWorld"] is not None
    edge, anchored_in_dataset_space, anchor_has_units = await sync_to_async(_anchor_facts)(scene["id"])
    assert anchored_in_dataset_space, "the mirror sets out from the dataset's own space"
    assert edge.name.endswith("(assumed)")
    assert edge.validity == enums.PlacementValidityChoices.UNKNOWN.value


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
async def test_an_unmappable_derivation_is_placed_in_its_own_dedicated_scene(authenticated_context: HttpContext):
    """A phasor-like dataset bootstraps placed: the mirror edge is about ITS space, not its parent's.

    An UNMAPPABLE derivation denies that any point of this dataset corresponds to a point
    of its *source* -- it says nothing about a world created to mirror the dataset's own
    axes. The bootstrap therefore places it like any other dataset, from its calibration,
    exact by construction. What stays true: no edge relates it to its source's spaces.
    """
    source = await seed.create_adataset(authenticated_context, "Source", shapes=[[2, 64, 64]])
    source_lens = await seed.create_lens(authenticated_context, source)

    derived = await seed.create_adataset(authenticated_context, "Phasorish", axes=seed.YX_AXES, shapes=[[64, 64]])
    await seed.create_physical_space(
        authenticated_context,
        derived,
        axes=[
            seed.physical_axis("y", enums.AxisType.SPACE, "micrometer"),
            seed.physical_axis("x", enums.AxisType.SPACE, "micrometer"),
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
    assert layer["pathToWorld"] is not None, "in its own dedicated scene the mirror identity is honest"
    edge, anchored_in_dataset_space, anchor_has_units = await sync_to_async(_anchor_facts)(scene["id"])
    assert not anchored_in_dataset_space and anchor_has_units, "the mirror sets out from the calibrated space"
    assert edge.validity == enums.PlacementValidityChoices.VALIDATED.value
    # Exactly one edge reaches this world -- the mirror. The UNMAPPABLE derivation is
    # untouched, and nothing new relates this data to its source's spaces.
    assert await models.Transformation.objects.filter(output__scenes__pk=scene["id"]).acount() == 1
    assert await models.Transformation.objects.filter(input=derived.intrinsic_coordinate_system, kind=enums.TransformKindChoices.UNMAPPABLE.value).aexists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_mappable_derivation_also_bootstraps_placed(authenticated_context: HttpContext):
    """A derived dataset (e.g. a deconvolution) bootstraps placed via its own anchor, not its root's.

    The old rule ("never pin derived data") was about shared scenes, where a one-hop edge
    would outrank the lineage truth. A bootstrapped scene is dedicated: the world mirrors
    this dataset's axes, so registering it directly is the truth.
    """
    source = await seed.create_adataset(authenticated_context, "Raw", axes=seed.YX_AXES, shapes=[[64, 64]])
    source_lens = await seed.create_lens(authenticated_context, source)

    derived = await seed.create_adataset(authenticated_context, "Deconvolved", axes=seed.YX_AXES, shapes=[[64, 64]])

    def derivation() -> None:
        graph_logic.write_relation_edge(
            name="Deconvolved <- Raw",
            input_system=derived.intrinsic_coordinate_system,
            output_system=source_lens.space,
            kind=enums.TransformKindChoices.IDENTITY.value,
            ctx=seed._creation(authenticated_context),
        )

    await sync_to_async(derivation)()

    scene = await _bootstrap(authenticated_context, derived)

    (layer,) = scene["layers"]
    assert layer["pathToWorld"] is not None
    edge, anchored_in_dataset_space, anchor_has_units = await sync_to_async(_anchor_facts)(scene["id"])
    assert anchored_in_dataset_space, "no calibration, so the mirror pins the dataset's own pixels"


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
    """`createADataset` takes the bootstrap spec inline, so ingest is one round trip; the SDL is the contract."""
    sdl = schema.as_str()
    definition = sdl[sdl.find("input CreateADatasetInput ") : sdl.find("\n}", sdl.find("input CreateADatasetInput "))]
    assert "bootstrapScene: BootstrapSceneInput" in definition
