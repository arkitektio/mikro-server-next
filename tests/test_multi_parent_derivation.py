"""A fusion has several parents, and the creator's declared order says which one places it.

A merge of two channels, a stitch of two tiles: the result was computed from several
lenses, and each of those relations is a spatial fact -- so each is an edge, exactly as a
single-source derivation is. What multi-parent adds is the question single-parent never
had to answer: which parent places the fused data? The answer is not a pk accident but a
declaration -- the first `derivedFrom` entry is the primary parent, and it drives the
lineage root, the default registration and the order `derivedFrom` reports.

These tests pin the three halves of that contract: the order is stored and reported as
declared, the placement machinery acts on the primary while still *walking* every parent,
and creation refuses the inputs that would make the primary a lie (a duplicate source, or
an UNMAPPABLE entry hiding a mappable parent behind it).
"""

import pytest
from asgiref.sync import sync_to_async
from kante.context import HttpContext

from core import models
from core.logic import graph as graph_logic
from mikro_server.schema import schema
from tests import seed
from tests.test_derived_datasets import _derive

CREATE_SCENE = """
mutation CreateScene($input: CreateSceneInput!) {
  createScene(input: $input) { id worldCoordinateSystem { id } }
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
    layers { id pathToWorld { transformation { id kind input { id kind } output { id kind } } } }
    registrations { id kind name }
  }
}
"""

DERIVED = """
query Derived($id: ID!) {
  adataset(id: $id) {
    id
    derivedFrom { id kind output { id } }
  }
}
"""

_AFFINE_3D = [
    [1.0, 0.0, 0.0, 5.0],
    [0.0, 1.0, 0.0, 5.0],
    [0.0, 0.0, 1.0, 0.0],
]


async def _two_sources(ctx: HttpContext) -> tuple[models.ADataset, models.Lens, models.ADataset, models.Lens]:
    """Two acquired datasets with a full lens each -- the parents of every fusion below."""
    left = await seed.create_adataset(ctx, "Left")
    left_lens = await seed.create_lens(ctx, left, slices=[])
    right = await seed.create_adataset(ctx, "Right")
    right_lens = await seed.create_lens(ctx, right, slices=[])
    return left, left_lens, right, right_lens


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_fusion_records_every_parent_in_declared_order(authenticated_context: HttpContext):
    """`derivedFrom` is the declared list, not a pk lottery: swap the input and the order swaps."""
    _, left_lens, _, right_lens = await _two_sources(authenticated_context)

    async def fuse(name: str, first: models.Lens, second: models.Lens):
        result = await _derive(
            authenticated_context,
            name,
            axes=seed.SIMPLE_AXES,
            shape=[3, 64, 64],
            entries=[{"lens": str(first.pk), "kind": "IDENTITY"}, {"lens": str(second.pk), "kind": "IDENTITY"}],
        )
        assert not result.errors, result.errors
        return result.data["createADataset"]["id"]

    fused_id = await fuse("Fused", left_lens, right_lens)
    swapped_id = await fuse("Swapped", right_lens, left_lens)

    left_space = str((await sync_to_async(lambda: left_lens.space)()).pk)
    right_space = str((await sync_to_async(lambda: right_lens.space)()).pk)

    for dataset_id, expected in ((fused_id, [left_space, right_space]), (swapped_id, [right_space, left_space])):
        result = await schema.execute(DERIVED, context_value=authenticated_context, variable_values={"id": dataset_id})
        assert not result.errors, result.errors
        edges = result.data["adataset"]["derivedFrom"]
        assert [edge["output"]["id"] for edge in edges] == expected, "the first entry is the primary parent, and only the creator says which that is"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_duplicate_source_is_refused(authenticated_context: HttpContext):
    """One entry per source: a second entry for the same lens is two claims about one relation."""
    _, left_lens, _, _ = await _two_sources(authenticated_context)

    result = await _derive(
        authenticated_context,
        "DoubleCounted",
        axes=seed.SIMPLE_AXES,
        shape=[3, 64, 64],
        entries=[{"lens": str(left_lens.pk), "kind": "IDENTITY"}, {"lens": str(left_lens.pk), "kind": "IDENTITY"}],
    )
    assert result.errors, "the same lens twice is not a fusion, it is a contradiction waiting to be written"
    assert "distinct lens" in str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_unmappable_entry_may_not_hide_a_mappable_parent(authenticated_context: HttpContext):
    """The primary is the placing parent, so an UNMAPPABLE first entry ahead of a mappable one is refused.

    The walks refuse an UNMAPPABLE primary -- that is its contract -- so a mappable parent
    behind it would be recorded and never placed by. Reversed, the same pair is fine: the
    mappable parent places, the UNMAPPABLE one records the history that did not survive.
    """
    _, left_lens, _, right_lens = await _two_sources(authenticated_context)

    refused = await _derive(
        authenticated_context,
        "HiddenParent",
        axes=seed.SIMPLE_AXES,
        shape=[3, 64, 64],
        entries=[
            {"lens": str(left_lens.pk), "kind": "UNMAPPABLE", "reason": "geometry lost"},
            {"lens": str(right_lens.pk), "kind": "IDENTITY"},
        ],
    )
    assert refused.errors, "a mappable parent must not hide behind an UNMAPPABLE primary"
    assert "primary" in str(refused.errors[0])

    accepted = await _derive(
        authenticated_context,
        "DeclaredParent",
        axes=seed.SIMPLE_AXES,
        shape=[3, 64, 64],
        entries=[
            {"lens": str(right_lens.pk), "kind": "IDENTITY"},
            {"lens": str(left_lens.pk), "kind": "UNMAPPABLE", "reason": "geometry lost"},
        ],
    )
    assert not accepted.errors, accepted.errors


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_all_unmappable_fusion_is_a_root_and_its_layer_is_refused_as_unmappable(authenticated_context: HttpContext):
    """History from several sources, geometry from none: the data is its own root, and its
    layer is refused with the impossibility message -- not the go-author-a-registration one,
    because there is no missing registration to author."""
    _, left_lens, _, right_lens = await _two_sources(authenticated_context)

    derived = await _derive(
        authenticated_context,
        "Measurements",
        axes=seed.SIMPLE_AXES,
        shape=[3, 64, 64],
        entries=[
            {"lens": str(left_lens.pk), "kind": "UNMAPPABLE", "reason": "reduced away"},
            {"lens": str(right_lens.pk), "kind": "UNMAPPABLE", "reason": "reduced away"},
        ],
    )
    assert not derived.errors, derived.errors
    dataset = await sync_to_async(models.ADataset.objects.get)(pk=derived.data["createADataset"]["id"])
    lens = await seed.create_lens(authenticated_context, dataset, slices=[])

    ancestors = await sync_to_async(graph_logic.lineage_ancestors)(dataset)
    root = await sync_to_async(graph_logic.primary_lineage_root)(dataset)
    assert ancestors == [], "no parent maps, so none places -- the spatial lineage is empty"
    assert root.pk == dataset.pk

    scene_result = await schema.execute(CREATE_SCENE, context_value=authenticated_context, variable_values={"input": {"name": "Sc"}})
    assert not scene_result.errors, scene_result.errors
    scene_id = scene_result.data["createScene"]["id"]

    made = await schema.execute(MAKE_LAYER, context_value=authenticated_context, variable_values={"input": {"scene": scene_id, "lens": str(lens.pk), "intensityAxis": "c"}})
    assert made.errors, "data no parent can place cannot be composed into a shared scene"
    assert "UNMAPPABLE" in str(made.errors[0]), "the error says nothing can place this, rather than sending someone to author an edge"
    assert "createTransformation" not in str(made.errors[0])

    placement = await schema.execute(PLACEMENT, context_value=authenticated_context, variable_values={"id": scene_id})
    assert not placement.errors, placement.errors
    assert placement.data["scene"]["registrations"] == [], "and nothing was fabricated on the way out"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_the_lineage_walks_every_parent_but_the_root_is_the_primary(authenticated_context: HttpContext):
    """`lineage_ancestors` is the DAG, `primary_lineage_root` is the chain the creator declared."""
    left, left_lens, right, right_lens = await _two_sources(authenticated_context)

    derived = await _derive(
        authenticated_context,
        "Fused",
        axes=seed.SIMPLE_AXES,
        shape=[3, 64, 64],
        entries=[{"lens": str(left_lens.pk), "kind": "IDENTITY"}, {"lens": str(right_lens.pk), "kind": "IDENTITY"}],
    )
    assert not derived.errors, derived.errors
    dataset = await sync_to_async(models.ADataset.objects.get)(pk=derived.data["createADataset"]["id"])

    ancestors = await sync_to_async(graph_logic.lineage_ancestors)(dataset)
    assert {ancestor.pk for ancestor in ancestors} == {left.pk, right.pk}, "every parent is spatial lineage: a path through any of them is a real placement"
    assert ancestors[0].pk == left.pk, "priority order within a generation: the primary parent comes first"

    root = await sync_to_async(graph_logic.primary_lineage_root)(dataset)
    assert root.pk == left.pk, "the root is reached by taking the FIRST edge at every hop, not any edge"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_unregistered_fusion_is_rejected_and_nothing_is_written(authenticated_context: HttpContext):
    """No parent is registered, so the fusion's layer is refused -- and the graph is untouched.

    The server used to pin the primary parent here. It no longer writes anything: two
    stitched tiles both landing at the world origin was always a fabrication, and now the
    creator authors the registration that is actually true (about whichever parent they
    measured) before the layer goes in.
    """
    left, left_lens, right, right_lens = await _two_sources(authenticated_context)

    derived = await _derive(
        authenticated_context,
        "Fused",
        axes=seed.SIMPLE_AXES,
        shape=[3, 64, 64],
        entries=[{"lens": str(left_lens.pk), "kind": "IDENTITY"}, {"lens": str(right_lens.pk), "kind": "IDENTITY"}],
    )
    assert not derived.errors, derived.errors
    dataset = await sync_to_async(models.ADataset.objects.get)(pk=derived.data["createADataset"]["id"])
    lens = await seed.create_lens(authenticated_context, dataset, slices=[])

    scene_result = await schema.execute(CREATE_SCENE, context_value=authenticated_context, variable_values={"input": {"name": "Sc"}})
    assert not scene_result.errors, scene_result.errors
    scene_id = scene_result.data["createScene"]["id"]
    edge_count = await sync_to_async(models.Transformation.objects.count)()

    made = await schema.execute(MAKE_LAYER, context_value=authenticated_context, variable_values={"input": {"scene": scene_id, "lens": str(lens.pk), "intensityAxis": "c"}})
    assert made.errors, "no parent is registered, so the fusion has no path to world"
    assert "createTransformation" in str(made.errors[0])

    def membership_count() -> int:
        return models.Scene.objects.get(pk=scene_id).coordinate_transformations.count()

    assert await sync_to_async(membership_count)() == 0, "the refused mutation wrote no membership edge"
    assert await sync_to_async(models.Transformation.objects.count)() == edge_count, "and no edge at all"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_fusion_placed_through_its_secondary_parent_is_placed(authenticated_context: HttpContext):
    """Every parent's edge is walkable: a registration on the second source is a real placement.

    Only the SECONDARY parent is registered into the scene. The search must cross the
    fusion's second derivation edge and come out at world -- and because a path exists,
    the auto-registration must not fabricate an assumed edge about the primary on top of
    it.
    """
    left, left_lens, right, right_lens = await _two_sources(authenticated_context)

    derived = await _derive(
        authenticated_context,
        "Fused",
        axes=seed.SIMPLE_AXES,
        shape=[3, 64, 64],
        entries=[{"lens": str(left_lens.pk), "kind": "IDENTITY"}, {"lens": str(right_lens.pk), "kind": "IDENTITY"}],
    )
    assert not derived.errors, derived.errors
    dataset = await sync_to_async(models.ADataset.objects.get)(pk=derived.data["createADataset"]["id"])
    lens = await seed.create_lens(authenticated_context, dataset, slices=[])

    scene_result = await schema.execute(
        CREATE_SCENE,
        context_value=authenticated_context,
        variable_values={"input": {"name": "Sc", "axes": [{"name": "z", "type": "SPACE", "unit": "micrometer"}, {"name": "y", "type": "SPACE", "unit": "micrometer"}, {"name": "x", "type": "SPACE", "unit": "micrometer"}]}},
    )
    assert not scene_result.errors, scene_result.errors
    scene_id = scene_result.data["createScene"]["id"]
    world_id = scene_result.data["createScene"]["worldCoordinateSystem"]["id"]

    right_intrinsic = await sync_to_async(lambda: right.intrinsic_coordinate_system)()
    registered = await schema.execute(
        REGISTER,
        context_value=authenticated_context,
        variable_values={"input": {"input": str(right_intrinsic.pk), "output": world_id, "kind": "AFFINE", "affine": _AFFINE_3D, "scene": scene_id}},
    )
    assert not registered.errors, registered.errors

    made = await schema.execute(MAKE_LAYER, context_value=authenticated_context, variable_values={"input": {"scene": scene_id, "lens": str(lens.pk), "intensityAxis": "c"}})
    assert not made.errors, made.errors

    placement = await schema.execute(PLACEMENT, context_value=authenticated_context, variable_values={"id": scene_id})
    assert not placement.errors, placement.errors

    path = placement.data["scene"]["layers"][0]["pathToWorld"]
    assert path is not None, "a fusion is placed by ANY of its parents; the walk must cross the second derivation edge"
    assert path[-1]["transformation"]["output"]["kind"] == "SHARED"
    assert str(right_intrinsic.pk) in [step["transformation"]["input"]["id"] for step in path], "the walk goes through the secondary parent's intrinsic system"

    names = [edge["name"] or "" for edge in placement.data["scene"]["registrations"]]
    assert not any("assumed" in name for name in names), f"a path exists, so no assumption may be written about the primary: {names}"
