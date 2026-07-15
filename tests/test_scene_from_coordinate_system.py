"""A hub, and a scene materialized from what was registered into it.

``createCoordinateSystem`` mints a hub -- the one ownerless (SHARED) coordinate system -- and
authors, explicitly, one edge per source registered into it. ``createSceneFromCoordinateSystem``
then builds a scene that *adopts* the hub as its world and turns those already-registered
sources into layers, up to a policy's ``nchildren``. It authors no edges at all -- it never
fabricates a placement, which is the pivot these tests hold it to.

The load-bearing behaviour is the membership closure: an edge into a shared space places only
when it is in the scene's composition, so a layer is placed exactly when its source->hub
registration is a member -- and its path to world is that one edge. A layer whose registration
was left out would pass creation yet resolve ``pathToWorld`` to null. Every image test asserts
a non-null path, not merely that the mutation did not raise.
"""

import pytest
from asgiref.sync import sync_to_async
from kante.context import HttpContext, UniversalRequest
from strawberry.http.temporal_response import TemporalResponse

from core import enums, models
from mikro_server.schema import schema
from tests import seed


CREATE_CS = """
mutation CreateCS($input: CreateCoordinateSystemInput!) {
  createCoordinateSystem(input: $input) {
    id kind name
    axes { name type unit }
  }
}
"""

FROM_CS = """
mutation FromCS($input: CreateSceneFromCoordinateSystemInput!) {
  createSceneFromCoordinateSystem(input: $input) {
    id name
    worldCoordinateSystem { id kind axes { name unit } }
    registrations { id kind name }
    layers {
      id kind
      placement
      placementValidity
      pathToWorld { inverted transformation { id kind } }
    }
  }
}
"""

#: The hub's axes: a purely spatial y/x world in micrometres.
ATLAS_AXES = [
    {"name": "y", "type": "SPACE", "unit": "micrometer"},
    {"name": "x", "type": "SPACE", "unit": "micrometer"},
]


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


def _register(source_field: str, source_id: str, axes=("y", "x"), validity: str = "VALIDATED") -> dict:
    """A registration path: place a source into the hub by a BY_DIMENSION edge on shared axes."""
    return {
        source_field: source_id,
        "kind": "BY_DIMENSION",
        "inputAxes": list(axes),
        "outputAxes": list(axes),
        "validity": validity,
    }


async def _create_hub(ctx: HttpContext, name: str, registrations: list[dict]) -> dict:
    result = await schema.execute(
        CREATE_CS,
        context_value=ctx,
        variable_values={"input": {"name": name, "axes": ATLAS_AXES, "registrations": registrations}},
    )
    assert not result.errors, result.errors
    return result.data["createCoordinateSystem"]


async def _scene_from(ctx: HttpContext, hub_id: str, **policy) -> dict:
    result = await schema.execute(
        FROM_CS,
        context_value=_fresh_request(ctx),
        variable_values={"input": {"coordinateSystem": hub_id, "policy": policy}},
    )
    assert not result.errors, result.errors
    return result.data["createSceneFromCoordinateSystem"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_hub_places_every_registered_dataset_in_the_scene(authenticated_context: HttpContext):
    """The whole point: sources registered into the hub become placed image layers.

    The world mirrors the hub's axes, the mirror edge is VALIDATED (identity by
    construction), and each dataset's registration edge is composed into the scene alongside
    it -- so every layer resolves a real ``pathToWorld``. A layer with a null path would mean
    the source->hub edge was created but never added to the scene's membership set.
    """
    a = await seed.create_adataset(authenticated_context, "A", shapes=[[3, 64, 64]])
    b = await seed.create_adataset(authenticated_context, "B", shapes=[[3, 64, 64]])

    hub = await _create_hub(
        authenticated_context,
        "Atlas",
        [_register("dataset", str(a.pk)), _register("dataset", str(b.pk))],
    )
    assert hub["kind"] == "SHARED"

    # Two registration edges land in the hub, one per dataset.
    registered = await sync_to_async(models.Transformation.objects.filter(output__pk=hub["id"], parent__isnull=True).count)()
    assert registered == 2

    scene = await _scene_from(authenticated_context, hub["id"])

    assert [(ax["name"], ax["unit"]) for ax in scene["worldCoordinateSystem"]["axes"]] == [("y", "micrometer"), ("x", "micrometer")]

    # Two image layers, and BOTH are placed: a non-null path is the membership closure working.
    assert len(scene["layers"]) == 2
    for layer in scene["layers"]:
        assert layer["kind"] == "IMAGE"
        assert layer["placement"] == "PLACED"
        assert layer["pathToWorld"] is not None, "the source->hub edge was not composed into the scene"
        assert layer["placementValidity"] == "VALIDATED"
        assert layer["pathToWorld"][-1]["transformation"]["kind"] == "BY_DIMENSION"

    # The scene's composition holds exactly the two source registrations: the world IS
    # the hub, so there is no mirror edge and each path is the one authored hop.
    assert len(scene["registrations"]) == 2
    assert scene["worldCoordinateSystem"]["id"] == hub["id"], "the scene adopts the hub as its world"
    for layer in scene["layers"]:
        assert len(layer["pathToWorld"]) == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_nchildren_caps_the_layers_in_registration_order(authenticated_context: HttpContext):
    """``nchildren`` is a flat cap on layers, honoured in the order the registrations were authored."""
    datasets = [await seed.create_adataset(authenticated_context, name, shapes=[[3, 32, 32]]) for name in ("A", "B", "C")]
    hub = await _create_hub(
        authenticated_context,
        "Capped",
        [_register("dataset", str(dataset.pk)) for dataset in datasets],
    )

    scene = await _scene_from(authenticated_context, hub["id"], nchildren=2)

    assert len(scene["layers"]) == 2, "nchildren limits how many sources are materialized"
    # The first two registrations (by pk) are the ones taken.
    placed_lens_dataset_ids = await sync_to_async(
        lambda: sorted(models.Layer.objects.filter(scene__pk=scene["id"]).values_list("lens__dataset__pk", flat=True))
    )()
    assert placed_lens_dataset_ids == sorted([datasets[0].pk, datasets[1].pk])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_transform_tables_gates_table_layers(authenticated_context: HttpContext):
    """A registered table dataset becomes a point layer only when the policy asks for it."""
    store = await sync_to_async(models.ParquetStore.objects.create)(path="s3://parquet/mols", bucket="parquet", key="mols", organization=authenticated_context.request.organization)
    created = await schema.execute(
        """
        mutation Create($input: CreateTableDatasetInput!) {
          createTableDataset(input: $input) { id }
        }
        """,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "data": str(store.pk),
                "name": "molecules",
                "columns": [
                    {"name": "y", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE", "unit": "micrometer"},
                    {"name": "x", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE", "unit": "micrometer"},
                ],
            }
        },
    )
    assert not created.errors, created.errors
    table_id = created.data["createTableDataset"]["id"]

    hub = await _create_hub(authenticated_context, "Tables", [_register("tableDataset", table_id)])

    off = await _scene_from(authenticated_context, hub["id"], transformTables=False)
    assert off["layers"] == [], "a table is skipped unless transform_tables is set"

    on = await _scene_from(authenticated_context, hub["id"], transformTables=True)
    (layer,) = on["layers"]
    assert layer["kind"] == "POINT"
    assert layer["pathToWorld"] is not None, "the table's registration edge was not composed into the scene"
    assert layer["placement"] == "PLACED"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_include_meshes_gates_mesh_layers(authenticated_context: HttpContext):
    """A registered mesh collection becomes a mesh layer unless the policy excludes it."""
    dataset = await seed.create_adataset(authenticated_context, "Meshed", axes=seed.YX_AXES, shapes=[[64, 64]])
    system = await sync_to_async(lambda: dataset.intrinsic_coordinate_system)()

    def stores() -> tuple[models.ParquetStore, models.ParquetStore]:
        catalog = models.ParquetStore.objects.create(path="s3://parquet/catalog", bucket="parquet", key="catalog", organization=authenticated_context.request.organization)
        shard = models.ParquetStore.objects.create(path="s3://parquet/geometry-0", bucket="parquet", key="geometry-0", organization=authenticated_context.request.organization)
        return catalog, shard

    catalog, shard = await sync_to_async(stores)()
    created = await schema.execute(
        """
        mutation Create($input: CreateMeshCollectionInput!) {
          createMeshCollection(input: $input) { id }
        }
        """,
        context_value=authenticated_context,
        variable_values={"input": {"coordinateSystem": str(system.pk), "version": "v1", "specVersion": "1.0", "catalog": str(catalog.pk), "geometry": [str(shard.pk)]}},
    )
    assert not created.errors, created.errors
    collection_id = created.data["createMeshCollection"]["id"]

    hub = await _create_hub(authenticated_context, "Meshes", [_register("meshCollection", collection_id)])

    off = await _scene_from(authenticated_context, hub["id"], includeMeshes=False)
    assert off["layers"] == [], "a mesh collection is skipped when include_meshes is off"

    on = await _scene_from(authenticated_context, hub["id"], includeMeshes=True)
    (layer,) = on["layers"]
    assert layer["kind"] == "MESH"
    assert layer["pathToWorld"] is not None
    assert layer["placement"] == "PLACED"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_only_a_hub_can_seed_a_scene(authenticated_context: HttpContext):
    """Only an ownerless hub can seed a scene; every owned system is refused.

    There is no kind to smuggle in on creation any more -- the input carries no kind
    field at all, so 'creating a non-hub' is unrepresentable rather than validated.
    The gate that remains is ownership: a scene's world is SHARED-kind too, but it is
    scene-owned and therefore not a hub.
    """
    sdl = schema.as_str()
    input_def = sdl[sdl.find("input CreateCoordinateSystemInput ") : sdl.find("}", sdl.find("input CreateCoordinateSystemInput "))]
    assert "kind" not in input_def, "a hub's kind is decided by its (absent) ownership, not an input"

    # A scene's world system is not a hub, and cannot be used to seed another scene.
    scene = await seed.create_scene(authenticated_context, "Plain")
    world = await sync_to_async(lambda: scene.world_coordinate_system)()
    rejected = await schema.execute(
        FROM_CS,
        context_value=authenticated_context,
        variable_values={"input": {"coordinateSystem": str(world.pk), "policy": {}}},
    )
    assert rejected.errors and "hub" in str(rejected.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_rerun_makes_a_second_scene_and_leaves_the_hub_untouched(authenticated_context: HttpContext):
    """Everything created is ordinary: run it twice and there are two scenes; the registrations are one copy."""
    dataset = await seed.create_adataset(authenticated_context, "Once", shapes=[[3, 48, 48]])
    hub = await _create_hub(authenticated_context, "Reused", [_register("dataset", str(dataset.pk))])

    first = await _scene_from(authenticated_context, hub["id"])
    second = await _scene_from(authenticated_context, hub["id"])
    assert first["id"] != second["id"]
    # Two scenes, one space: both adopt the very same hub as their world.
    assert first["worldCoordinateSystem"]["id"] == second["worldCoordinateSystem"]["id"] == hub["id"]

    # The hub's own registration edges are untouched -- still exactly one, shared, not
    # copied per scene. Nothing is authored per run: the scene composes over the hub itself.
    registered = await sync_to_async(models.Transformation.objects.filter(output__pk=hub["id"], parent__isnull=True).count)()
    assert registered == 1
    for scene in (first, second):
        assert len(scene["layers"]) == 1
        assert scene["layers"][0]["pathToWorld"] is not None


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_non_renderable_dataset_is_skipped_not_fatal(authenticated_context: HttpContext):
    """A registered dataset too small to render is skipped, exactly like a table with too few
    coordinate columns -- it does not abort the batch and place nothing."""
    good = await seed.create_adataset(authenticated_context, "Good", shapes=[[3, 64, 64]])
    # x is a single pixel: not renderable.
    tiny = await seed.create_adataset(authenticated_context, "Tiny", axes=seed.YX_AXES, shapes=[[64, 1]])

    hub = await _create_hub(
        authenticated_context,
        "Mixed",
        [_register("dataset", str(tiny.pk)), _register("dataset", str(good.pk))],
    )

    scene = await _scene_from(authenticated_context, hub["id"])

    # Only the renderable one becomes a layer; the tiny one is silently skipped.
    (layer,) = scene["layers"]
    assert layer["kind"] == "IMAGE"
    assert layer["pathToWorld"] is not None
    placed_dataset_id = await sync_to_async(lambda: models.Layer.objects.get(scene__pk=scene["id"]).lens.dataset_id)()
    assert placed_dataset_id == good.pk


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_calibrated_dataset_registers_through_its_physical_system(authenticated_context: HttpContext):
    """The natural calibrated workflow: register a dataset by its PHYSICAL calibration, not its
    intrinsic pixels. The layer's real source is intrinsic, yet its path to world resolves --
    the walk crosses the dataset's own (non-member) calibration edge to reach the composed
    PHYSICAL->hub registration."""
    dataset = await seed.create_adataset(authenticated_context, "Cal", axes=seed.YX_AXES, shapes=[[64, 64]])
    await seed.create_calibration(
        authenticated_context,
        dataset,
        axes=[seed.calibrated_axis("y", enums.AxisType.SPACE, "micrometer"), seed.calibrated_axis("x", enums.AxisType.SPACE, "micrometer")],
        scale=[0.325, 0.325],
    )
    physical = await sync_to_async(lambda: dataset.calibrations.get())()

    hub = await _create_hub(authenticated_context, "PhysAtlas", [_register("coordinateSystem", str(physical.pk))])

    scene = await _scene_from(authenticated_context, hub["id"])

    (layer,) = scene["layers"]
    assert layer["kind"] == "IMAGE"
    assert layer["placement"] == "PLACED"
    assert layer["pathToWorld"] is not None, "the layer's intrinsic source could not reach world through the PHYSICAL registration"


def test_the_schema_exposes_the_hub_mutations():
    """The SDL is the contract: both mutations exist, and the hub kind is created directly."""
    sdl = schema.as_str()
    assert "createCoordinateSystem(" in sdl
    assert "createSceneFromCoordinateSystem(" in sdl
    assert "input CreateSceneFromCoordinateSystemInput " in sdl
    assert "input ScenePolicyInput " in sdl
