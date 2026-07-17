"""The `placeableIn` filter: which lenses / table datasets can be composed into a scene.

A `Lens`/`TableDataset` is *placeable in* a scene when a traversable path exists from its
coordinate system to the scene's world, honouring the scene's membership set -- the very
gate ``assert_placeable_in_scene`` applies when a layer is created. The filter walks the
transformation edges, so it is a Python-side reachability question, not an ORM join.

The load-bearing test is the consistency one: the batched helper the filter runs over the
whole candidate set must agree, object for object, with the single-source
``is_placeable_in_scene`` -- otherwise the picker would offer a source that layer creation
then refuses (or hide one it would accept). The rest pin the pieces that make that true:
the UNMAPPABLE gate, the descendant closure (a derived dataset placed through its parent's
registration), the table case, and membership isolation between two scenes over one world.
"""

import pytest
from asgiref.sync import sync_to_async
from kante.context import HttpContext

from core import enums, models
from core.logic import graph as graph_logic
from mikro_server.schema import schema
from tests import seed

_CREATE_TABLE = """
mutation Create($input: CreateTableDatasetInput!) {
  createTableDataset(input: $input) { id }
}
"""

_COORD_COLUMNS = [
    {"name": "y", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"},
    {"name": "x", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"},
]

LENSES = """
query Lenses($scene: ID!) {
  lenses(filters: { placeableIn: $scene }) { id }
}
"""

TABLE_DATASETS = """
query Tables($scene: ID!) {
  tableDatasets(filters: { placeableIn: $scene }) { id }
}
"""


async def _table_dataset(ctx: HttpContext, key: str) -> models.TableDataset:
    """A freestanding coordinate table: it owns a placeable (y, x) system, registered on demand."""
    store = await sync_to_async(models.ParquetStore.objects.create)(
        path=f"s3://parquet/{key}", bucket="parquet", key=key, organization=ctx.request.organization
    )
    result = await schema.execute(
        _CREATE_TABLE,
        context_value=ctx,
        variable_values={"input": {"data": str(store.pk), "name": key, "columns": _COORD_COLUMNS}},
    )
    assert not result.errors, result.errors
    return await sync_to_async(models.TableDataset.objects.get)(pk=result.data["createTableDataset"]["id"])


def _derivation(ctx: HttpContext, child: models.ADataset, parent: models.ADataset, kind: str) -> models.Transformation:
    """A derivation edge child -> parent (input = child's intrinsic, output = parent's).

    IDENTITY between two c/y/x datasets is a real in-place derivation; UNMAPPABLE records
    "came from that image" while denying any point correspondence -- the edge the placement
    walk refuses.
    """
    return models.Transformation.objects.create(
        kind=kind,
        input=child.intrinsic_coordinate_system,
        output=parent.intrinsic_coordinate_system,
        organization=ctx.request.organization,
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_batched_helper_agrees_with_per_candidate_predicate(authenticated_context: HttpContext):
    """The filter's batched set matches ``is_placeable_in_scene`` object for object.

    Unsliced and sliced lenses over a registered and an unregistered dataset -- the one gap
    the whole design fights is the picker and the layer mutation disagreeing about any of them.
    """
    ctx = authenticated_context
    placed = await seed.create_adataset(ctx, "Placed")
    unplaced = await seed.create_adataset(ctx, "Unplaced")
    scene = await seed.create_scene(ctx, "Composition")
    await seed.register_into_scene(ctx, scene, placed)

    lenses = [
        await seed.create_lens(ctx, placed, slices=[]),
        await seed.create_lens(ctx, placed, slices=[{"axis": "y", "start": 8, "stop": 40}]),
        await seed.create_lens(ctx, unplaced, slices=[]),
        await seed.create_lens(ctx, unplaced, slices=[{"axis": "x", "start": 4, "stop": 20}]),
    ]

    def check() -> None:
        dataset_ids = graph_logic.placeable_lens_dataset_ids(scene)
        for lens in lenses:
            source = graph_logic.lens_source_system(lens)
            expected = graph_logic.is_placeable_in_scene(scene, source)
            assert (lens.dataset_id in dataset_ids) == expected, f"lens {lens.pk} disagrees: batched={lens.dataset_id in dataset_ids}, predicate={expected}"

    await sync_to_async(check)()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_registered_datasets_lenses_are_placeable(authenticated_context: HttpContext):
    """Every lens of a registered dataset -- even a fresh, never-layered one -- is offered; none of an unregistered dataset's are."""
    ctx = authenticated_context
    placed = await seed.create_adataset(ctx, "Placed")
    unplaced = await seed.create_adataset(ctx, "Unplaced")
    scene = await seed.create_scene(ctx, "Composition")
    await seed.register_into_scene(ctx, scene, placed)

    fresh = await seed.create_lens(ctx, placed, slices=[])
    sliced = await seed.create_lens(ctx, placed, slices=[{"axis": "y", "start": 8, "stop": 40}])
    orphan = await seed.create_lens(ctx, unplaced, slices=[])

    def check() -> None:
        ids = graph_logic.placeable_lens_dataset_ids(scene)
        assert placed.pk in ids
        assert unplaced.pk not in ids

    await sync_to_async(check)()

    result = await schema.execute(LENSES, context_value=ctx, variable_values={"scene": str(scene.pk)})
    assert not result.errors, result.errors
    returned = {lens["id"] for lens in result.data["lenses"]}
    assert str(fresh.pk) in returned
    assert str(sliced.pk) in returned
    assert str(orphan.pk) not in returned


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_unmappable_is_excluded_but_a_mappable_descendant_is_placeable(authenticated_context: HttpContext):
    """A mappable derived dataset rides its parent's registration to world; an UNMAPPABLE one does not.

    Registering only the root, a lens of the IDENTITY-derived child is placeable (the
    descendant closure), while a lens of the UNMAPPABLE-derived child is not (the gate).
    """
    ctx = authenticated_context
    root = await seed.create_adataset(ctx, "Root")
    mappable = await seed.create_adataset(ctx, "MappableChild")
    unmappable = await seed.create_adataset(ctx, "UnmappableChild")
    scene = await seed.create_scene(ctx, "Composition")
    await seed.register_into_scene(ctx, scene, root)

    def wire() -> None:
        _derivation(ctx, mappable, root, enums.TransformKindChoices.IDENTITY.value)
        _derivation(ctx, unmappable, root, enums.TransformKindChoices.UNMAPPABLE.value)

    await sync_to_async(wire)()

    lens_mappable = await seed.create_lens(ctx, mappable, slices=[])
    lens_unmappable = await seed.create_lens(ctx, unmappable, slices=[])

    def check() -> None:
        ids = graph_logic.placeable_lens_dataset_ids(scene)
        assert root.pk in ids
        assert mappable.pk in ids, "a mappable descendant is placed through its parent's registration"
        assert unmappable.pk not in ids, "the UNMAPPABLE gate refuses a derivation whose geometry did not survive"
        # Consistency with the single-source predicate, again, on the derived sources.
        for lens, dataset_id in ((lens_mappable, mappable.pk), (lens_unmappable, unmappable.pk)):
            source = graph_logic.lens_source_system(lens)
            assert (dataset_id in ids) == graph_logic.is_placeable_in_scene(scene, source)

    await sync_to_async(check)()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_table_dataset_placeable_only_once_registered(authenticated_context: HttpContext):
    """A table dataset is offered exactly when its own coordinate system is registered into the scene."""
    ctx = authenticated_context
    placed = await _table_dataset(ctx, "placed-table")
    unplaced = await _table_dataset(ctx, "unplaced-table")
    scene = await seed.create_scene(ctx, "Composition")
    system = await sync_to_async(lambda: placed.coordinate_system)()
    await seed.register_into_scene(ctx, scene, system=system)

    def check() -> None:
        ids = graph_logic.placeable_table_dataset_ids(scene)
        assert placed.pk in ids
        assert unplaced.pk not in ids

    await sync_to_async(check)()

    result = await schema.execute(TABLE_DATASETS, context_value=ctx, variable_values={"scene": str(scene.pk)})
    assert not result.errors, result.errors
    returned = {table["id"] for table in result.data["tableDatasets"]}
    assert str(placed.pk) in returned
    assert str(unplaced.pk) not in returned


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_two_scenes_over_one_world_share_the_placeable_set(authenticated_context: HttpContext):
    """One truth per space: the placeable set is the world's, so every scene over it agrees.

    The registration is a fact about the space, not a per-scene endorsement -- there is
    no membership for it to leak through or be gated by."""
    ctx = authenticated_context
    dataset = await seed.create_adataset(ctx, "Shared")
    scene_a = await seed.create_scene(ctx, "SceneA")

    def make_sibling() -> models.Scene:
        return models.Scene.objects.create(name="SceneB", world=scene_a.world, organization=ctx.request.organization)

    scene_b = await sync_to_async(make_sibling)()
    await seed.register_into_scene(ctx, scene_a, dataset)

    def check() -> None:
        assert dataset.pk in graph_logic.placeable_lens_dataset_ids(scene_a)
        assert dataset.pk in graph_logic.placeable_lens_dataset_ids(scene_b), "candidates are a property of the space, identical for every scene over it"

    await sync_to_async(check)()


ADATASETS = """
query Datasets($scene: ID!) {
  adatasets(filters: { placeableIn: $scene }) { id }
}
"""


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_adataset_placeable_in_agrees_with_its_lenses(authenticated_context: HttpContext):
    """A dataset is offered exactly when one of its lenses is: same set, one hop up.

    Both read `placeable_lens_dataset_ids`, so the picker cannot offer a dataset whose
    every lens the layer mutation would refuse, nor hide one it would accept.
    """
    ctx = authenticated_context
    placed = await seed.create_adataset(ctx, "Placed")
    unplaced = await seed.create_adataset(ctx, "Unplaced")
    scene = await seed.create_scene(ctx, "Composition")
    await seed.register_into_scene(ctx, scene, placed)
    await seed.create_lens(ctx, placed, slices=[])
    await seed.create_lens(ctx, unplaced, slices=[])

    result = await schema.execute(ADATASETS, context_value=ctx, variable_values={"scene": str(scene.pk)})
    assert not result.errors, result.errors
    assert {d["id"] for d in result.data["adatasets"]} == {str(placed.pk)}

    lenses = await schema.execute(LENSES, context_value=ctx, variable_values={"scene": str(scene.pk)})
    assert not lenses.errors, lenses.errors

    def lens_datasets() -> set[str]:
        return {str(models.Lens.objects.get(pk=lens["id"]).dataset_id) for lens in lenses.data["lenses"]}

    assert await sync_to_async(lens_datasets)() == {d["id"] for d in result.data["adatasets"]}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_derived_dataset_is_placeable_through_its_source(authenticated_context: HttpContext):
    """The descendant closure reaches datasets too: a child is offered on its parent's registration.

    And an UNMAPPABLE derivation is where that stops -- the walk refuses the edge, so the
    child is not offered however much it owes the source historically.
    """
    ctx = authenticated_context
    source = await seed.create_adataset(ctx, "Source")
    derived = await seed.create_adataset(ctx, "Derived")
    severed = await seed.create_adataset(ctx, "Severed")
    scene = await seed.create_scene(ctx, "Composition")
    await seed.register_into_scene(ctx, scene, source)
    await sync_to_async(_derivation)(ctx, derived, source, enums.TransformKindChoices.IDENTITY.value)
    await sync_to_async(_derivation)(ctx, severed, source, enums.TransformKindChoices.UNMAPPABLE.value)
    for dataset in (source, derived, severed):
        await seed.create_lens(ctx, dataset, slices=[])

    result = await schema.execute(ADATASETS, context_value=ctx, variable_values={"scene": str(scene.pk)})
    assert not result.errors, result.errors
    assert {d["id"] for d in result.data["adatasets"]} == {str(source.pk), str(derived.pk)}
