"""A feature table is a node in the graph, and the edge to its image says nothing maps.

Per-object measurements had nowhere to live. A `Table` is anchored by whatever `Layer`
happens to point at it, which is right for a point cloud (its columns *are* positions) and
wrong for a measurement table, whose rows are objects. So the table could not be a node,
and its relation to the image it was measured from could not be an edge, and the lineage
was simply not recorded.

It is a collection now, shaped like `MeshCollection`: parquet-backed, versioned, immutable,
resolving to a store rather than to rows. What it does *not* share with a mesh collection is
where it sits: a mesh really is in the label array's voxel grid, and a feature table is
nowhere at all -- so it owns a FEATURE system whose one INDEX axis enumerates the objects,
and the edge relating it to the image is UNMAPPABLE.
"""

import pytest
from asgiref.sync import sync_to_async
from kante.context import HttpContext

from core import models
from mikro_server.schema import schema
from tests import seed

CREATE = """
mutation Create($input: CreateFeatureCollectionInput!) {
  createFeatureCollection(input: $input) {
    id
    name
    version
    store { id key }
    coordinateSystem { id kind axes { name type unit } }
    derivedFrom {
      id kind
      output { id kind }
      ... on UnmappableTransformation { reason }
    }
  }
}
"""


async def _parquet(ctx: HttpContext, key: str) -> models.ParquetStore:
    return await sync_to_async(models.ParquetStore.objects.create)(path=f"s3://parquet/{key}", bucket="parquet", key=key, organization=ctx.request.organization)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_feature_collection_lives_in_a_space_of_its_own(authenticated_context: HttpContext):
    """It owns a FEATURE system, and the edge back to the image is UNMAPPABLE."""
    dataset = await seed.create_adataset(authenticated_context, "Labels")
    store = await _parquet(authenticated_context, "features")
    system = await sync_to_async(lambda: dataset.intrinsic_coordinate_system)()

    result = await schema.execute(
        CREATE,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "name": "nuclei morphology",
                "version": "v1",
                "store": str(store.pk),
                "coordinateSystem": str(system.pk),
            }
        },
    )
    assert not result.errors, result.errors

    collection = result.data["createFeatureCollection"]

    # Its own space: one axis, enumerating the objects. Not the image's pixel grid -- there
    # is no pixel of the image that IS row 7.
    assert collection["coordinateSystem"]["kind"] == "FEATURE"
    axes = collection["coordinateSystem"]["axes"]
    assert [axis["name"] for axis in axes] == ["object"]
    assert axes[0]["type"] == "INDEX"
    assert axes[0]["unit"] is None, "an index has no unit: the distance between object 3 and object 4 means nothing"

    # And the relation to the image it was measured from is recorded, and is a denial.
    assert collection["derivedFrom"]["kind"] == "UNMAPPABLE"
    assert collection["derivedFrom"]["output"]["id"] == str(system.pk)

    # The Parquet went through the datalayer like every other Parquet object.
    assert await models.ParquetStore.objects.filter(pk=store.pk, populated=True).aexists()

    # No `rows` field, for the reason MeshCollection has no `meshes`: a paginated list would
    # look natural and would end up walking millions of Parquet rows through GraphQL.
    sdl = schema.as_str()
    definition = sdl[sdl.find("type FeatureCollection ") : sdl.find("\n}", sdl.find("type FeatureCollection "))]
    assert "\n  rows" not in definition
    assert "\n  features" not in definition


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_the_table_is_discoverable_from_the_image_and_unreachable_from_it(authenticated_context: HttpContext):
    """Both halves of the design, in one test.

    From the image's own system, `coordinateGraph` finds the table -- that is how a client
    answers "what was measured from this?" -- while no placement search can cross the edge,
    because there is nothing on the other side of it that is anywhere.
    """
    dataset = await seed.create_adataset(authenticated_context, "Labels")
    store = await _parquet(authenticated_context, "features")
    system = await sync_to_async(lambda: dataset.intrinsic_coordinate_system)()

    created = await schema.execute(
        CREATE,
        context_value=authenticated_context,
        variable_values={"input": {"name": "nuclei", "version": "v1", "store": str(store.pk), "coordinateSystem": str(system.pk)}},
    )
    assert not created.errors, created.errors
    feature_system_id = created.data["createFeatureCollection"]["coordinateSystem"]["id"]

    result = await schema.execute(
        """
        query Graph($id: ID!) {
          coordinateGraph(coordinateSystem: $id) {
            systems { id kind }
            transformations { id kind }
          }
        }
        """,
        context_value=authenticated_context,
        variable_values={"id": str(system.pk)},
    )
    assert not result.errors, result.errors

    graph = result.data["coordinateGraph"]
    assert feature_system_id in [s["id"] for s in graph["systems"]], "discovery is kind-blind: the table is related to this image, and that is worth finding"
    assert "UNMAPPABLE" in [edge["kind"] for edge in graph["transformations"]]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_identity_to_a_feature_space_is_rejected(authenticated_context: HttpContext):
    """Claiming a correspondence to a table of objects has to survive the rank check.

    Nothing special-cases this. An IDENTITY says the two spaces ARE the same, and a
    three-axis pixel grid is not a one-axis enumeration of objects -- the same check that
    catches a projection wearing an identity's clothes catches this, because it is the same
    mistake.
    """
    dataset = await seed.create_adataset(authenticated_context, "Labels")
    store = await _parquet(authenticated_context, "features")
    system = await sync_to_async(lambda: dataset.intrinsic_coordinate_system)()

    result = await schema.execute(
        CREATE,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "name": "nuclei",
                "version": "v1",
                "store": str(store.pk),
                "coordinateSystem": str(system.pk),
                "derivedFrom": {"kind": "IDENTITY"},
            }
        },
    )
    assert result.errors, "a (c,y,x) image and a one-axis table of objects are not the same space"
    assert "IDENTITY" in str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_freestanding_table_is_allowed_and_relates_to_nothing(authenticated_context: HttpContext):
    """The anchor is optional: a table measured from nothing in this system has no edge.

    It is not an error, it is an absence -- and it reads differently from an UNMAPPABLE
    edge, which is a *statement*. One says "I do not know where this came from", the other
    says "I know exactly where it came from, and none of it is anywhere".
    """
    store = await _parquet(authenticated_context, "orphan")

    result = await schema.execute(
        CREATE,
        context_value=authenticated_context,
        variable_values={"input": {"name": "imported", "version": "v1", "store": str(store.pk)}},
    )
    assert not result.errors, result.errors

    collection = result.data["createFeatureCollection"]
    assert collection["coordinateSystem"]["kind"] == "FEATURE"
    assert collection["derivedFrom"] is None
