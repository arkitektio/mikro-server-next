"""Tests for the round ROI kinds and the point set.

CIRCLE, SPHERE and ELLIPSOID are encoded as the two opposite corners of their
bounding box -- exactly what RECTANGLE and CUBE already are -- so a bounding box
is the vectors themselves rather than something a reader has to reconstruct from
a centre and a radius. That is the whole point of the encoding: the annotation
write path (``compute_intrinsic_bbox``) is kind-blind, so a corner-encoded kind
gets a correct ``intrinsicBbox`` and correct marquee bounds for free, while a
centre+radius kind would get a box around the centre point and the radius vector.

MULTI_POINT is the other axis: not a new box shape, a new *arity*. Its vectors
are unconnected points, which POINT (exactly one) and PATH (connected) both
already say something different about.
"""

import pytest
from asgiref.sync import sync_to_async
from pytest import approx

from core import enums, models
from core.logic.roi import calculate_roi_bounds
from kante.context import HttpContext
from mikro_server.schema import schema
from tests import seed


DRAW = """
mutation Create($input: CreateAnnotationInput!) {
  createAnnotation(input: $input) {
    id
    kind
    vectors
    intrinsicBbox { min max }
  }
}
"""


# A legacy ROI vector is [c, t, z, y, x]. Centre (z=30, y=20, x=10), radius 5.
SPHERE_CORNERS = [
    [0, 0, 25, 15, 5],
    [0, 0, 35, 25, 15],
]


def test_sphere_bounds_are_the_corners_of_its_bounding_cube():
    """The radius is half the extent, so no radius arithmetic happens anywhere."""
    bounds = calculate_roi_bounds(SPHERE_CORNERS, enums.RoiKindChoices.SPHERE.value)

    assert (bounds.min_x, bounds.max_x) == (5, 15)
    assert (bounds.min_y, bounds.max_y) == (15, 25)
    assert (bounds.min_z, bounds.max_z) == (25, 35)
    assert bounds.width == bounds.height == bounds.depth == 10, "uniform by construction"


def test_the_corner_encoded_kinds_agree_on_one_box():
    """A sphere, an ellipsoid and a cube on the same corners are the same box.

    This is the property the encoding buys: adding a round kind adds no second
    way to read a pair of corners, so nothing downstream has to learn about it.
    """
    cube = calculate_roi_bounds(SPHERE_CORNERS, enums.RoiKindChoices.CUBE.value)

    for kind in (enums.RoiKindChoices.SPHERE, enums.RoiKindChoices.ELLIPSOID):
        assert calculate_roi_bounds(SPHERE_CORNERS, kind.value).to_dict() == cube.to_dict(), f"{kind.value} must read its corners exactly as a cube does"

    corners = [[0, 0, 0, 15, 5], [0, 0, 0, 25, 15]]
    rectangle = calculate_roi_bounds(corners, enums.RoiKindChoices.RECTANGLE.value)

    for kind in (enums.RoiKindChoices.CIRCLE, enums.RoiKindChoices.ELLIPSIS):
        assert calculate_roi_bounds(corners, kind.value).to_dict() == rectangle.to_dict(), f"{kind.value} must read its corners exactly as a rectangle does"


def test_the_ellipse_is_corner_encoded_like_the_rest_of_the_family():
    """ELLIPSIS used to be [centre, radii], which is the one reading that needed a kind.

    Under the old encoding these two vectors meant "centred at x=10, y=20, with
    radii 5 and 5" and boxed to x in [5, 15]. They are corners now, so they mean
    a 10x15 ellipse spanning x in [10, 20] -- and, more to the point, the
    kind-blind annotation bbox path agrees with this function instead of
    silently disagreeing with it.
    """
    vectors = [[0, 0, 0, 20, 10], [0, 0, 0, 35, 20]]

    bounds = calculate_roi_bounds(vectors, enums.RoiKindChoices.ELLIPSIS.value)

    assert (bounds.min_x, bounds.max_x) == (10, 20)
    assert (bounds.min_y, bounds.max_y) == (20, 35)
    assert bounds.width != bounds.height, "an ellipse is the per-axis half of the pair; a circle is the uniform one"


def test_an_ellipsoid_may_have_a_radius_per_axis():
    """The only thing that separates it from a sphere is that the extents differ."""
    bounds = calculate_roi_bounds([[0, 0, 0, 0, 0], [0, 0, 2, 6, 20]], enums.RoiKindChoices.ELLIPSOID.value)

    assert (bounds.depth, bounds.height, bounds.width) == (2, 6, 20)


def test_multi_point_bounds_hull_every_point():
    """Unconnected points still have a hull, and every one of them is in it."""
    points = [[0, 0, 0, 4, 1], [0, 0, 0, 2, 9], [0, 0, 0, 7, 5]]

    bounds = calculate_roi_bounds(points, enums.RoiKindChoices.MULTI_POINT.value)

    assert (bounds.min_x, bounds.max_x) == (1, 9)
    assert (bounds.min_y, bounds.max_y) == (2, 7)


def test_the_new_kinds_reach_the_graphql_enum():
    """Both enums carry them: the Django one is what is stored, the strawberry one what is asked for."""
    sdl = schema.as_str()

    for member in ("CIRCLE", "SPHERE", "ELLIPSOID", "MULTI_POINT"):
        assert member in sdl, f"{member} missing from the RoiKind enum"
        assert hasattr(enums.RoiKindChoices, member), f"{member} missing from RoiKindChoices"
        assert enums.RoiKind[member].value == enums.RoiKindChoices[member].value, "a stored value and a requested value must be the same string"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_drawn_sphere_gets_its_box_for_free(db, authenticated_context: HttpContext):
    """The kind-blind annotation write path already boxes a corner-encoded shape correctly.

    No branch in ``compute_intrinsic_bbox`` knows what a sphere is, and none needs
    to: the box is the half-open hull of the corners (a voxel at n covers
    [n - 0.5, n + 0.5)), identical to what the same corners give as a cube.
    """
    ctx = authenticated_context
    scene = await seed.create_scene(ctx, "Spheres")

    # The drawing space mirrors the world's z/y/x, so annotation vectors are 3D.
    corners = [[25.0, 15.0, 5.0], [35.0, 25.0, 15.0]]

    result = await schema.execute(
        DRAW,
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "kind": "SPHERE", "vectors": corners}},
    )
    assert not result.errors, result.errors
    sphere = result.data["createAnnotation"]

    assert sphere["kind"] == "SPHERE"
    assert sphere["intrinsicBbox"]["min"] == approx([24.5, 14.5, 4.5])
    assert sphere["intrinsicBbox"]["max"] == approx([35.5, 25.5, 15.5])

    cube = await schema.execute(
        DRAW,
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "kind": "CUBE", "vectors": corners}},
    )
    assert not cube.errors, cube.errors
    assert cube.data["createAnnotation"]["intrinsicBbox"] == sphere["intrinsicBbox"], "same corners, same box: the round kind adds no second reading"

    stored = await models.Annotation.objects.aget(id=sphere["id"])
    assert stored.kind == enums.RoiKindChoices.SPHERE.value
    assert stored.bbox_cube is not None, "the GiST search copy is written like it is for every other kind"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_drawn_point_set_is_hulled_not_connected(db, authenticated_context: HttpContext):
    """MULTI_POINT stores every click; the box spans them all."""
    ctx = authenticated_context
    scene = await seed.create_scene(ctx, "Counts")

    points = [[0.0, 4.0, 1.0], [0.0, 2.0, 9.0], [0.0, 7.0, 5.0]]

    result = await schema.execute(
        DRAW,
        context_value=ctx,
        variable_values={"input": {"scene": str(scene.id), "kind": "MULTI_POINT", "vectors": points}},
    )
    assert not result.errors, result.errors
    drawn = result.data["createAnnotation"]

    assert drawn["vectors"] == points, "every point survives; a point set is one annotation, not three"
    assert drawn["intrinsicBbox"]["min"] == approx([-0.5, 1.5, 0.5])
    assert drawn["intrinsicBbox"]["max"] == approx([0.5, 7.5, 9.5])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_the_new_kinds_are_filterable(db, authenticated_context: HttpContext):
    """`ROIFilter.kind` derives its enum from `RoiKindChoices`, so it picks the new kinds up for free."""
    ctx = authenticated_context
    dataset = await seed.create_folder(ctx, "DS")
    image = await seed.create_image(ctx, "Img", dataset)

    sphere = await models.ROI.objects.acreate(image=image, creator=ctx.request.user, vectors=SPHERE_CORNERS, kind=enums.RoiKindChoices.SPHERE.value)
    await models.ROI.objects.acreate(image=image, creator=ctx.request.user, vectors=SPHERE_CORNERS, kind=enums.RoiKindChoices.CUBE.value)

    result = await schema.execute(
        "query List($filters: ROIFilter) { rois(filters: $filters) { id } }",
        context_value=ctx,
        variable_values={"filters": {"kind": "SPHERE"}},
    )
    assert not result.errors, result.errors
    assert {r["id"] for r in result.data["rois"]} == {str(sphere.id)}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_the_legacy_roi_accepts_and_bounds_a_sphere(db, authenticated_context: HttpContext):
    """`createRoi` types its kind as the same enum, so the new kinds are creatable there too.

    ``calculate_bounds`` is called explicitly because nothing on the create path
    calls it -- a pre-existing gap that leaves every legacy ROI's min/max columns
    null, for every kind. What is asserted here is the half this change owns: a
    sphere resolves through the bounds logic to its corners.
    """
    ctx = authenticated_context
    dataset = await seed.create_folder(ctx, "DS")
    image = await seed.create_image(ctx, "Img", dataset)

    result = await schema.execute(
        "mutation Create($input: RoiInput!) { createRoi(input: $input) { id kind } }",
        context_value=ctx,
        variable_values={"input": {"image": str(image.id), "kind": "SPHERE", "vectors": SPHERE_CORNERS}},
    )
    assert not result.errors, result.errors
    assert result.data["createRoi"]["kind"] == "SPHERE"

    def bounds():
        roi = models.ROI.objects.get(id=result.data["createRoi"]["id"])
        assert roi.kind == enums.RoiKindChoices.SPHERE.value, "the stored string round-trips through the TextChoicesField"
        roi.calculate_bounds()
        return roi

    roi = await sync_to_async(bounds)()
    assert (roi.min_x, roi.max_x) == (5, 15)
    assert (roi.min_z, roi.max_z) == (25, 35)
