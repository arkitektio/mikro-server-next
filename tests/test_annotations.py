"""Tests for annotations and their collections.

The scene path of ``createAnnotation`` is the load-bearing sugar: the first
shape drawn on a scene mints the scene's collection -- its own coordinate
system mirroring the world's axes, a VALIDATED identity registration into the
world, and one annotation layer -- and every later shape appends to all of it.
The collection path stays inert: appending never touches layers or edges.
"""

import pytest
from asgiref.sync import sync_to_async

from core import enums, models
from kante.context import HttpContext
from mikro_server.schema import schema
from tests import seed


CREATE = """
mutation Create($input: CreateAnnotationInput!) {
  createAnnotation(input: $input) {
    id
    name
    kind
    vectors
    strokeWidth
    filled
    createdWithTransforms
    intrinsicBbox { min max }
    collection { id name scene { id } coordinateSystem { id kind } }
  }
}
"""


def _counts(scene: "models.Scene") -> dict:
    return {
        "collections": models.AnnotationCollection.objects.count(),
        "systems": models.CoordinateSystem.objects.filter(annotation_collection__isnull=False).count(),
        "layers": models.Layer.objects.filter(scene=scene, kind=enums.LayerKindChoices.ANNOTATION.value).count(),
        "registrations": models.Transformation.objects.filter(parent__isnull=True, output=scene.world).count(),
    }


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_drawing_on_a_scene_mints_its_collection(db, authenticated_context: HttpContext):
    """The first annotation mints collection + system + registration + layer; the second reuses them all."""
    ctx = authenticated_context
    scene = await seed.create_scene(ctx, "Canvas")

    result = await schema.execute(
        CREATE,
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "kind": "POINT", "vectors": [[1.0, 2.0, 3.0]]}},
    )
    assert not result.errors, result.errors
    first = result.data["createAnnotation"]
    assert first["collection"]["scene"]["id"] == str(scene.id)
    assert first["collection"]["coordinateSystem"]["kind"] == "INTRINSIC"
    assert first["strokeWidth"] == 1.0

    counts = await sync_to_async(_counts)(scene)
    assert counts == {"collections": 1, "systems": 1, "layers": 1, "registrations": 1}

    def registration():
        edge = models.Transformation.objects.get(parent__isnull=True, output=scene.world)
        system = models.CoordinateSystem.objects.get(annotation_collection__isnull=False)
        world_axes = [axis.name for axis in scene.world.axes.all().order_by("order")]
        drawing_axes = [axis.name for axis in system.axes.all().order_by("order")]
        return edge, world_axes, drawing_axes

    edge, world_axes, drawing_axes = await sync_to_async(registration)()
    assert drawing_axes == world_axes, "the drawing space mirrors the world's axes"
    assert edge.kind == enums.TransformKindChoices.BY_DIMENSION.value
    assert edge.validity == enums.PlacementValidityChoices.VALIDATED.value, "the mirror is exact by construction"

    # The second shape appends: nothing new is minted.
    result = await schema.execute(
        CREATE,
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "kind": "POINT", "vectors": [[4.0, 5.0, 6.0]]}},
    )
    assert not result.errors, result.errors
    second = result.data["createAnnotation"]
    assert second["collection"]["id"] == first["collection"]["id"]

    counts = await sync_to_async(_counts)(scene)
    assert counts == {"collections": 1, "systems": 1, "layers": 1, "registrations": 1}
    assert await models.Annotation.objects.acount() == 2


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_collection_xor_scene(db, authenticated_context: HttpContext):
    """Exactly one of collection/scene: both or neither is an authoring error."""
    ctx = authenticated_context
    scene = await seed.create_scene(ctx)

    neither = await schema.execute(
        CREATE,
        context_value=ctx,
        variable_values={"input": {"kind": "POINT", "vectors": [[0.0, 0.0, 0.0]]}},
    )
    assert neither.errors, "neither collection nor scene must be refused"

    first = await schema.execute(
        CREATE,
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "kind": "POINT", "vectors": [[0.0, 0.0, 0.0]]}},
    )
    assert not first.errors, first.errors
    collection_id = first.data["createAnnotation"]["collection"]["id"]

    both = await schema.execute(
        CREATE,
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "collection": collection_id, "kind": "POINT", "vectors": [[0.0, 0.0, 0.0]]}},
    )
    assert both.errors, "collection and scene together must be refused"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_drawing_into_a_collection_appends_only(db, authenticated_context: HttpContext):
    """The collection path never touches layers or edges."""
    ctx = authenticated_context
    scene = await seed.create_scene(ctx)

    first = await schema.execute(
        CREATE,
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "kind": "POINT", "vectors": [[0.0, 0.0, 0.0]]}},
    )
    assert not first.errors, first.errors
    collection_id = first.data["createAnnotation"]["collection"]["id"]
    counts_before = await sync_to_async(_counts)(scene)

    appended = await schema.execute(
        CREATE,
        context_value=ctx,
        variable_values={"input": {"collection": collection_id, "kind": "PATH", "vectors": [[1.0, 1.0, 1.0], [2.0, 2.0, 2.0]]}},
    )
    assert not appended.errors, appended.errors
    assert appended.data["createAnnotation"]["collection"]["id"] == collection_id
    assert await sync_to_async(_counts)(scene) == counts_before


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_annotation_layer_in_a_second_scene_needs_a_registration(db, authenticated_context: HttpContext):
    """A foreign scene refuses the layer as UNREGISTERED until the registration is authored."""
    ctx = authenticated_context
    scene_a = await seed.create_scene(ctx, "Home")
    scene_b = await seed.create_scene(ctx, "Away")

    first = await schema.execute(
        CREATE,
        context_value=ctx,
        variable_values={"input": {"scene": str(scene_a.id), "kind": "POINT", "vectors": [[0.0, 0.0, 0.0]]}},
    )
    assert not first.errors, first.errors
    collection_id = first.data["createAnnotation"]["collection"]["id"]

    layer_mutation = "mutation M($i: CreateAnnotationLayerInput!) { createAnnotationLayer(input: $i) { id } }"
    refused = await schema.execute(
        layer_mutation,
        context_value=ctx,
        variable_values={"i": {"scene": str(scene_b.id), "annotationCollection": collection_id}},
    )
    assert refused.errors, "an unregistered collection must be refused in a foreign scene"
    assert "createTransformation" in str(refused.errors[0])

    def collection_system():
        return models.AnnotationCollection.objects.get(pk=collection_id).coordinate_system

    system = await sync_to_async(collection_system)()
    await seed.register_into_scene(ctx, scene_b, system=system)

    allowed = await schema.execute(
        layer_mutation,
        context_value=ctx,
        variable_values={"i": {"scene": str(scene_b.id), "annotationCollection": collection_id}},
    )
    assert not allowed.errors, allowed.errors


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_update_annotation_recomputes_derived_fields(db, authenticated_context: HttpContext):
    """New vectors re-derive the bounding box; the rest edits in place."""
    ctx = authenticated_context
    scene = await seed.create_scene(ctx)

    made = await schema.execute(
        CREATE,
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "kind": "POINT", "vectors": [[1.0, 2.0, 3.0]]}},
    )
    assert not made.errors, made.errors
    annotation = made.data["createAnnotation"]
    bbox_before = annotation["intrinsicBbox"]

    update = """
    mutation Update($input: UpdateAnnotationInput!) {
      updateAnnotation(input: $input) {
        id
        name
        filled
        vectors
        intrinsicBbox { min max }
      }
    }
    """
    result = await schema.execute(
        update,
        context_value=ctx,
        variable_values={"input": {"id": annotation["id"], "name": "Renamed", "filled": True, "vectors": [[10.0, 20.0, 30.0]]}},
    )
    assert not result.errors, result.errors
    updated = result.data["updateAnnotation"]
    assert updated["name"] == "Renamed"
    assert updated["filled"] is True
    assert updated["vectors"] == [[10.0, 20.0, 30.0]]
    assert updated["intrinsicBbox"] != bbox_before, "moved vectors must move the derived box"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_delete_guards(db, authenticated_context: HttpContext, bot_context: HttpContext):
    """Only the creator (or an admin) deletes; a same-org bot without ownership is denied."""
    ctx = authenticated_context
    scene = await seed.create_scene(ctx)

    made = await schema.execute(
        CREATE,
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "kind": "POINT", "vectors": [[0.0, 0.0, 0.0]]}},
    )
    assert not made.errors, made.errors
    annotation = made.data["createAnnotation"]
    collection_id = annotation["collection"]["id"]

    delete_annotation = "mutation D($input: DeleteAnnotationInput!) { deleteAnnotation(input: $input) }"
    denied = await schema.execute(delete_annotation, context_value=bot_context, variable_values={"input": {"id": annotation["id"]}})
    assert denied.errors, "a non-owner non-admin must not delete an annotation"
    assert await models.Annotation.objects.filter(pk=annotation["id"]).aexists()

    delete_collection = "mutation D($input: DeleteAnnotationCollectionInput!) { deleteAnnotationCollection(input: $input) }"
    denied = await schema.execute(delete_collection, context_value=bot_context, variable_values={"input": {"id": collection_id}})
    assert denied.errors, "a non-owner non-admin must not delete a collection"

    allowed = await schema.execute(delete_annotation, context_value=ctx, variable_values={"input": {"id": annotation["id"]}})
    assert not allowed.errors, allowed.errors
    assert not await models.Annotation.objects.filter(pk=annotation["id"]).aexists()

    allowed = await schema.execute(delete_collection, context_value=ctx, variable_values={"input": {"id": collection_id}})
    assert not allowed.errors, allowed.errors
    assert not await models.AnnotationCollection.objects.filter(pk=collection_id).aexists()
    assert not await models.CoordinateSystem.objects.filter(annotation_collection__isnull=False).aexists(), "the drawing system cascades with its collection"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_coordinates_surface(db, authenticated_context: HttpContext):
    """Pins go in and come back as named coordinates; an update replaces the whole set."""
    ctx = authenticated_context
    scene = await seed.create_scene(ctx)

    made = await schema.execute(
        CREATE,
        context_value=ctx,
        variable_values={
            "input": {
                "scene": str(scene.id),
                "kind": "POINT",
                "vectors": [[0.0, 0.0, 0.0]],
                "coordinates": [{"name": "t", "value": 0}, {"name": "c", "value": 2}],
            }
        },
    )
    assert not made.errors, made.errors
    annotation_id = made.data["createAnnotation"]["id"]

    query = "query Get($id: ID!) { annotation(id: $id) { coordinates { name value } } }"
    result = await schema.execute(query, context_value=ctx, variable_values={"id": annotation_id})
    assert not result.errors, result.errors
    pins = {c["name"]: c["value"] for c in result.data["annotation"]["coordinates"]}
    assert pins == {"t": 0, "c": 2}

    update = "mutation U($input: UpdateAnnotationInput!) { updateAnnotation(input: $input) { coordinates { name value } } }"
    result = await schema.execute(
        update,
        context_value=ctx,
        variable_values={"input": {"id": annotation_id, "coordinates": [{"name": "t", "value": 5}]}},
    )
    assert not result.errors, result.errors
    pins = {c["name"]: c["value"] for c in result.data["updateAnnotation"]["coordinates"]}
    assert pins == {"t": 5}, "the whole pin set is replaced, not merged"


async def _draw(ctx: HttpContext, target: dict, **fields) -> dict:
    """One shape via createAnnotation; returns the payload."""
    result = await schema.execute(
        CREATE,
        context_value=ctx,
        variable_values={"input": {**target, "kind": "POINT", **fields}},
    )
    assert not result.errors, result.errors
    return result.data["createAnnotation"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_pinned_to_filter(db, authenticated_context: HttpContext):
    """Containment on the pinned dict: spanning a coordinate never matches a pin on it."""
    ctx = authenticated_context
    scene = await seed.create_scene(ctx)

    first = await _draw(ctx, {"scene": str(scene.id)}, name="both", vectors=[[0.0, 0.0, 0.0]], coordinates=[{"name": "t", "value": 0}, {"name": "c", "value": 0}])
    collection_id = first["collection"]["id"]
    target = {"collection": collection_id}
    await _draw(ctx, target, name="t3", vectors=[[1.0, 1.0, 1.0]], coordinates=[{"name": "t", "value": 3}])
    await _draw(ctx, target, name="spanning", vectors=[[2.0, 2.0, 2.0]])

    query = "query L($filters: AnnotationFilter) { annotations(filters: $filters) { name } }"

    result = await schema.execute(query, context_value=ctx, variable_values={"filters": {"pinnedTo": [{"name": "t", "value": 3}]}})
    assert not result.errors, result.errors
    assert {a["name"] for a in result.data["annotations"]} == {"t3"}

    result = await schema.execute(query, context_value=ctx, variable_values={"filters": {"pinnedTo": [{"name": "t", "value": 0}, {"name": "c", "value": 0}]}})
    assert not result.errors, result.errors
    assert {a["name"] for a in result.data["annotations"]} == {"both"}

    result = await schema.execute(query, context_value=ctx, variable_values={"filters": {"pinnedTo": [{"name": "z", "value": 0}]}})
    assert not result.errors, result.errors
    assert result.data["annotations"] == [], "a spanning annotation never matches a pin"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_spatial_filters(db, authenticated_context: HttpContext):
    """Overlap and point containment against the cube column, scoped to one frame."""
    ctx = authenticated_context
    scene = await seed.create_scene(ctx)

    first = await _draw(ctx, {"scene": str(scene.id)}, name="near", vectors=[[0.0, 0.0, 0.0], [10.0, 10.0, 10.0]])
    collection_id = first["collection"]["id"]
    await _draw(ctx, {"collection": collection_id}, name="far", vectors=[[100.0, 100.0, 100.0], [200.0, 200.0, 200.0]])

    query = "query L($filters: AnnotationFilter) { annotations(filters: $filters) { name } }"

    result = await schema.execute(
        query,
        context_value=ctx,
        variable_values={"filters": {"collection": collection_id, "intersects": {"min": [5.0, 5.0, 5.0], "max": [20.0, 20.0, 20.0]}}},
    )
    assert not result.errors, result.errors
    assert {a["name"] for a in result.data["annotations"]} == {"near"}

    result = await schema.execute(
        query,
        context_value=ctx,
        variable_values={"filters": {"collection": collection_id, "containsPoint": [150.0, 150.0, 150.0]}},
    )
    assert not result.errors, result.errors
    assert {a["name"] for a in result.data["annotations"]} == {"far"}

    result = await schema.execute(
        query,
        context_value=ctx,
        variable_values={"filters": {"intersects": {"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 1.0]}}},
    )
    assert result.errors, "a spatial predicate without a frame must be refused"
    assert "frame" in str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_nearest_annotations(db, authenticated_context: HttpContext):
    """Cube-distance ordering, limit, and exclusion of shapes with no box."""
    ctx = authenticated_context
    scene = await seed.create_scene(ctx)

    first = await _draw(ctx, {"scene": str(scene.id)}, name="a", vectors=[[0.0, 0.0, 0.0]])
    collection_id = first["collection"]["id"]
    await _draw(ctx, {"collection": collection_id}, name="b", vectors=[[50.0, 50.0, 50.0]])
    await _draw(ctx, {"collection": collection_id}, name="c", vectors=[[200.0, 200.0, 200.0]])
    await _draw(ctx, {"collection": collection_id}, name="boxless", vectors=[])

    query = "query N($collection: ID!, $point: [Float!]!, $limit: Int!) { nearestAnnotations(collection: $collection, point: $point, limit: $limit) { name } }"

    result = await schema.execute(query, context_value=ctx, variable_values={"collection": collection_id, "point": [1.0, 1.0, 1.0], "limit": 10})
    assert not result.errors, result.errors
    assert [a["name"] for a in result.data["nearestAnnotations"]] == ["a", "b", "c"], "ordered by cube distance; the boxless shape is nowhere, not near"

    result = await schema.execute(query, context_value=ctx, variable_values={"collection": collection_id, "point": [199.0, 199.0, 199.0], "limit": 2})
    assert not result.errors, result.errors
    assert [a["name"] for a in result.data["nearestAnnotations"]] == ["c", "b"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_bulk_create(db, authenticated_context: HttpContext):
    """Many shapes, one call: one minted bundle, per-shape boxes, uniform version, history intact."""
    ctx = authenticated_context
    scene = await seed.create_scene(ctx)

    mutation = """
    mutation Bulk($input: CreateAnnotationsInput!) {
      createAnnotations(input: $input) {
        id
        name
        createdWithTransforms
        intrinsicBbox { min max }
        collection { id }
      }
    }
    """
    specs = [
        {"kind": "POINT", "name": "one", "vectors": [[0.0, 0.0, 0.0]], "coordinates": [{"name": "t", "value": 0}]},
        {"kind": "POINT", "name": "two", "vectors": [[5.0, 5.0, 5.0]]},
        {"kind": "PATH", "name": "three", "vectors": [[1.0, 1.0, 1.0], [2.0, 2.0, 2.0]]},
    ]
    result = await schema.execute(
        mutation,
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "annotations": specs}},
    )
    assert not result.errors, result.errors
    created = result.data["createAnnotations"]
    assert [a["name"] for a in created] == ["one", "two", "three"]
    assert len({a["collection"]["id"] for a in created}) == 1
    assert all(a["intrinsicBbox"] is not None for a in created), "every shape gets its box"
    assert len({a["createdWithTransforms"] for a in created}) == 1, "one version read for the whole batch"

    counts = await sync_to_async(_counts)(scene)
    assert counts == {"collections": 1, "systems": 1, "layers": 1, "registrations": 1}, "the batch mints the scene bundle exactly once"
    assert await models.Annotation.objects.acount() == 3

    def history_rows():
        return models.Annotation.provenance.model.objects.count()

    assert await sync_to_async(history_rows)() == 3, "bulk-created rows still write their history"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_annotation_lists_are_org_scoped(db, authenticated_context: HttpContext, other_org_context: HttpContext):
    """The root lists never leak across organizations -- the hole the old dataRois field had."""
    ctx = authenticated_context
    scene = await seed.create_scene(ctx)

    made = await schema.execute(
        CREATE,
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "kind": "POINT", "vectors": [[0.0, 0.0, 0.0]]}},
    )
    assert not made.errors, made.errors

    query = "query { annotations { id } annotationCollections { id } }"
    ours = await schema.execute(query, context_value=ctx)
    assert not ours.errors, ours.errors
    assert len(ours.data["annotations"]) == 1
    assert len(ours.data["annotationCollections"]) == 1

    theirs = await schema.execute(query, context_value=other_org_context)
    assert not theirs.errors, theirs.errors
    assert theirs.data["annotations"] == []
    assert theirs.data["annotationCollections"] == []
