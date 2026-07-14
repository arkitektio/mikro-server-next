"""Conformance tests for the coordinate graph.

These exist because the bugs this architecture is built to prevent do not raise.
A transposed axis, a nominal pyramid factor, a dropped half-voxel, a two-corner
bounding box under a rotation -- none of them crash, and none of them produce a
stack trace. They just put things in the wrong place, plausibly, and stay there
for years. Every assertion below is aimed at one of those.

The pyramid fixture deliberately uses a **36-voxel z axis**. 36 does not halve
cleanly: it floors to 18, 9, 4, 2, 1, so the true downsample factors are
1, 2, 4, **9, 18, 36** while a nominal ``2 ** level`` claims 1, 2, 4, 8, 16, 32.
With a power-of-two axis the test passes either way and proves nothing -- which is
exactly why the old bug survived in z while xy looked fine.

The intrinsic space is the level-0 **pixel grid**: pyramid scales are
dimensionless ratios, ROI boxes are in pixels, and physical units only exist on
calibrations -- a PHYSICAL system plus one edge, tested in section 7.
"""

import pytest
from pytest import approx

from core import enums
from core.logic import coords, graph
from core.models import CoordinateSystem, DataRoi, Transformation
from kante.context import HttpContext
from mikro_server.schema import schema
from tests import seed


# A realistic acquisition: t and c are not downsampled, z is 36 (not a power of
# two), and xy is 1024 (which is).
PYRAMID_AXES = [
    seed.axis("t", enums.AxisType.TIME),
    seed.axis("c", enums.AxisType.CHANNEL),
    seed.axis("z", enums.AxisType.SPACE),
    seed.axis("y", enums.AxisType.SPACE),
    seed.axis("x", enums.AxisType.SPACE),
]

PYRAMID_SHAPES = [
    [10, 2, 36, 1024, 1024],
    [10, 2, 18, 512, 512],
    [10, 2, 9, 256, 256],
    [10, 2, 4, 128, 128],
    [10, 2, 2, 64, 64],
    [10, 2, 1, 32, 32],
]

_AXIS_SPECS = [coords.AxisSpec(name=a.name, type=a.type.value) for a in PYRAMID_AXES]


def _level_transform(level: int) -> tuple[list[float], list[float]]:
    return coords.pyramid_transform(PYRAMID_SHAPES[0], PYRAMID_SHAPES[level], _AXIS_SPECS)


# --- 1. the assertion that matters ----------------------------------------


def test_extent_preserved():
    """Every level must cover the same pixel extent. This is THE assertion.

    ``scale[i] * shape[i]`` is the size of the array along axis i, in level-0
    pixels. If a level's scale is right, that size is the same at every level --
    the pyramid is the same object, sampled more coarsely. A nominal 2**level
    factor breaks this on any axis that does not halve cleanly, and breaks it
    silently.
    """
    for level in range(len(PYRAMID_SHAPES)):
        scale, _ = _level_transform(level)
        for i in range(len(_AXIS_SPECS)):
            assert scale[i] * PYRAMID_SHAPES[level][i] == approx(PYRAMID_SHAPES[0][i]), f"level {level} axis '{_AXIS_SPECS[i].name}' does not cover the same extent as level 0"


def test_z_factor_is_not_a_power_of_two():
    """The z scales must follow the real shapes, not the nominal 2**level chain.

    Level 3's z factor is 36/4 = 9, not 8. A model that stores nominal factors
    says 8, and every level from 3 up is then compressed in z -- with nothing
    anywhere to say so.
    """
    z = _AXIS_SPECS.index(next(a for a in _AXIS_SPECS if a.name == "z"))
    expected = [1.0, 2.0, 4.0, 9.0, 18.0, 36.0]

    for level, want in enumerate(expected):
        scale, _ = _level_transform(level)
        assert scale[z] == approx(want), f"level {level} z scale"

    nominal = [float(2**level) for level in range(6)]
    assert expected[3:] != nominal[3:], "the fixture must actually exercise a non-power-of-two axis, or this proves nothing"


def test_half_voxel_offset_is_recorded():
    """A downsample shifts the voxel centres, and the translation must say so.

    Level 1's voxels are centred half a level-0 voxel further in. Nothing recorded
    this before, so LOD 1 drew half a pixel off from LOD 0 -- visible only as a
    faint shimmer when the renderer crossed a level boundary.
    """
    _, translation = _level_transform(0)
    assert translation == [0.0] * len(_AXIS_SPECS), "level 0 is not downsampled and must not be offset"

    for level in range(1, len(PYRAMID_SHAPES)):
        _, translation = _level_transform(level)
        for i, spec in enumerate(_AXIS_SPECS):
            factor = PYRAMID_SHAPES[0][i] / PYRAMID_SHAPES[level][i]
            assert translation[i] == approx((factor - 1) / 2), f"level {level} axis '{spec.name}' half-voxel offset"


def test_categorical_axes_are_never_downsampled():
    """A fractional coordinate between two channels is meaningless, so a channel axis must keep its extent."""
    bad_shape = [10, 1, 36, 1024, 1024]  # c halved from 2 to 1
    with pytest.raises(ValueError, match="must not be downsampled"):
        coords.pyramid_transform(PYRAMID_SHAPES[0], bad_shape, _AXIS_SPECS)


def test_continuous_axes_may_be_downsampled():
    """Time and microtime are continuous: a temporal pyramid or a re-binned FLIM axis is legitimate.

    Striding a long timelapse to every other frame is as meaningful as spatial
    downsampling, and the half-voxel arithmetic is identical. Only *categorical*
    axes (channel and friends) are protected.
    """
    strided_time = [5, 2, 18, 512, 512]  # t 10 -> 5, spatial halved too
    scale, translation = coords.pyramid_transform(PYRAMID_SHAPES[0], strided_time, _AXIS_SPECS)
    assert scale[0] == approx(2.0)
    assert translation[0] == approx(0.5)

    flim_axes = [
        coords.AxisSpec(name="tau", type=enums.AxisTypeChoices.MICROTIME.value),
        coords.AxisSpec(name="y", type=enums.AxisTypeChoices.SPACE.value),
        coords.AxisSpec(name="x", type=enums.AxisTypeChoices.SPACE.value),
    ]
    scale, _ = coords.pyramid_transform([256, 64, 64], [64, 64, 64], flim_axes)
    assert scale[0] == approx(4.0), "re-binning a FLIM arrival-time axis must be allowed"


# --- 2. axis order and the permutation ------------------------------------


def test_axis_type_order():
    """RFC-5 MUST: time, then channel and custom types, then space."""
    assert coords.is_sorted_by_type(_AXIS_SPECS)

    scrambled = [_AXIS_SPECS[2], _AXIS_SPECS[0], _AXIS_SPECS[1]]  # z, t, c
    assert not coords.is_sorted_by_type(scrambled)
    with pytest.raises(coords.AxisOrderError):
        coords.assert_axis_type_order(scrambled)


def test_array_to_vertex_order():
    """The one named permutation: array order is (z, y, x), vertex order is (x, y, z).

    A silently transposed coordinate is the failure mode of this whole
    architecture. It does not crash; it puts the cell in the wrong place.
    """
    # t=1, c=0, z=2, y=3, x=4
    coordinate = [1.0, 0.0, 2.0, 3.0, 4.0]
    assert coords.array_to_vertex_order(coordinate, _AXIS_SPECS) == [4.0, 3.0, 2.0]

    back = coords.vertex_to_array_order([4.0, 3.0, 2.0], _AXIS_SPECS)
    assert back == {"x": 4.0, "y": 3.0, "z": 2.0}


def test_render_axes_take_the_last_spatial_axis_as_x():
    """x is the fastest-varying spatial axis, not the first.

    The rule this replaces took ``spatial[0]``, which under the required (z, y, x)
    ordering picks *z* as x -- and under the (c, y, x) shape most fixtures use,
    swaps x and y. Every image layer in the old test suite was transposed.
    """
    axes = coords.resolve_render_axes(_AXIS_SPECS)
    assert (axes.x, axes.y, axes.z) == ("x", "y", "z")
    assert (axes.t, axes.intensity) == ("t", "c")

    flat = [_AXIS_SPECS[1], _AXIS_SPECS[3], _AXIS_SPECS[4]]  # c, y, x
    flat_axes = coords.resolve_render_axes(flat)
    assert (flat_axes.x, flat_axes.y, flat_axes.z) == ("x", "y", None)


# --- 3. bounding boxes ------------------------------------------------------


def test_half_voxel_convention():
    """The voxel centre is the origin: voxel n occupies [n - 0.5, n + 0.5)."""
    low, high = coords.vectors_bbox([[340.0, 10.0, 10.0]])
    assert low == [339.5, 9.5, 9.5]
    assert high == [340.5, 10.5, 10.5]

    # A single-voxel cube at the origin has its vertices at +-0.5.
    low, high = coords.vectors_bbox([[0.0, 0.0, 0.0]])
    assert low == [-0.5, -0.5, -0.5]
    assert high == [0.5, 0.5, 0.5]


def test_bbox_uses_every_corner():
    """An affine-transformed AABB is not an AABB.

    Under a rotation, pushing only the min and max corners through the matrix
    gives a box that is not merely different but strictly *too small* -- so
    geometry that really is inside it tests as outside, and gets culled.
    """
    # 45 degrees about z. The unit square's diagonal is what min/max misses.
    c = 0.7071067811865476
    rotation = [[c, -c, 0.0, 0.0], [c, c, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]]
    edges = [(enums.TransformKindChoices.AFFINE.value, {"affine": rotation})]

    mins, maxs = [0.0, 0.0, 0.0], [1.0, 1.0, 0.0]
    full = coords.transformed_bbox(mins, maxs, edges)

    # What the two-corner shortcut would have produced.
    matrix = coords.compose(edges, 3)
    shortcut_corners = [coords.apply(matrix, mins), coords.apply(matrix, maxs)]
    shortcut_low, shortcut_high = coords.aabb(shortcut_corners)

    # The rotated square spans [-c, c] in x: the corners (0,1) and (1,0) swing out
    # to either side, and neither of them is a corner of the original box.
    assert full["min"][0] == approx(-c)
    assert full["max"][0] == approx(c)
    assert full["max"][1] == approx(2 * c)

    # The two-corner shortcut only ever sees (0,0) and (1,1), which the rotation
    # maps to (0,0) and (0, 2c) -- so it reports a box of ZERO width in x. The
    # true box is 2c wide. Nothing about that is ill-formed; it is simply wrong,
    # and it culls every object in the half of the box it dropped.
    assert shortcut_low[0] == approx(0.0) and shortcut_high[0] == approx(0.0)
    assert full["min"][0] < shortcut_low[0]
    assert full["max"][0] > shortcut_high[0]


def test_eight_corners_in_3d():
    """A 3D box has eight corners, and all eight are transformed."""
    assert len(coords.bbox_corners([0.0, 0.0, 0.0], [1.0, 1.0, 1.0])) == 8


# --- 4. the lens edge -------------------------------------------------------


def test_lens_to_parent_is_a_translation_of_the_slice_starts():
    """A crop shifts voxel coordinates, and the edge must record the shift.

    Without it, an ROI drawn on a cropped lens has no defined path back to its
    dataset. That was a live correctness hole, not a hypothetical one.
    """
    slices = [coords.AxisSpec(name="z", type="SPACE")]  # placeholder, replaced below

    class _Slice:
        def __init__(self, dim, start=None, stop=None, step=None):
            self.dim, self.start, self.stop, self.step = dim, start, stop, step

    slices = [_Slice("z", start=4, stop=32)]
    kind, params = coords.lens_to_parent(["t", "c", "z", "y", "x"], slices)

    assert kind == enums.TransformKindChoices.TRANSLATION.value
    assert params["translation"] == [0.0, 0.0, 4.0, 0.0, 0.0]


def test_stepped_lens_rescales_as_well_as_offsets():
    """A stepped lens is a SEQUENCE, not a bare translation.

    A translation-only edge would mis-place every subsampled lens by a factor of
    the step -- silently, since nothing about it is ill-formed.
    """

    class _Slice:
        def __init__(self, dim, start=None, stop=None, step=None):
            self.dim, self.start, self.stop, self.step = dim, start, stop, step

    kind, params = coords.lens_to_parent(["z", "y", "x"], [_Slice("x", start=10, step=2)])

    assert kind == enums.TransformKindChoices.SEQUENCE.value
    assert params["scale"] == [1.0, 1.0, 2.0]
    assert params["translation"] == [0.0, 0.0, 10.0]


def test_lens_roundtrip():
    """A point in lens space, pushed to the parent and back, is where it started."""

    class _Slice:
        def __init__(self, dim, start=None, stop=None, step=None):
            self.dim, self.start, self.stop, self.step = dim, start, stop, step

    dims = ["z", "y", "x"]
    kind, params = coords.lens_to_parent(dims, [_Slice("z", start=4), _Slice("x", start=7)])

    forward = coords.compose([(kind, params)], 3)
    point = [3.0, 5.0, 2.0]
    in_parent = coords.apply(forward, point)

    assert in_parent == [7.0, 5.0, 9.0]

    # Invert by hand (a translation's inverse is its negation) and come back.
    inverse = coords.to_matrix(
        enums.TransformKindChoices.TRANSLATION.value,
        {"translation": [-value for value in params["translation"]]},
        3,
    )
    assert coords.apply(inverse, in_parent) == approx(point)


def test_lens_shape_follows_python_slice_semantics():
    """The lens' shape is derived, so it cannot drift from the slices that define it."""

    class _Slice:
        def __init__(self, dim, start=None, stop=None, step=None):
            self.dim, self.start, self.stop, self.step = dim, start, stop, step

    shape = coords.lens_shape([36, 1024, 1024], ["z", "y", "x"], [_Slice("z", start=4, stop=32), _Slice("x", step=2)])
    assert shape == [28, 1024, 512]


# --- 5. the graph, end to end ----------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_stored_edges_are_forward_and_absolute(authenticated_context: HttpContext):
    """The stored graph must say what the arithmetic says.

    Reads the rows back rather than the functions: a derivation that is right but
    stored wrong is still wrong.
    """
    from asgiref.sync import sync_to_async

    dataset = await seed.create_adataset(authenticated_context, "Pyramid", axes=PYRAMID_AXES, shapes=PYRAMID_SHAPES)

    def check():
        arrays = list(dataset.data_arrays.order_by("level"))
        assert len(arrays) == 6

        intrinsic = dataset.intrinsic_coordinate_system
        z = 2

        for level, array in enumerate(arrays):
            edge = array.to_parent
            assert edge is not None, f"level {level} has no edge into intrinsic space"

            # Every edge maps input -> output, and every level lands in the SAME
            # intrinsic system: a star, not a chain.
            assert edge.input_id == array.coordinate_system.pk
            assert edge.output_id == intrinsic.pk

            if level == 0:
                assert edge.kind == enums.TransformKindChoices.SCALE.value
                scale = edge.params["scale"]
                assert scale == [1.0] * len(PYRAMID_AXES), "level 0 maps onto the pixel grid identically"
            else:
                assert edge.kind == enums.TransformKindChoices.SEQUENCE.value
                children = list(edge.children.order_by("order"))
                assert [child.kind for child in children] == [
                    enums.TransformKindChoices.SCALE.value,
                    enums.TransformKindChoices.TRANSLATION.value,
                ]
                # RFC-5 permits a wrapper's children to omit their endpoints.
                assert all(child.input_id is None and child.output_id is None for child in children)
                scale = children[0].params["scale"]

            # The absolute scale, read back from the row: dimensionless, so every
            # level covers the level-0 pixel extent exactly.
            assert scale[z] * array.shape[z] == approx(36), f"level {level} z extent"

        # Level 3's z factor is 9, not the nominal 8.
        level_3 = arrays[3].to_parent
        assert level_3.children.get(order=0).params["scale"][z] == approx(9.0)

    await sync_to_async(check)()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_dataset_graph_is_connected(authenticated_context: HttpContext):
    """RFC-5 MUST: a dataset's systems are all joined by a path of edges.

    Scoped to the dataset's own subgraph -- the level-to-intrinsic star plus its
    lenses. A *scene's* world system is legitimately disconnected until someone
    authors a registration edge, so asserting global connectivity would either
    fail falsely or, if the seed happened to add one, pass vacuously.
    """
    from asgiref.sync import sync_to_async

    dataset = await seed.create_adataset(authenticated_context, "Pyramid", axes=PYRAMID_AXES, shapes=PYRAMID_SHAPES)
    await seed.create_lens(authenticated_context, dataset, slices=[{"dim": "z", "start": 4, "stop": 32}])

    def check():
        systems = set(CoordinateSystem.objects.filter(intrinsic_of=dataset).values_list("pk", flat=True))
        systems |= set(CoordinateSystem.objects.filter(data_array__dataset=dataset).values_list("pk", flat=True))
        systems |= set(CoordinateSystem.objects.filter(lens__dataset=dataset).values_list("pk", flat=True))

        intrinsic = dataset.intrinsic_coordinate_system.pk

        # Every non-intrinsic system must reach the intrinsic one.
        for pk in systems - {intrinsic}:
            chain = graph.path_to_intrinsic(CoordinateSystem.objects.get(pk=pk))
            assert chain, f"coordinate system {pk} cannot reach the dataset's intrinsic space"

    await sync_to_async(check)()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_roi_bbox_accounts_for_the_lens_crop(authenticated_context: HttpContext):
    """An ROI drawn on a cropped lens lands in the right place in intrinsic pixel space.

    This is the correctness hole the lens edge closes, tested end to end: the ROI's
    coordinates are lens-relative, and its intrinsic box must carry the crop offset.
    The box is in level-0 *pixels* -- physical units live on calibrations, so a
    recalibration can never move it.
    """
    from asgiref.sync import sync_to_async

    axes = [
        seed.axis("z", enums.AxisType.SPACE),
        seed.axis("y", enums.AxisType.SPACE),
        seed.axis("x", enums.AxisType.SPACE),
    ]
    dataset = await seed.create_adataset(authenticated_context, "Crop", axes=axes, shapes=[[36, 128, 128]])
    lens = await seed.create_lens(authenticated_context, dataset, slices=[{"dim": "z", "start": 4, "stop": 32}])

    def check():
        system = lens.coordinate_system
        # A single voxel at z=0 in LENS coordinates -- which is z=4 in the dataset.
        bbox = graph.compute_intrinsic_bbox(system, [[0.0, 10.0, 10.0]])

        # The voxel spans [-0.5, 0.5) in lens space, so [3.5, 4.5) in level-0 pixels.
        assert bbox["min"][0] == approx(3.5)
        assert bbox["max"][0] == approx(4.5)
        # x and y are uncropped: voxel 10 spans [9.5, 10.5).
        assert bbox["min"][2] == approx(9.5)
        assert bbox["max"][2] == approx(10.5)

    await sync_to_async(check)()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_roi_survives_its_scene(authenticated_context: HttpContext):
    """An ROI belongs to a coordinate system, not to a scene. Delete the scene and it stands.

    Enforced by the FK graph rather than assumed: the ROI's system hangs off the
    dataset, so a scene deletion cannot reach it.
    """
    from asgiref.sync import sync_to_async

    dataset = await seed.create_adataset(authenticated_context, "Kept")
    scene = await seed.create_scene(authenticated_context, "Doomed")

    def draw():
        return DataRoi.objects.create(
            coordinate_system=dataset.intrinsic_coordinate_system,
            name="ROI",
            kind=enums.RoiKindChoices.POINT.value,
            vectors=[[0.0, 1.0, 1.0]],
            creator=authenticated_context.request.user,
        )

    roi = await sync_to_async(draw)()
    await scene.adelete()

    assert await DataRoi.objects.filter(pk=roi.pk).aexists(), "deleting a scene must not delete an ROI"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_every_stored_edge_is_forward(authenticated_context: HttpContext):
    """No row may encode an inverse map. Direction is always input -> output."""
    from asgiref.sync import sync_to_async

    await seed.create_adataset(authenticated_context, "Pyramid", axes=PYRAMID_AXES, shapes=PYRAMID_SHAPES)

    def check():
        for edge in Transformation.objects.filter(parent__isnull=True):
            assert edge.input_id is not None and edge.output_id is not None, "a top-level edge must join two systems"
            # A level's array system is its input, never its output: the pyramid
            # maps up into intrinsic space, not down out of it.
            assert edge.input.kind == enums.CoordinateSystemKindChoices.ARRAY.value
            assert edge.output.kind == enums.CoordinateSystemKindChoices.INTRINSIC.value

    await sync_to_async(check)()


# --- 6. registration: the architecture's central claim -----------------------
#
# Registration used to be a 4x4 matrix on the Layer, so two layers over one
# dataset carried two copies of one fact and were free to disagree. It is now an
# edge between two coordinate systems, and a scene declares which edges it
# composes with. These tests drive that through the real API.


REGISTER = """
mutation Register($input: CreateTransformationInput!) {
  createTransformation(input: $input) {
    __typename
    id
    kind
    input { id kind }
    output { id kind }
    ... on AffineTransformation { affine }
  }
}
"""

SCENE_GRAPH = """
query SceneGraph($id: ID!) {
  scene(id: $id) {
    worldCoordinateSystem { id kind }
    coordinateSystems { id kind }
    coordinateTransformations { __typename id ... on AffineTransformation { affine } }
    rois { id name }
  }
}
"""

# A 90-degree rotation about z with a 100 um offset -- a registration that is not
# the identity, so a dropped edge shows up as a wrong answer rather than a no-op.
_AFFINE = [
    [0.0, -1.0, 0.0, 100.0],
    [1.0, 0.0, 0.0, 50.0],
    [0.0, 0.0, 1.0, 0.0],
]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_registration_is_a_scene_level_edge(authenticated_context: HttpContext):
    """Register a dataset into a scene, and reach its ROI through the edge.

    This is the whole claim in one test: an ROI drawn against a *dataset* shows up
    in a *scene* because a transformation edge joins their coordinate systems --
    not because anything contains anything.
    """
    from asgiref.sync import sync_to_async

    dataset = await seed.create_adataset(authenticated_context, "Specimen")
    scene = await seed.create_scene(authenticated_context, "Composition")

    def systems():
        return dataset.intrinsic_coordinate_system, scene.world_coordinate_system

    intrinsic, world = await sync_to_async(systems)()

    # 1. The registration edge, added to the scene in the same call.
    result = await schema.execute(
        REGISTER,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "input": str(intrinsic.pk),
                "output": str(world.pk),
                "kind": "AFFINE",
                "affine": _AFFINE,
                "scene": str(scene.pk),
            }
        },
    )
    assert not result.errors, result.errors
    edge = result.data["createTransformation"]

    # The JSON params unpack into typed fields on the concrete subtype. Nothing but
    # the interface's is_type_of makes this an AffineTransformation rather than the
    # bare interface.
    assert edge["__typename"] == "AffineTransformation"
    assert edge["affine"] == _AFFINE
    assert edge["input"]["kind"] == "INTRINSIC"
    assert edge["output"]["kind"] == "WORLD"

    # 2. An ROI drawn against the DATASET, which knows nothing about the scene.
    def draw():
        return DataRoi.objects.create(
            coordinate_system=intrinsic,
            name="Nucleus",
            kind=enums.RoiKindChoices.POINT.value,
            vectors=[[0.0, 12.0, 30.0]],
            creator=authenticated_context.request.user,
        )

    await sync_to_async(draw)()

    # 3. The scene reaches both, through the edge.
    result = await schema.execute(SCENE_GRAPH, context_value=authenticated_context, variable_values={"id": str(scene.pk)})
    assert not result.errors, result.errors
    data = result.data["scene"]

    reachable = {system["id"] for system in data["coordinateSystems"]}
    assert str(intrinsic.pk) in reachable, "the registered dataset's system must be reachable from the scene"
    assert str(world.pk) in reachable

    assert [r["name"] for r in data["rois"]] == ["Nucleus"], "the ROI must reach the scene through the transformation edge"
    assert data["coordinateTransformations"][0]["affine"] == _AFFINE


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_removing_an_edge_from_a_scene_does_not_delete_it(authenticated_context: HttpContext):
    """Scene membership is a separate statement from the edge.

    An edge is a fact about two coordinate systems and exists independently of any
    scene. Dropping it from a composition un-registers the dataset from *that*
    scene; it does not unmake the fact, and it does not touch the ROI.
    """
    from asgiref.sync import sync_to_async

    from core.models import Transformation as TransformationModel

    dataset = await seed.create_adataset(authenticated_context, "Specimen")
    scene = await seed.create_scene(authenticated_context, "Composition")

    def systems():
        return dataset.intrinsic_coordinate_system, scene.world_coordinate_system

    intrinsic, world = await sync_to_async(systems)()

    result = await schema.execute(
        REGISTER,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "input": str(intrinsic.pk),
                "output": str(world.pk),
                "kind": "AFFINE",
                "affine": _AFFINE,
                "scene": str(scene.pk),
            }
        },
    )
    assert not result.errors, result.errors
    edge_id = result.data["createTransformation"]["id"]

    def draw():
        return DataRoi.objects.create(
            coordinate_system=intrinsic,
            name="Nucleus",
            kind=enums.RoiKindChoices.POINT.value,
            vectors=[[0.0, 12.0, 30.0]],
            creator=authenticated_context.request.user,
        )

    roi = await sync_to_async(draw)()

    unregister = """
    mutation Unregister($input: SceneTransformationInput!) {
      removeTransformationFromScene(input: $input) { id }
    }
    """
    result = await schema.execute(
        unregister,
        context_value=authenticated_context,
        variable_values={"input": {"scene": str(scene.pk), "transformation": edge_id}},
    )
    assert not result.errors, result.errors

    # The dataset is no longer registered into this scene, so neither it nor its
    # ROI is reachable from it any more.
    result = await schema.execute(SCENE_GRAPH, context_value=authenticated_context, variable_values={"id": str(scene.pk)})
    assert not result.errors, result.errors
    data = result.data["scene"]

    assert str(intrinsic.pk) not in {system["id"] for system in data["coordinateSystems"]}
    assert data["rois"] == []
    assert data["coordinateTransformations"] == []

    # But the edge and the ROI both still exist. Un-registering is not deleting.
    assert await TransformationModel.objects.filter(pk=edge_id).aexists()
    assert await DataRoi.objects.filter(pk=roi.pk).aexists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_wrapper_kinds_cannot_be_authored_directly(authenticated_context: HttpContext):
    """A SEQUENCE is built by the ingest from its children, never authored empty.

    Without the reject-list a caller could create a wrapper with no children, which
    composes to the identity and silently un-places whatever it was meant to place.
    """
    from asgiref.sync import sync_to_async

    dataset = await seed.create_adataset(authenticated_context, "Specimen")
    scene = await seed.create_scene(authenticated_context, "Composition")

    def systems():
        return dataset.intrinsic_coordinate_system, scene.world_coordinate_system

    intrinsic, world = await sync_to_async(systems)()

    result = await schema.execute(
        REGISTER,
        context_value=authenticated_context,
        variable_values={"input": {"input": str(intrinsic.pk), "output": str(world.pk), "kind": "SEQUENCE"}},
    )
    assert result.errors, "an empty SEQUENCE wrapper must be rejected"

    # And a SCALE without its scale is rejected too: the params are per-kind.
    result = await schema.execute(
        REGISTER,
        context_value=authenticated_context,
        variable_values={"input": {"input": str(intrinsic.pk), "output": str(world.pk), "kind": "SCALE"}},
    )
    assert result.errors, "a SCALE transformation with no `scale` must be rejected"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mesh_collection_round_trip(authenticated_context: HttpContext):
    """A mesh collection resolves to Parquet *stores*, never to rows of meshes.

    The Parquet goes through the datalayer like every other Parquet object in the
    system -- presigned upload, store id back -- so the client can ask for an access
    grant and query it with DuckDB. A bare URL would sit outside the datalayer:
    nothing would sign it, nothing would scope it to an organization, and nothing
    would clean it up.
    """
    from asgiref.sync import sync_to_async

    from core.models import ParquetStore

    dataset = await seed.create_adataset(authenticated_context, "Labels")

    def setup():
        system = dataset.intrinsic_coordinate_system
        catalog = ParquetStore.objects.create(
            path="s3://parquet/catalog",
            bucket="parquet",
            key="catalog",
            organization=authenticated_context.request.organization,
        )
        shard = ParquetStore.objects.create(
            path="s3://parquet/geometry-0",
            bucket="parquet",
            key="geometry-0",
            organization=authenticated_context.request.organization,
        )
        return system, catalog, shard

    system, catalog, shard = await sync_to_async(setup)()

    create = """
    mutation Create($input: CreateMeshCollectionInput!) {
      createMeshCollection(input: $input) {
        id
        version
        specVersion
        grid
        encoding
        catalog { id key }
        geometry { id key }
        coordinateSystem { id kind }
      }
    }
    """
    result = await schema.execute(
        create,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "coordinateSystem": str(system.pk),
                "version": "v20260713-a3f9",
                "specVersion": "1.0",
                "catalog": str(catalog.pk),
                "geometry": [str(shard.pk)],
                # cellSize is in VOXELS, so the octree aligns to the label grid.
                "grid": {"cellSize": [64, 64, 64], "levels": 5, "sortKey": "MORTON"},
                "encoding": {"positions": "UINT16_QUANTIZED_PER_CELL", "codec": "MESHOPT"},
            }
        },
    )
    assert not result.errors, result.errors

    collection = result.data["createMeshCollection"]
    assert collection["version"] == "v20260713-a3f9"
    assert collection["grid"]["cellSize"] == [64, 64, 64]
    assert collection["encoding"]["codec"] == "MESHOPT"
    assert collection["coordinateSystem"]["id"] == str(system.pk)

    # The Parquet is addressed by store, so it carries an access grant.
    assert collection["catalog"]["id"] == str(catalog.pk)
    assert [g["key"] for g in collection["geometry"]] == ["geometry-0"]

    # The upload marked the stores populated, exactly as from_parquet_like does.
    assert await ParquetStore.objects.filter(pk=catalog.pk, populated=True).aexists()
    assert await ParquetStore.objects.filter(pk=shard.pk, populated=True).aexists()

    # The collection deliberately exposes no `meshes` field: a paginated one would
    # end up walking millions of Parquet rows through GraphQL to feed a render loop.
    sdl = schema.as_str()
    mesh_def = sdl[sdl.find("type MeshCollection ") : sdl.find("\n}", sdl.find("type MeshCollection "))]
    assert "\n  meshes" not in mesh_def
    # And the catalog is a store, not a URL.
    assert "catalogUrl" not in sdl


# --- 7. calibration: physical space is one node plus one edge ----------------
#
# The intrinsic space is the pixel grid, so a dataset carries no units at all
# until someone states a calibration: a PHYSICAL system whose axes carry the
# units, and a single edge mapping intrinsic pixels into it. These tests drive
# that through the real API and pin the property the design exists for --
# refining a calibration moves nothing that was drawn in pixels.


CALIBRATE = """
mutation Calibrate($input: CreateCalibrationInput!) {
  createCalibration(input: $input) {
    id
    name
    kind
    axes { name type unit }
  }
}
"""

DATASET_SPACES = """
query Spaces($id: ID!) {
  adataset(id: $id) {
    intrinsicSystem { id kind axes { name unit } }
    calibrations { id name kind axes { name unit } }
  }
}
"""

_CAL_AXES = [
    {"name": "c", "type": "CHANNEL", "unit": "a.u."},
    {"name": "y", "type": "SPACE", "unit": "micrometer"},
    {"name": "x", "type": "SPACE", "unit": "micrometer"},
]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_calibration_round_trip(authenticated_context: HttpContext):
    """A calibration is a PHYSICAL system plus one SCALE edge from intrinsic pixels.

    The units live on the physical axes; the intrinsic axes stay unitless. The
    magnitude lives on the edge. Reading back 'the pixel size' means joining the
    two -- deliberately, because that is what keeps pixel space stable.
    """
    from asgiref.sync import sync_to_async

    dataset = await seed.create_adataset(authenticated_context, "Calibrated")

    result = await schema.execute(
        CALIBRATE,
        context_value=authenticated_context,
        variable_values={"input": {"dataset": str(dataset.pk), "axes": _CAL_AXES, "scale": [1.0, 0.325, 0.325]}},
    )
    assert not result.errors, result.errors
    physical = result.data["createCalibration"]
    assert physical["kind"] == "PHYSICAL"
    assert [a["unit"] for a in physical["axes"]] == ["a.u.", "micrometer", "micrometer"]

    result = await schema.execute(DATASET_SPACES, context_value=authenticated_context, variable_values={"id": str(dataset.pk)})
    assert not result.errors, result.errors
    spaces = result.data["adataset"]

    # The intrinsic axes are the pixel grid: no unit, anywhere, ever.
    assert all(axis["unit"] is None for axis in spaces["intrinsicSystem"]["axes"])
    assert [c["id"] for c in spaces["calibrations"]] == [physical["id"]]

    def check_edge():
        intrinsic = dataset.intrinsic_coordinate_system
        edge = Transformation.objects.get(input=intrinsic, output_id=physical["id"])
        assert edge.kind == enums.TransformKindChoices.SCALE.value
        assert edge.params["scale"] == [1.0, 0.325, 0.325]

    await sync_to_async(check_edge)()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_recalibration_moves_nothing_drawn_in_pixels(authenticated_context: HttpContext):
    """THE property this design buys: refining a calibration touches one edge and nothing else.

    Under the old model the physical spacing was baked into every pyramid edge and
    every ROI bounding box, so a corrected pixel size silently invalidated all of
    them. Now it is one UPDATE on one row, plus a version bump that tells clients
    the physical interpretation moved.
    """
    from asgiref.sync import sync_to_async

    dataset = await seed.create_adataset(authenticated_context, "Recal", shapes=[[3, 64, 64], [3, 32, 32]])
    physical = await seed.create_calibration(
        authenticated_context,
        dataset,
        axes=[
            seed.calibrated_axis("c", enums.AxisType.CHANNEL, unit="a.u."),
            seed.calibrated_axis("y", enums.AxisType.SPACE, unit="micrometer"),
            seed.calibrated_axis("x", enums.AxisType.SPACE, unit="micrometer"),
        ],
        scale=[1.0, 0.325, 0.325],
    )

    def snapshot():
        intrinsic = dataset.intrinsic_coordinate_system
        roi = DataRoi.objects.create(
            coordinate_system=intrinsic,
            name="Nucleus",
            kind=enums.RoiKindChoices.POINT.value,
            vectors=[[0.0, 12.0, 30.0]],
            intrinsic_bbox=graph.compute_intrinsic_bbox(intrinsic, [[0.0, 12.0, 30.0]]),
            creator=authenticated_context.request.user,
        )
        edge = Transformation.objects.get(input=intrinsic, output=physical)
        level_edges = list(Transformation.objects.filter(input__data_array__dataset=dataset).values_list("pk", "params"))
        return roi, edge, level_edges

    roi, edge, level_edges_before = await sync_to_async(snapshot)()
    bbox_before = dict(roi.intrinsic_bbox)

    # The metadata was wrong: the objective was 20x, not 40x. Refine the edge.
    update = """
    mutation Refine($input: UpdateTransformationInput!) {
      updateTransformation(input: $input) { id version ... on ScaleTransformation { scale } }
    }
    """
    result = await schema.execute(
        update,
        context_value=authenticated_context,
        variable_values={"input": {"id": str(edge.pk), "scale": [1.0, 0.65, 0.65]}},
    )
    assert not result.errors, result.errors
    assert result.data["updateTransformation"]["version"] == 2
    assert result.data["updateTransformation"]["scale"] == [1.0, 0.65, 0.65]

    def after():
        refreshed = DataRoi.objects.get(pk=roi.pk)
        level_edges = list(Transformation.objects.filter(input__data_array__dataset=dataset).values_list("pk", "params"))
        return refreshed.intrinsic_bbox, level_edges

    bbox_after, level_edges_after = await sync_to_async(after)()

    assert bbox_after == bbox_before, "an ROI is drawn in pixels; recalibration must not move it"
    assert level_edges_after == level_edges_before, "the pyramid is pixel-to-pixel; recalibration must not touch it"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_dataset_can_carry_many_calibrations(authenticated_context: HttpContext):
    """Stage space and specimen space coexist: each is just another node off the same pixel grid."""
    from asgiref.sync import sync_to_async

    dataset = await seed.create_adataset(authenticated_context, "Multi")

    for name, scale in (("stage", [1.0, 0.325, 0.325]), ("specimen", [1.0, 0.65, 0.65])):
        result = await schema.execute(
            CALIBRATE,
            context_value=authenticated_context,
            variable_values={"input": {"dataset": str(dataset.pk), "name": name, "axes": _CAL_AXES, "scale": scale}},
        )
        assert not result.errors, result.errors

    def names():
        return sorted(system.name for system in dataset.calibrations.all())

    assert await sync_to_async(names)() == ["Multi/specimen", "Multi/stage"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_uncalibrated_data_is_first_class(authenticated_context: HttpContext):
    """A FLIM cube or a simulation has no physical interpretation, and no fake units appear anywhere."""
    result_dataset = await seed.create_adataset(authenticated_context, "Simulation")

    result = await schema.execute(DATASET_SPACES, context_value=authenticated_context, variable_values={"id": str(result_dataset.pk)})
    assert not result.errors, result.errors
    spaces = result.data["adataset"]

    assert spaces["calibrations"] == []
    assert all(axis["unit"] is None for axis in spaces["intrinsicSystem"]["axes"])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_calibration_with_a_stage_offset_is_a_sequence(authenticated_context: HttpContext):
    """A pixel size plus a stage position composes into a SEQUENCE edge, like a downsampled pyramid level."""
    from asgiref.sync import sync_to_async

    dataset = await seed.create_adataset(authenticated_context, "Staged")
    physical = await seed.create_calibration(
        authenticated_context,
        dataset,
        axes=[
            seed.calibrated_axis("c", enums.AxisType.CHANNEL, unit="a.u."),
            seed.calibrated_axis("y", enums.AxisType.SPACE, unit="micrometer"),
            seed.calibrated_axis("x", enums.AxisType.SPACE, unit="micrometer"),
        ],
        scale=[1.0, 0.325, 0.325],
        translation=[0.0, 1500.0, -2300.0],
        name="stage",
    )

    def check():
        edge = Transformation.objects.get(input=dataset.intrinsic_coordinate_system, output=physical)
        assert edge.kind == enums.TransformKindChoices.SEQUENCE.value
        children = list(edge.children.order_by("order"))
        assert children[0].params["scale"] == [1.0, 0.325, 0.325]
        assert children[1].params["translation"] == [0.0, 1500.0, -2300.0]

    await sync_to_async(check)()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_calibration_must_match_the_pixel_axes(authenticated_context: HttpContext):
    """A calibration reinterprets axes; it does not retype or recount them."""
    dataset = await seed.create_adataset(authenticated_context, "Strict")

    # Wrong count: two axes for a three-axis dataset.
    result = await schema.execute(
        CALIBRATE,
        context_value=authenticated_context,
        variable_values={"input": {"dataset": str(dataset.pk), "axes": _CAL_AXES[1:], "scale": [0.325, 0.325]}},
    )
    assert result.errors, "a calibration with the wrong axis count must be rejected"

    # Wrong type at a position: the channel axis calibrated as SPACE.
    retyped = [{"name": "c", "type": "SPACE", "unit": "micrometer"}] + _CAL_AXES[1:]
    result = await schema.execute(
        CALIBRATE,
        context_value=authenticated_context,
        variable_values={"input": {"dataset": str(dataset.pk), "axes": retyped, "scale": [1.0, 0.325, 0.325]}},
    )
    assert result.errors, "a calibration that retypes an axis must be rejected"

    # No transformation at all.
    result = await schema.execute(
        CALIBRATE,
        context_value=authenticated_context,
        variable_values={"input": {"dataset": str(dataset.pk), "axes": _CAL_AXES}},
    )
    assert result.errors, "a calibration needs a scale, a translation or an affine"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_only_calibrations_can_be_deleted_directly(authenticated_context: HttpContext):
    """deleteCalibration refuses anything that is not PHYSICAL: every other system cascades with its owner."""
    from asgiref.sync import sync_to_async

    dataset = await seed.create_adataset(authenticated_context, "Guarded")
    physical = await seed.create_calibration(
        authenticated_context,
        dataset,
        axes=[
            seed.calibrated_axis("c", enums.AxisType.CHANNEL, unit="a.u."),
            seed.calibrated_axis("y", enums.AxisType.SPACE, unit="micrometer"),
            seed.calibrated_axis("x", enums.AxisType.SPACE, unit="micrometer"),
        ],
        scale=[1.0, 0.325, 0.325],
    )

    delete = """
    mutation Delete($input: DeleteCalibrationInput!) {
      deleteCalibration(input: $input)
    }
    """

    def intrinsic_pk():
        return dataset.intrinsic_coordinate_system.pk

    result = await schema.execute(
        delete,
        context_value=authenticated_context,
        variable_values={"input": {"id": str(await sync_to_async(intrinsic_pk)())}},
    )
    assert result.errors, "deleting an INTRINSIC system through deleteCalibration must be rejected"

    result = await schema.execute(delete, context_value=authenticated_context, variable_values={"input": {"id": str(physical.pk)}})
    assert not result.errors, result.errors
    assert not await CoordinateSystem.objects.filter(pk=physical.pk).aexists()


# --- 8. units are pint units, not free-form strings --------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_calibrated_axis_unit_must_be_a_parseable_unit(authenticated_context: HttpContext):
    """A calibrated axis' unit is the kanne `Unit` scalar, so a unit pint cannot parse is rejected.

    A free-form unit string is worthless: it fails at the moment someone tries to
    convert with it, which is long after the write and far from whoever made it.
    Rejecting it at the write is the whole point of typing the field -- and a
    direct ORM write through create_calibrated_axes is held to the same standard.
    """
    from asgiref.sync import sync_to_async

    from core.logic import graph as graph_logic
    from core.models import CoordinateSystem as CS

    def make_system():
        return CS.objects.create(
            name="units",
            kind=enums.CoordinateSystemKindChoices.PHYSICAL.value,
            organization=authenticated_context.request.organization,
        )

    system = await sync_to_async(make_system)()

    with pytest.raises(ValueError, match="not a valid unit"):
        await sync_to_async(graph_logic.create_calibrated_axes)(system, [seed.calibrated_axis("y", enums.AxisType.SPACE, unit="furlongs_per_fortnight")])

    # A real unit is kept with its given spelling, and 'a.u.' is the escape hatch
    # for an axis whose values are arbitrary (a channel's intensity, say).
    axes = await sync_to_async(graph_logic.create_calibrated_axes)(
        system,
        [
            seed.calibrated_axis("y", enums.AxisType.SPACE, unit="micrometer"),
            seed.calibrated_axis("x", enums.AxisType.SPACE, unit="a.u."),
        ],
    )
    assert [a.unit for a in axes] == ["micrometer", "a.u."]
