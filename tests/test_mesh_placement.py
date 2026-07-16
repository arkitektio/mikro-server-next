"""A mesh layer must reach world, before and after the collection owns its own system.

Nothing covered this. `createMeshLayer` builds a layer over the *legacy* `Mesh` (a
BigFileStore), so a layer over a `MeshCollection` can only be authored through the ORM --
and its placement, which runs through `layer_source_system` -> `mesh_collection
.coordinate_system`, had no test at all.

That matters right now, because the collection is about to stop *borrowing* the dataset's
intrinsic system and start *owning* one, anchored to the dataset by an edge. If the
placement search cannot resolve the collection's own system back to its dataset, a mesh
layer silently loses its path to world and every existing test still passes. So this file
is written first, against the old shape, and must stay green through the change.
"""

import pytest
from asgiref.sync import sync_to_async
from kante.context import HttpContext

from core import enums, models
from mikro_server.schema import schema
from tests import seed

PLACEMENT = """
query Placement($id: ID!) {
  scene(id: $id) {
    layers {
      id
      pathToWorld {
        inverted
        transformation { id kind input { id kind } output { id kind } }
      }
    }
  }
}
"""

_AFFINE_3D = [
    [1.0, 0.0, 0.0, 5.0],
    [0.0, 1.0, 0.0, 5.0],
    [0.0, 0.0, 1.0, 0.0],
]


async def _mesh_collection(ctx: HttpContext, dataset: models.ADataset) -> models.MeshCollection:
    """A collection over a dataset's meshes, through the real mutation."""

    def stores() -> tuple[models.ParquetStore, models.ParquetStore]:
        catalog = models.ParquetStore.objects.create(path="s3://parquet/catalog", bucket="parquet", key="catalog", organization=ctx.request.organization)
        shard = models.ParquetStore.objects.create(path="s3://parquet/geometry-0", bucket="parquet", key="geometry-0", organization=ctx.request.organization)
        return catalog, shard

    catalog, shard = await sync_to_async(stores)()
    system = await sync_to_async(lambda: dataset.intrinsic_coordinate_system)()

    result = await schema.execute(
        """
        mutation Create($input: CreateMeshCollectionInput!) {
          createMeshCollection(input: $input) { id coordinateSystem { id kind } }
        }
        """,
        context_value=ctx,
        variable_values={
            "input": {
                "coordinateSystem": str(system.pk),
                "version": "v1",
                "specVersion": "1.0",
                "catalog": str(catalog.pk),
                "geometry": [str(shard.pk)],
            }
        },
    )
    assert not result.errors, result.errors
    return await sync_to_async(models.MeshCollection.objects.get)(pk=result.data["createMeshCollection"]["id"])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_mesh_layer_reaches_world(authenticated_context: HttpContext):
    """The meshes were extracted from a dataset, so they go where that dataset went."""
    dataset = await seed.create_adataset(authenticated_context, "Labels")
    collection = await _mesh_collection(authenticated_context, dataset)
    scene = await seed.create_scene(authenticated_context, "Composition")

    def place() -> None:
        models.Transformation.objects.create(
            kind=enums.TransformKindChoices.AFFINE.value,
            input=dataset.intrinsic_coordinate_system,
            output=scene.world_coordinate_system,
            params={"affine": _AFFINE_3D},
            organization=authenticated_context.request.organization,
        )
        # No mutation authors a mesh-collection layer: createMeshLayer is for the legacy
        # Mesh. The ORM is the only way in, which is why this path went untested.
        models.Layer.objects.create(kind=enums.LayerKindChoices.MESH.value, scene=scene, mesh_collection=collection)

    await sync_to_async(place)()

    result = await schema.execute(PLACEMENT, context_value=authenticated_context, variable_values={"id": str(scene.pk)})
    assert not result.errors, result.errors

    path = result.data["scene"]["layers"][0]["pathToWorld"]
    assert path is not None, "a mesh layer is placed by the dataset its meshes were extracted from"
    assert path[-1]["transformation"]["output"]["kind"] == "SHARED"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_unregistered_mesh_layer_has_no_path(authenticated_context: HttpContext):
    """The mirror image: nothing is registered, so there is nothing to inherit.

    Without this, a change that made every mesh layer resolve to *some* path would still
    look green against the test above.
    """
    dataset = await seed.create_adataset(authenticated_context, "Labels")
    collection = await _mesh_collection(authenticated_context, dataset)
    scene = await seed.create_scene(authenticated_context, "Composition")

    await sync_to_async(models.Layer.objects.create)(kind=enums.LayerKindChoices.MESH.value, scene=scene, mesh_collection=collection)

    result = await schema.execute(PLACEMENT, context_value=authenticated_context, variable_values={"id": str(scene.pk)})
    assert not result.errors, result.errors

    assert result.data["scene"]["layers"][0]["pathToWorld"] is None
