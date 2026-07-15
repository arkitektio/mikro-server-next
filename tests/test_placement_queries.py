"""The scene and placement API must not scale its query count with its layer count.

Every placement field (`pathToWorld`, `levelPaths`, `coordinateSystems`, `rois`) is a
custom resolver over the coordinate graph, so the strawberry-django optimizer cannot see
what it touches: it walks `layer.lens.coordinate_system` for a client that selected
nothing but `pathToWorld`. Left alone, each layer rebuilt the scene's adjacency from
scratch and the reachability closure ran once per field.

These tests pin the property that fixes rather than the fix: **the same query count for a
scene of three layers and a scene of seven**. A count that grows with the layers is the N+1
coming back, whatever shape it returns in. Each scene carries one image layer at minimum,
so every placement field is actually exercised at both sizes.
"""

import threading

import pytest
from asgiref.sync import sync_to_async
from django.db.backends import utils as db_utils
from kante.context import HttpContext, UniversalRequest
from strawberry.http.temporal_response import TemporalResponse

from core import enums, models
from mikro_server.schema import schema
from tests import seed


def _fresh_request(ctx: HttpContext) -> HttpContext:
    """A new request for the same identity.

    Per-request state (the scene-graph memo, the auth extension's caches) lives on the
    context, so reusing one across two executions would let the second ride on the first's
    warm caches -- and a query count measured that way is not the one a real client pays.
    """
    request = UniversalRequest(
        _extensions={"token": "test"},
        _client=ctx.request._client,
        _user=ctx.request._user,
        _organization=ctx.request._organization,
    )
    request.set_membership(ctx.request._membership)  # type: ignore[arg-type]
    return HttpContext(request=request, response=TemporalResponse(), headers=ctx.headers, type="http")


class QueryCounter:
    """Counts every SQL statement, on any thread.

    Not `django_assert_num_queries`: the schema is executed async, so the ORM work
    happens on asgiref's executor thread, whose connection is a different object from
    the one the test thread would instrument. Patching the cursor catches all of them.
    """

    def __init__(self) -> None:
        self.queries: list[str] = []
        self._lock = threading.Lock()

    def __enter__(self) -> "QueryCounter":
        self._execute = db_utils.CursorWrapper.execute
        self._executemany = db_utils.CursorWrapper.executemany

        def execute(inner, sql, params=None):
            with self._lock:
                self.queries.append(sql)
            return self._execute(inner, sql, params)

        def executemany(inner, sql, param_list):
            with self._lock:
                self.queries.append(sql)
            return self._executemany(inner, sql, param_list)

        db_utils.CursorWrapper.execute = execute
        db_utils.CursorWrapper.executemany = executemany
        return self

    def __exit__(self, *exc) -> None:
        db_utils.CursorWrapper.execute = self._execute
        db_utils.CursorWrapper.executemany = self._executemany

    def __len__(self) -> int:
        return len(self.queries)


SCENE_PLACEMENTS = """
query ScenePlacements {
  scenes {
    id
    layers {
      id
      pathToWorld { inverted transformation { id kind inputAxes outputAxes ... on SequenceTransformation { transformations { id kind inputAxes outputAxes } } } }
      ... on ImageLayer {
        levelPaths {
          dataArray { id level }
          path { inverted transformation { id kind inputAxes outputAxes ... on SequenceTransformation { transformations { id kind inputAxes outputAxes } } } }
        }
      }
    }
    coordinateSystems { id kind }
    rois { id }
  }
}
"""

ROOT_LAYERS = """
query RootLayers {
  layers {
    id
    pathToWorld { inverted transformation { id kind inputAxes outputAxes ... on SequenceTransformation { transformations { id kind inputAxes outputAxes } } } }
    ... on ImageLayer {
      levelPaths {
        dataArray { id level }
        path { inverted transformation { id kind inputAxes outputAxes ... on SequenceTransformation { transformations { id kind inputAxes outputAxes } } } }
      }
    }
  }
}
"""

#: A three-level pyramid, so `levelPaths` has more than one level to place.
_SHAPES = [[3, 64, 64], [3, 32, 32], [3, 16, 16]]

_AFFINE = [
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 1.0, 0.0, 0.0],
    [0.0, 0.0, 1.0, 0.0],
    [0.0, 0.0, 0.0, 1.0],
]


async def _seed_scene(ctx: HttpContext, *, layer_count: int) -> models.Scene:
    """A scene of `layer_count` layers spread over two registered datasets.

    Two datasets, not one: a single-dataset scene would not catch an adjacency that is
    rebuilt per dataset, and both datasets' edges have to stay in their own adjacency for
    the BFS to keep returning the path it returns today.

    The last two layers are a *shape* layer over a real ROI and a *mesh* layer over a mesh
    collection, so the seed covers the two source systems that are not reached through a
    lens. The mesh layer matters twice over: a collection owns its coordinate system, so
    resolving which dataset it belongs to means following its anchor edge, and doing that
    one layer at a time is a query per layer -- exactly the N+1 these tests exist to catch,
    on a path they would otherwise never touch.
    """
    datasets = [await seed.create_adataset(ctx, f"Placed{index}", shapes=_SHAPES) for index in range(2)]
    lenses = [await seed.create_lens(ctx, dataset, slices=[{"axis": "y", "start": 8, "stop": 40}]) for dataset in datasets]
    scene = await seed.create_scene(ctx, "Composition")

    def setup() -> None:
        world = scene.world_coordinate_system
        for index in range(layer_count - 2):
            models.Layer.objects.create(
                kind=enums.LayerKindChoices.IMAGE.value,
                scene=scene,
                lens=lenses[index % len(lenses)],
            )

        # No organization: an ROI is scoped through the coordinate system it is drawn in.
        roi = models.DataRoi.objects.create(
            coordinate_system=datasets[0].intrinsic_coordinate_system,
            name="Region",
            kind=enums.RoiKindChoices.RECTANGLE.value,
            vectors=[[0.0, 0.0, 0.0], [0.0, 8.0, 8.0]],
        )
        models.Layer.objects.create(kind=enums.LayerKindChoices.SHAPE.value, scene=scene, data_roi=roi)

        # Keyed by scene: the store path is globally unique, and each measurement seeds a
        # fresh scene.
        key = f"mesh-catalog-{scene.pk}"
        catalog = models.ParquetStore.objects.create(path=f"s3://parquet/{key}", bucket="parquet", key=key, organization=ctx.request.organization)
        collection = models.MeshCollection.objects.create(version="v1", spec_version="1.0", catalog=catalog, organization=ctx.request.organization)
        mesh_system = models.CoordinateSystem.objects.create(
            name="v1/mesh",
            kind=enums.CoordinateSystemKindChoices.MESH.value,
            mesh_collection=collection,
            organization=ctx.request.organization,
        )
        for index, axis in enumerate(datasets[0].intrinsic_coordinate_system.axes.all().order_by("order")):
            models.Axis.objects.create(coordinate_system=mesh_system, order=index, name=axis.name, type=axis.type)
        models.Transformation.objects.create(
            kind=enums.TransformKindChoices.IDENTITY.value,
            input=mesh_system,
            output=datasets[0].intrinsic_coordinate_system,
            organization=ctx.request.organization,
        )
        models.Layer.objects.create(kind=enums.LayerKindChoices.MESH.value, scene=scene, mesh_collection=collection)

        for dataset in datasets:
            edge = models.Transformation.objects.create(
                kind=enums.TransformKindChoices.AFFINE.value,
                input=dataset.intrinsic_coordinate_system,
                output=world,
                params={"affine": _AFFINE},
                organization=ctx.request.organization,
            )
            scene.coordinate_transformations.add(edge)

    await sync_to_async(setup)()
    return scene


async def _execute(ctx: HttpContext, query: str) -> tuple[dict, int]:
    """The query's data and the number of SQL statements one fresh request costs.

    Warmed once and measured on a second, separate request: the first execution of a
    process pays one-off costs (content types, permissions) that no steady-state client
    pays, and counting them would bury the thing under test.
    """
    await schema.execute(query, context_value=_fresh_request(ctx))

    counted = _fresh_request(ctx)
    with QueryCounter() as counter:
        result = await schema.execute(query, context_value=counted)
    assert not result.errors, result.errors
    return result.data, len(counter)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_scene_placements_are_flat_in_layer_count(authenticated_context: HttpContext):
    """Asking a scene for its layers' placements costs the same at 7 layers as at 3."""
    await _seed_scene(authenticated_context, layer_count=3)
    small_data, small_queries = await _execute(authenticated_context, SCENE_PLACEMENTS)

    await models.Scene.objects.all().adelete()
    await _seed_scene(authenticated_context, layer_count=7)
    large_data, large_queries = await _execute(authenticated_context, SCENE_PLACEMENTS)

    assert len(small_data["scenes"][0]["layers"]) == 3
    assert len(large_data["scenes"][0]["layers"]) == 7
    assert large_queries == small_queries, f"the placement query count grows with the layers: {small_queries} for 3 layers, {large_queries} for 7"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_root_layers_are_flat_in_layer_count(authenticated_context: HttpContext):
    """The same, through the root `layers` field rather than through a scene."""
    await _seed_scene(authenticated_context, layer_count=3)
    small_data, small_queries = await _execute(authenticated_context, ROOT_LAYERS)

    await models.Scene.objects.all().adelete()
    await _seed_scene(authenticated_context, layer_count=7)
    large_data, large_queries = await _execute(authenticated_context, ROOT_LAYERS)

    assert len(small_data["layers"]) == 3
    assert len(large_data["layers"]) == 7
    assert large_queries == small_queries, f"the root layer query count grows with the layers: {small_queries} for 3 layers, {large_queries} for 7"


CREATE_LAYER = """
mutation Make($input: CreateIntensityLayerInput!) {
  createIntensityLayer(input: $input) { id }
}
"""


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_creating_a_layer_is_flat_in_scene_size(authenticated_context: HttpContext):
    """Placing one more layer costs the same in a 7-layer scene as in a 3-layer one.

    The placement check a layer mutation runs (is this source placeable in this scene?)
    must fetch a universe whose size depends on the dataset and the world, not on the
    layer count -- the full SceneGraph, which walks every layer and every co-tenant
    dataset's edges, would make assembling a scene slower with every layer already in it.
    """

    async def measure(layer_count: int) -> int:
        scene = await _seed_scene(authenticated_context, layer_count=layer_count)
        # A fresh dataset, registered as its own seed step: the measured mutation is the
        # layer creation alone, and its placement check runs the full BFS in both scenes.
        dataset = await seed.create_adataset(authenticated_context, f"Incoming{layer_count}", shapes=_SHAPES)
        lens = await seed.create_lens(authenticated_context, dataset, slices=[])
        await seed.register_into_scene(authenticated_context, scene, dataset)

        variables = {"input": {"scene": str(scene.pk), "lens": str(lens.pk), "intensityAxis": "c"}}

        counted = _fresh_request(authenticated_context)
        with QueryCounter() as counter:
            result = await schema.execute(CREATE_LAYER, context_value=counted, variable_values=variables)
        assert not result.errors, result.errors
        return len(counter)

    # Warm the process-lifetime caches (content types, auth) on a throwaway scene first.
    await measure(1)
    await models.Scene.objects.all().adelete()
    await models.ADataset.objects.all().adelete()

    small_queries = await measure(3)
    await models.Scene.objects.all().adelete()
    await models.ADataset.objects.all().adelete()

    large_queries = await measure(7)
    assert large_queries == small_queries, f"creating a layer costs more in a bigger scene: {small_queries} queries at 3 layers, {large_queries} at 7"
