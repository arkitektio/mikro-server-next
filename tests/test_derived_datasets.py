"""A derived dataset is placed by where its source is, not by an assumption.

A deconvolution, a segmentation, a projection, a resample: none of them is a fresh
acquisition, and none of them sits anywhere on its own account. Its pixels stand in a
definite relation to the lens they were computed from, and that relation is a spatial fact
-- so it is an edge, like the pyramid scale and the lens crop and the calibration, and not
a label describing one. Recorded that way, the derived dataset inherits its source's
placement: refine the source's registration and the derived data moves with it, because
there is only one copy of the fact.

These tests pin the two things that make the edge more than decoration: the placement
search must be able to *walk* it (it used to dead-end the moment it left the dataset), and
the auto-registration must not paper over it with an assumed identity placement that, being
one hop from world against the lineage's several, would outrank the truth forever.
"""

from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from datalayer.models import ZarrStore
from kante.context import HttpContext

from core import enums, models
from mikro_server.schema import schema
from tests import seed

CREATE_SCENE = """
mutation CreateScene($input: CreateSceneInput!) {
  createScene(input: $input) {
    id
    worldCoordinateSystem { id }
  }
}
"""

REGISTER = """
mutation Register($input: CreateTransformationInput!) {
  createTransformation(input: $input) { id kind }
}
"""

MAKE_LAYER = """
mutation Make($input: CreateIntensityLayerInput!) {
  createIntensityLayer(input: $input) { id }
}
"""

PLACEMENT = """
query Placement($id: ID!) {
  scene(id: $id) {
    layers {
      id
      pathToWorld {
        inverted
        transformation {
          id kind inputAxes outputAxes
          input { id  }
          output { id residents { __typename } }
        }
      }
    }
    registrations { id kind name }
  }
}
"""

DERIVED = """
query Derived($id: ID!) {
  adataset(id: $id) {
    id
    derivedFrom { id kind inputAxes outputAxes output { id  } }
  }
}
"""

DERIVED_DATASETS = """
query Children($id: ID!) {
  adataset(id: $id) {
    id
    derivedDatasets { id name }
  }
}
"""

_AFFINE_3D = [
    [1.0, 0.0, 0.0, 5.0],
    [0.0, 1.0, 0.0, 5.0],
    [0.0, 0.0, 1.0, 0.0],
]


async def _derive(ctx: HttpContext, name: str, *, axes, shape, lens=None, entries=None, transform=None, valueRelation=None):
    """Create a dataset through the real mutation, stating the lens(es) it was computed from.

    Either one `lens` plus its nested `transform` dict (and optional `valueRelation`),
    or explicit `entries` for a fusion.
    """
    store = await ZarrStore.objects.acreate(
        organization=ctx.request.organization,
        key=f"derived-{name}",
        bucket="zarr",
        shape=shape,
        chunks=shape,
        version="3",
        dtype="uint8",
        populated=True,
    )

    if entries is None:
        entry = {"lens": str(lens.pk)}
        if transform is not None:
            entry["transform"] = transform
        if valueRelation is not None:
            entry["valueRelation"] = valueRelation
        entries = [entry]

    # fill_info() reads zarr metadata from S3; stub it so the pre-set shape stays intact.
    with patch("datalayer.models.ZarrStore.fill_info", return_value=None):
        return await schema.execute(
            """
            mutation Derive($input: CreateADatasetInput!) {
              createADataset(input: $input) { id name derivedFrom { id kind inputAxes outputAxes valueRelation } }
            }
            """,
            context_value=ctx,
            variable_values={
                "input": {
                    "name": name,
                    "data": str(store.id),
                    "scales": [],
                    "axes": [{"name": axis.name, "type": axis.type.value} for axis in axes],
                    "derivedFrom": entries,
                }
            },
        )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_derived_dataset_walks_to_world_through_its_source(authenticated_context: HttpContext):
    """The path runs through the source's systems, not around them.

    This is the assertion the whole change exists for. The placement search partitions its
    edge universe per dataset, so before the lineage closure the walk crossed the
    derivation edge into the source's lens system and then **dead-ended** -- the source's
    own lens->array->intrinsic edges live in the source's bucket, which was never merged.
    `pathToWorld` came back null for data that is perfectly well placed.
    """
    source = await seed.create_adataset(authenticated_context, "Source")  # (c, y, x)
    source_lens = await seed.create_lens(authenticated_context, source, slices=[])

    scene_result = await schema.execute(CREATE_SCENE, context_value=authenticated_context, variable_values={"input": {"name": "Sc", "axes": [{"name": "z", "type": "SPACE", "unit": "micrometer"}, {"name": "y", "type": "SPACE", "unit": "micrometer"}, {"name": "x", "type": "SPACE", "unit": "micrometer"}]}})
    assert not scene_result.errors, scene_result.errors
    scene_id = scene_result.data["createScene"]["id"]
    world_id = scene_result.data["createScene"]["worldCoordinateSystem"]["id"]

    # The SOURCE is registered into the scene. The derived dataset never is.
    source_intrinsic = await sync_to_async(lambda: source.intrinsic_coordinate_system)()
    registered = await schema.execute(
        REGISTER,
        context_value=authenticated_context,
        variable_values={"input": {"input": str(source_intrinsic.pk), "output": world_id, "transform": {"kind": "AFFINE", "affine": _AFFINE_3D}}},
    )
    assert not registered.errors, registered.errors

    # A deconvolution: same grid, so the derivation is an identity.
    derived = await _derive(authenticated_context, "Deconvolved", lens=source_lens, axes=seed.SIMPLE_AXES, shape=[3, 64, 64], transform={"kind": "IDENTITY"})
    assert not derived.errors, derived.errors
    derived_id = derived.data["createADataset"]["id"]

    derived_dataset = await sync_to_async(models.ADataset.objects.get)(pk=derived_id)
    derived_lens = await seed.create_lens(authenticated_context, derived_dataset, slices=[])

    made = await schema.execute(MAKE_LAYER, context_value=authenticated_context, variable_values={"input": {"scene": scene_id, "lens": str(derived_lens.pk), "intensityAxis": "c"}})
    assert not made.errors, made.errors

    placement = await schema.execute(PLACEMENT, context_value=authenticated_context, variable_values={"id": scene_id})
    assert not placement.errors, placement.errors

    layer = placement.data["scene"]["layers"][0]
    path = layer["pathToWorld"]
    assert path is not None, "a derived dataset is placed by its source; the walk must cross the derivation edge"

    # It ends in the source's registration -- the derived data inherits it.
    assert path[-1]["transformation"]["output"]["residents"] == [], "the walk ends in a space nothing lives in: a world"
    inputs = [step["transformation"]["input"]["id"] for step in path]
    assert str(source_intrinsic.pk) in inputs, "the walk passes through the source dataset's own space"

    # And no assumed registration was fabricated for the derived dataset.
    names = [edge["name"] or "" for edge in placement.data["scene"]["registrations"]]
    assert not any("assumed" in name for name in names), f"the derived dataset must inherit, not be pinned: {names}"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_unregistered_derived_dataset_is_rejected_and_placed_through_its_source(authenticated_context: HttpContext):
    """When nothing is registered yet, the layer is refused -- and registering the SOURCE fixes it.

    Nothing fabricates a placement any more. The honest fix is the one a client authors
    about the data the pixels came from: register the source, and the derived layer
    reaches world through its derivation edge. Registering the derived dataset directly
    would also produce a path, but it would be a second, shorter claim that outranks the
    lineage under the shortest-path BFS -- which is exactly why the server never writes
    one on its own.
    """
    source = await seed.create_adataset(authenticated_context, "Source")  # (c, y, x)
    source_lens = await seed.create_lens(authenticated_context, source, slices=[])

    derived = await _derive(authenticated_context, "Deconvolved", lens=source_lens, axes=seed.SIMPLE_AXES, shape=[3, 64, 64], transform={"kind": "IDENTITY"})
    assert not derived.errors, derived.errors
    derived_dataset = await sync_to_async(models.ADataset.objects.get)(pk=derived.data["createADataset"]["id"])
    derived_lens = await seed.create_lens(authenticated_context, derived_dataset, slices=[])

    scene_result = await schema.execute(CREATE_SCENE, context_value=authenticated_context, variable_values={"input": {"name": "Sc"}})
    assert not scene_result.errors, scene_result.errors
    scene_id = scene_result.data["createScene"]["id"]

    variables = {"input": {"scene": scene_id, "lens": str(derived_lens.pk), "intensityAxis": "c"}}
    refused = await schema.execute(MAKE_LAYER, context_value=authenticated_context, variable_values=variables)
    assert refused.errors, "nothing places the derived dataset yet, so the layer is refused"
    assert "createTransformation" in str(refused.errors[0])

    # Register the SOURCE -- the claim that is actually true -- and retry.
    scene = await sync_to_async(models.Scene.objects.get)(pk=scene_id)
    await seed.register_into_scene(authenticated_context, scene, source)

    made = await schema.execute(MAKE_LAYER, context_value=authenticated_context, variable_values=variables)
    assert not made.errors, made.errors

    def registrations() -> list[models.Transformation]:
        world_id = models.Scene.objects.get(pk=scene_id).world_id
        return list(models.Transformation.objects.filter(parent__isnull=True, output_id=world_id).select_related("input"))

    edges = await sync_to_async(registrations)()
    assert len(edges) == 1, f"the layer mutation wrote no edge of its own: {edges}"

    source_intrinsic = await sync_to_async(lambda: source.intrinsic_coordinate_system)()
    derived_intrinsic = await sync_to_async(lambda: derived_dataset.intrinsic_coordinate_system)()
    assert edges[0].input_id == source_intrinsic.pk
    assert edges[0].input_id != derived_intrinsic.pk

    # The derived layer reaches world -- through its source, not around it.
    placement = await schema.execute(PLACEMENT, context_value=authenticated_context, variable_values={"id": scene_id})
    assert not placement.errors, placement.errors
    path = placement.data["scene"]["layers"][0]["pathToWorld"]
    assert path is not None
    assert path[-1]["transformation"]["output"]["residents"] == [], "the walk ends in a space nothing lives in: a world"
    assert str(source_intrinsic.pk) in [step["transformation"]["input"]["id"] for step in path], "the walk goes through the source dataset's own space"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_the_derivation_edge_is_readable_on_the_dataset(authenticated_context: HttpContext):
    """`derivedFrom` is the edge itself, so a client can compose it -- not a label about it."""
    source = await seed.create_adataset(authenticated_context, "Source")
    source_lens = await seed.create_lens(authenticated_context, source, slices=[])

    derived = await _derive(authenticated_context, "Segmented", lens=source_lens, axes=seed.SIMPLE_AXES, shape=[3, 64, 64], transform={"kind": "IDENTITY"})
    assert not derived.errors, derived.errors

    result = await schema.execute(DERIVED, context_value=authenticated_context, variable_values={"id": derived.data["createADataset"]["id"]})
    assert not result.errors, result.errors

    edges = result.data["adataset"]["derivedFrom"]
    assert len(edges) == 1
    assert edges[0]["kind"] == "IDENTITY"
    assert edges[0]["inputAxes"] == ["c", "y", "x"]
    assert edges[0]["outputAxes"] == ["c", "y", "x"]

    # An acquired dataset was derived from nothing, and says so.
    plain = await schema.execute(DERIVED, context_value=authenticated_context, variable_values={"id": str(source.pk)})
    assert not plain.errors, plain.errors
    assert plain.data["adataset"]["derivedFrom"] == []


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_the_derivation_is_readable_from_the_source_as_well(authenticated_context: HttpContext):
    """`derivedDatasets` answers "what came out of this" -- the same edges, read backwards.

    A source cannot otherwise be asked what was made from it: `derivedFrom` only points
    upwards, so finding a dataset's descendants meant fetching every dataset and reading
    each one's parents. The inverse is a query over the same edges, so the two can never
    disagree; there is no back-reference column to fall out of step.

    On the lens as well as the dataset, because a derivation names a *lens*: which
    selection a segmentation was computed from is the finer question, and the dataset-level
    field aggregates it over every lens.
    """
    source = await seed.create_adataset(authenticated_context, "Source")
    lens = await seed.create_lens(authenticated_context, source, slices=[])

    derived = await _derive(authenticated_context, "Segmented", lens=lens, axes=seed.SIMPLE_AXES, shape=[3, 64, 64], transform={"kind": "IDENTITY"})
    assert not derived.errors, derived.errors
    child_id = derived.data["createADataset"]["id"]

    result = await schema.execute(DERIVED_DATASETS, context_value=authenticated_context, variable_values={"id": str(source.pk)})
    assert not result.errors, result.errors
    assert [child["id"] for child in result.data["adataset"]["derivedDatasets"]] == [child_id]

    # The same fact through the lens the derivation actually named.
    from_lens = await schema.execute(
        "query L($id: ID!) { lens(id: $id) { id derivedDatasets { id name } } }",
        context_value=authenticated_context,
        variable_values={"id": str(lens.pk)},
    )
    assert not from_lens.errors, from_lens.errors
    assert [child["name"] for child in from_lens.data["lens"]["derivedDatasets"]] == ["Segmented"]

    # A leaf produced nothing, and says so rather than echoing its own parent back.
    leaf = await schema.execute(DERIVED_DATASETS, context_value=authenticated_context, variable_values={"id": child_id})
    assert not leaf.errors, leaf.errors
    assert leaf.data["adataset"]["derivedDatasets"] == []


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_fusion_is_a_child_of_every_source_it_named_exactly_once(authenticated_context: HttpContext):
    """Report every child, not just the ones this source places -- and each child once.

    Two traps the naive query falls into. A fusion has several parents but only the first
    *places* it, so a walk that follows placement would hide the fusion from its second
    source -- yet it is just as much derived from it, and `derivedFrom` says so from the
    other side. And a fusion of two lenses of ONE source has two edges landing in that
    source: one relation, two facts, and the child must still be listed once.
    """
    primary = await seed.create_adataset(authenticated_context, "Primary")
    secondary = await seed.create_adataset(authenticated_context, "Secondary")
    primary_lens = await seed.create_lens(authenticated_context, primary, slices=[])
    secondary_lens = await seed.create_lens(authenticated_context, secondary, slices=[])

    fusion = await _derive(
        authenticated_context,
        "Fused",
        axes=seed.SIMPLE_AXES,
        shape=[3, 64, 64],
        entries=[{"lens": str(primary_lens.pk), "transform": {"kind": "IDENTITY"}}, {"lens": str(secondary_lens.pk), "transform": {"kind": "IDENTITY"}}],
    )
    assert not fusion.errors, fusion.errors
    fused_id = fusion.data["createADataset"]["id"]

    for source in (primary, secondary):
        result = await schema.execute(DERIVED_DATASETS, context_value=authenticated_context, variable_values={"id": str(source.pk)})
        assert not result.errors, result.errors
        assert [child["id"] for child in result.data["adataset"]["derivedDatasets"]] == [fused_id], f"{source.name} is a real parent of the fusion, primary or not"

    # Two lenses of ONE source: two edges into it, still one child.
    other_lens = await seed.create_lens(authenticated_context, primary, slices=[{"axis": "y", "start": 8, "stop": 40}])
    two_lens_fusion = await _derive(
        authenticated_context,
        "SelfFused",
        axes=seed.SIMPLE_AXES,
        shape=[3, 64, 64],
        entries=[{"lens": str(primary_lens.pk), "transform": {"kind": "IDENTITY"}}, {"lens": str(other_lens.pk), "transform": {"kind": "IDENTITY"}}],
    )
    assert not two_lens_fusion.errors, two_lens_fusion.errors
    assert len(two_lens_fusion.data["createADataset"]["derivedFrom"]) == 2, "the dedup below is only a test if two edges really land in one source"

    result = await schema.execute(DERIVED_DATASETS, context_value=authenticated_context, variable_values={"id": str(primary.pk)})
    assert not result.errors, result.errors
    names = [child["name"] for child in result.data["adataset"]["derivedDatasets"]]
    assert names.count("SelfFused") == 1, f"one child, however many of its edges land here: {names}"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_unmappable_child_is_still_a_child(authenticated_context: HttpContext):
    """The inverse is kind-blind, exactly as `derivedFrom` is.

    "This came from that, and the geometry did not survive" is a derivation -- the one the
    UNMAPPABLE kind exists to record. The placement walks refuse that edge; a lineage
    report must not, or the source silently disowns the very data whose provenance is
    hardest to reconstruct by other means.
    """
    source = await seed.create_adataset(authenticated_context, "Raw")
    lens = await seed.create_lens(authenticated_context, source, slices=[])

    measured = await _derive(authenticated_context, "Measurements", lens=lens, axes=seed.SIMPLE_AXES, shape=[3, 64, 64], transform={"kind": "UNMAPPABLE"})
    assert not measured.errors, measured.errors

    result = await schema.execute(DERIVED_DATASETS, context_value=authenticated_context, variable_values={"id": str(source.pk)})
    assert not result.errors, result.errors
    assert [child["name"] for child in result.data["adataset"]["derivedDatasets"]] == ["Measurements"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_calibrated_dataset_is_not_its_own_child(authenticated_context: HttpContext):
    """A calibration runs intrinsic -> PHYSICAL, and both ends belong to one dataset.

    Which means it looks exactly like a derivation landing in this dataset's space, from
    this dataset's intrinsic system -- and it is nothing of the sort: a dataset is not
    computed from itself. Only the guard that skips the dataset asking keeps it out, so
    this is the test that says the guard is load-bearing rather than decorative.
    """
    dataset = await seed.create_adataset(authenticated_context, "Calibrated")
    await seed.create_physical_space(
        authenticated_context,
        dataset,
        axes=[
            seed.physical_axis("c", enums.AxisType.CHANNEL, unit="a.u."),
            seed.physical_axis("y", enums.AxisType.SPACE, unit="micrometer"),
            seed.physical_axis("x", enums.AxisType.SPACE, unit="micrometer"),
        ],
        scale=[1.0, 0.325, 0.325],
    )

    result = await schema.execute(DERIVED_DATASETS, context_value=authenticated_context, variable_values={"id": str(dataset.pk)})
    assert not result.errors, result.errors
    assert result.data["adataset"]["derivedDatasets"] == [], "a calibration is a space of one's own, not a descendant"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_projection_drops_an_axis_as_by_dimension(authenticated_context: HttpContext):
    """A max-z projection is a rank change, and BY_DIMENSION is how a rank change is stated."""
    axes = [
        seed.axis("c", enums.AxisType.CHANNEL),
        seed.axis("z", enums.AxisType.SPACE),
        seed.axis("y", enums.AxisType.SPACE),
        seed.axis("x", enums.AxisType.SPACE),
    ]
    source = await seed.create_adataset(authenticated_context, "Volume", axes=axes, shapes=[[2, 16, 32, 32]])
    source_lens = await seed.create_lens(authenticated_context, source, slices=[])

    flat_axes = [
        seed.axis("c", enums.AxisType.CHANNEL),
        seed.axis("y", enums.AxisType.SPACE),
        seed.axis("x", enums.AxisType.SPACE),
    ]
    derived = await _derive(
        authenticated_context,
        "MaxZ",
        lens=source_lens,
        axes=flat_axes,
        shape=[2, 32, 32],
        transform={"kind": "BY_DIMENSION", "inputAxes": ["c", "y", "x"], "outputAxes": ["c", "y", "x"]},
    )
    assert not derived.errors, derived.errors

    edge = derived.data["createADataset"]["derivedFrom"][0]
    assert edge["kind"] == "BY_DIMENSION"
    # The projection says nothing about z -- which is exactly the truth, and exactly what a
    # square edge could not have said.
    assert edge["inputAxes"] == ["c", "y", "x"]
    assert edge["outputAxes"] == ["c", "y", "x"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_identity_is_not_a_rank_claim_in_disguise(authenticated_context: HttpContext):
    """IDENTITY says the two grids ARE the same. Between different axes that is a lie.

    IDENTITY carries no parameters, so no rank check would otherwise look at it -- and it
    is the *default* for a derivation. A projection defaulting into an identity would state
    that a 3D volume and its 2D projection are the same space, and nothing downstream could
    tell that apart from a genuine in-place operation.
    """
    axes = [
        seed.axis("c", enums.AxisType.CHANNEL),
        seed.axis("z", enums.AxisType.SPACE),
        seed.axis("y", enums.AxisType.SPACE),
        seed.axis("x", enums.AxisType.SPACE),
    ]
    source = await seed.create_adataset(authenticated_context, "Volume", axes=axes, shapes=[[2, 16, 32, 32]])
    source_lens = await seed.create_lens(authenticated_context, source, slices=[])

    flat_axes = [
        seed.axis("c", enums.AxisType.CHANNEL),
        seed.axis("y", enums.AxisType.SPACE),
        seed.axis("x", enums.AxisType.SPACE),
    ]
    derived = await _derive(authenticated_context, "MaxZ", lens=source_lens, axes=flat_axes, shape=[2, 32, 32], transform={"kind": "IDENTITY"})

    assert derived.errors, "an identity between (c,z,y,x) and (c,y,x) is a rank change wearing an identity's clothes"
    assert "IDENTITY" in str(derived.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_categorized_derivation_bootstraps_a_label_layer(authenticated_context: HttpContext):
    """`valueRelation` is the structural signal LABEL inference was missing.

    The spatial kind says where a threshold's pixels sit (IDENTITY); CATEGORIZED says
    what happened to the numbers -- they became labels. Stated on the derivation edge,
    it lets the bootstrap render the mask as a label map with no explicit override,
    while a TRANSFORMED derivation (a deconvolution) still reads as intensity.
    """
    source = await seed.create_adataset(authenticated_context, "Raw")  # (c, y, x)
    lens = await seed.create_lens(authenticated_context, source, slices=[])

    derived = await _derive(
        authenticated_context,
        "Mask",
        axes=seed.SIMPLE_AXES,
        shape=[3, 64, 64],
        lens=lens,
        transform={"kind": "IDENTITY"},
        valueRelation="CATEGORIZED",
    )
    assert not derived.errors, derived.errors
    assert derived.data["createADataset"]["derivedFrom"][0]["valueRelation"] == "CATEGORIZED", "the statement rides the derivation edge itself"
    mask = await sync_to_async(models.ADataset.objects.get)(pk=derived.data["createADataset"]["id"])

    bootstrapped = await schema.execute(
        "mutation B($input: CreateSceneFromDatasetInput!) { createSceneFromDataset(input: $input) { id } }",
        context_value=authenticated_context,
        variable_values={"input": {"dataset": str(mask.pk)}},
    )
    assert not bootstrapped.errors, bootstrapped.errors

    def label_layer() -> models.Layer:
        return models.Layer.objects.get(lens__dataset=mask)

    layer = await sync_to_async(label_layer)()
    (child,) = layer.render_graph["root"]["children"]
    assert child["transfer"]["categorical"] is True, "a stated categorization renders as labels without an override"
    assert layer.blending == enums.BlendingChoices.NORMAL.value

    # The orthogonality, from the other side: transformed values are still an intensity.
    deconvolved = await _derive(
        authenticated_context,
        "Deconvolved",
        axes=seed.SIMPLE_AXES,
        shape=[3, 64, 64],
        lens=lens,
        transform={"kind": "IDENTITY"},
        valueRelation="TRANSFORMED",
    )
    assert not deconvolved.errors, deconvolved.errors
    intensity = await sync_to_async(models.ADataset.objects.get)(pk=deconvolved.data["createADataset"]["id"])

    bootstrapped = await schema.execute(
        "mutation B($input: CreateSceneFromDatasetInput!) { createSceneFromDataset(input: $input) { id } }",
        context_value=authenticated_context,
        variable_values={"input": {"dataset": str(intensity.pk)}},
    )
    assert not bootstrapped.errors, bootstrapped.errors

    def intensity_layer() -> models.Layer:
        return models.Layer.objects.get(lens__dataset=intensity)

    layer = await sync_to_async(intensity_layer)()
    children = layer.render_graph["root"]["children"]
    assert all(not child["transfer"].get("categorical") for child in children), "new numbers are still an intensity, not labels"


# `test_a_value_relation_on_a_registration_is_refused` was removed with RFC-9. The refusal
# rested on there being a class of edge -- a registration into a shared space -- across which
# values were known not to travel. There is no such class any more: every edge is an edge, and
# `valueRelation` rides whichever one its author thinks it describes.



_DATASETS = """
query List($filters: ADatasetFilter) {
  adatasets(filters: $filters) { name }
}
"""


async def _names(ctx: HttpContext, filters: dict) -> set[str]:
    result = await schema.execute(_DATASETS, context_value=ctx, variable_values={"filters": filters})
    assert not result.errors, result.errors
    return {d["name"] for d in result.data["adatasets"]}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_derived_from_and_not_derived_filters(authenticated_context: HttpContext):
    """`derivedFrom` lists a source's children; `notDerived` lists the roots.

    Both are `graph_logic.derivation_edges` as a query, so both inherit its two rules:
    an edge landing back in the *same* dataset is not a derivation (a calibration edge
    runs intrinsic -> the dataset's own PHYSICAL space, and would otherwise make it its
    own child), and an UNMAPPABLE derivation still counts -- it records that the data
    came from there, only that its geometry did not survive.
    """
    ctx = authenticated_context
    source = await seed.create_adataset(ctx, "Acquired")
    lens = await seed.create_lens(ctx, source, slices=[])

    child = await _derive(ctx, "Deconvolved", lens=lens, axes=seed.SIMPLE_AXES, shape=[3, 64, 64], transform={"kind": "IDENTITY"})
    assert not child.errors, child.errors

    # The calibration edge is the trap: it leaves the source's intrinsic system just as a
    # derivation does, and lands in a space the source itself owns.
    await seed.create_physical_space(
        ctx,
        source,
        axes=[
            seed.physical_axis("c", enums.AxisType.CHANNEL, "a.u."),
            seed.physical_axis("y", enums.AxisType.SPACE, "micrometer"),
            seed.physical_axis("x", enums.AxisType.SPACE, "micrometer"),
        ],
        scale=[1.0, 0.5, 0.5],
    )

    assert await _names(ctx, {"derivedFrom": str(source.pk)}) == {"Deconvolved"}
    # The source is not its own child, however many edges leave its intrinsic system.
    assert await _names(ctx, {"notDerived": True}) == {"Acquired"}
    assert await _names(ctx, {"notDerived": False}) == {"Deconvolved"}

    # These are plain-Q subqueries and `spec` is an aggregate: the id__in lands in WHERE
    # beside the counts' GROUP BY / HAVING, and the two must still compose.
    assert await _names(ctx, {"notDerived": True, "spec": ["IMAGE"]}) == {"Acquired"}
    assert await _names(ctx, {"notDerived": True, "spec": ["VOLUME"]}) == set()
    assert await _names(ctx, {"derivedFrom": str(source.pk), "spec": ["IMAGE", "MULTICHANNEL"]}) == {"Deconvolved"}
    assert await _names(ctx, {"derivedFrom": str(source.pk), "hasPhysicalSpace": True}) == set()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_derivation_filters_are_kind_blind(authenticated_context: HttpContext):
    """An UNMAPPABLE child still came from here: reporting it is the whole point of the kind."""
    ctx = authenticated_context
    source = await seed.create_adataset(ctx, "Acquired")
    lens = await seed.create_lens(ctx, source, slices=[])

    unmappable = await _derive(ctx, "Segmented", lens=lens, axes=seed.SIMPLE_AXES, shape=[3, 64, 64], transform={"kind": "UNMAPPABLE"}, valueRelation="CATEGORIZED")
    assert not unmappable.errors, unmappable.errors

    assert await _names(ctx, {"derivedFrom": str(source.pk)}) == {"Segmented"}
    assert await _names(ctx, {"notDerived": True}) == {"Acquired"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_derived_from_reports_every_parent_of_a_fusion(authenticated_context: HttpContext):
    """A fusion has two real parents, and is a child of both -- not only the one that places it."""
    ctx = authenticated_context
    first = await seed.create_adataset(ctx, "ChannelA")
    second = await seed.create_adataset(ctx, "ChannelB")
    lens_a = await seed.create_lens(ctx, first, slices=[])
    lens_b = await seed.create_lens(ctx, second, slices=[])

    fused = await _derive(
        ctx,
        "Fused",
        axes=seed.SIMPLE_AXES,
        shape=[3, 64, 64],
        entries=[{"lens": str(lens_a.pk), "transform": {"kind": "IDENTITY"}}, {"lens": str(lens_b.pk), "transform": {"kind": "IDENTITY"}}],
    )
    assert not fused.errors, fused.errors

    assert await _names(ctx, {"derivedFrom": str(first.pk)}) == {"Fused"}
    assert await _names(ctx, {"derivedFrom": str(second.pk)}) == {"Fused"}
    assert await _names(ctx, {"notDerived": True}) == {"ChannelA", "ChannelB"}
