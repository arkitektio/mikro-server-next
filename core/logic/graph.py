"""Building and querying the coordinate graph.

The ORM-touching half of the coordinate work; the pure arithmetic lives in
:mod:`core.logic.coords`. Every write path that creates a coordinate system, an
axis or an edge goes through here, so that the derivations happen exactly once
and their results are what get stored.

Nothing here composes a path to world. That is the client's job, on purpose: the
same dataset can sit in two scenes under two different registrations, so there is
no single answer the server could give. See :mod:`core.models.coords`.
"""

from kanne_server import scalars as kanne_scalars

from core import enums, models
from core.creation import CreationContext
from core.logic import coords as coords_logic


def create_pixel_axes(system: "models.CoordinateSystem", axes: list) -> list["models.Axis"]:
    """Write a pixel-space system's axes, enumerating them so `order` is the array index.

    ``Axis.order`` being the array-dimension index is load-bearing: it is what ties
    ``scale[i]`` to ``shape[i]``, and what makes "the last spatial axis is x" a
    well-defined statement. It is always written by enumeration, never supplied by
    a caller.

    Pixel axes (INTRINSIC and ARRAY systems) keep their names and semantic types
    -- a z axis is spatial whether it holds indices or micrometres, and the render
    axes are derived from the types -- but they never carry a unit. Units belong
    to calibrated systems only.
    """
    rows = []
    for index, axis in enumerate(axes):
        axis_type = axis.type.value if hasattr(axis.type, "value") else axis.type
        rows.append(
            models.Axis(
                coordinate_system=system,
                order=index,
                name=axis.name,
                type=axis_type,
                unit=None,
                long_name=axis.long_name,
            )
        )
    return models.Axis.objects.bulk_create(rows)


def create_calibrated_axes(system: "models.CoordinateSystem", axes: list) -> list["models.Axis"]:
    """Write a calibrated (PHYSICAL / WORLD / ATLAS) system's axes, with their units.

    Every axis must carry a unit: a calibrated space without units is a pixel
    space wearing a costume. A unit pint cannot parse is worthless -- it will fail
    at the moment someone tries to convert with it, long after the write and far
    from whoever made it -- so it is rejected here, holding a direct ORM write to
    the same standard as the GraphQL boundary. 'a.u.' is the escape hatch for
    genuinely arbitrary units.
    """
    rows = []
    for index, axis in enumerate(axes):
        axis_type = axis.type.value if hasattr(axis.type, "value") else axis.type
        if axis.unit is None:
            raise ValueError(f"Axis '{axis.name}' of calibrated system '{system.name}' has no unit. Use 'a.u.' for arbitrary units; a unitless axis belongs to a pixel system.")
        rows.append(
            models.Axis(
                coordinate_system=system,
                order=index,
                name=axis.name,
                type=axis_type,
                unit=kanne_scalars.parse_unit(axis.unit),
                long_name=axis.long_name,
            )
        )
    return models.Axis.objects.bulk_create(rows)


def _sequence(
    *,
    input_system: "models.CoordinateSystem",
    output_system: "models.CoordinateSystem",
    scale: list[float],
    translation: list[float],
    ctx: CreationContext,
) -> "models.Transformation":
    """A SEQUENCE edge of a scale then a translation, with the children RFC-5 permits to omit their endpoints."""
    sequence = models.Transformation.objects.create(
        kind=enums.TransformKindChoices.SEQUENCE.value,
        input=input_system,
        output=output_system,
        params={},
        creator=ctx.user,
        organization=ctx.organization,
    )
    # The children omit input and output: the wrapping sequence supplies them.
    models.Transformation.objects.create(
        kind=enums.TransformKindChoices.SCALE.value,
        parent=sequence,
        order=0,
        params={"scale": scale},
        creator=ctx.user,
        organization=ctx.organization,
    )
    models.Transformation.objects.create(
        kind=enums.TransformKindChoices.TRANSLATION.value,
        parent=sequence,
        order=1,
        params={"translation": translation},
        creator=ctx.user,
        organization=ctx.organization,
    )
    return sequence


def create_level_edge(
    *,
    array_system: "models.CoordinateSystem",
    intrinsic: "models.CoordinateSystem",
    shape_0: list[int],
    shape_level: list[int],
    axis_specs: list[coords_logic.AxisSpec],
    ctx: CreationContext,
) -> "models.Transformation":
    """Store the edge placing one pyramid level in its dataset's intrinsic pixel space.

    The scale is **absolute** and dimensionless, derived from the actual shapes --
    so a pyramid whose axes do not halve cleanly (36 floors to 18, 9, 4, 2, 1,
    giving factors 1, 2, 4, **9, 18, 36**, not 1, 2, 4, 8, 16, 32) is described
    correctly rather than plausibly. The translation is the half-voxel offset the
    downsample introduces; without it every level above 0 draws offset from level 0.

    Derived once, here, at write time. If it were re-derived at read, every reader
    would have to agree on how -- and one of them would not.
    """
    scale, translation = coords_logic.pyramid_transform(shape_0, shape_level, axis_specs)

    if all(offset == 0 for offset in translation):
        # Level 0, or any level that happens not to be downsampled: a scale suffices.
        return models.Transformation.objects.create(
            kind=enums.TransformKindChoices.SCALE.value,
            input=array_system,
            output=intrinsic,
            params={"scale": scale},
            creator=ctx.user,
            organization=ctx.organization,
        )

    return _sequence(input_system=array_system, output_system=intrinsic, scale=scale, translation=translation, ctx=ctx)


def create_lens_edge(
    *,
    lens_system: "models.CoordinateSystem",
    parent_system: "models.CoordinateSystem",
    dataset_dims: list[str],
    slices: list,
    ctx: CreationContext,
) -> "models.Transformation":
    """Store the edge placing a lens back in its dataset's level-0 voxel space.

    A pure crop is a translation of the slice starts. A *stepped* lens also
    rescales, so it is a sequence -- a translation-only edge would mis-place every
    subsampled lens, and would do it without complaining.
    """
    kind, params = coords_logic.lens_to_parent(dataset_dims, slices)

    if kind == enums.TransformKindChoices.TRANSLATION.value:
        return models.Transformation.objects.create(
            kind=kind,
            input=lens_system,
            output=parent_system,
            params=params,
            creator=ctx.user,
            organization=ctx.organization,
        )

    return _sequence(
        input_system=lens_system,
        output_system=parent_system,
        scale=params["scale"],
        translation=params["translation"],
        ctx=ctx,
    )


def create_calibration(
    *,
    dataset: "models.ADataset",
    name: str,
    axes: list,
    scale: list[float] | None,
    translation: list[float] | None,
    affine: list[list[float]] | None,
    ctx: CreationContext,
) -> "models.CoordinateSystem":
    """Create a calibrated PHYSICAL system for a dataset and the edge placing its pixels there.

    This is the *only* place physical space enters the model: a calibration is one
    node (the physical space, axes carrying the units) plus one edge (intrinsic
    pixels -> physical). Refining it later is ``update_transformation`` on the
    edge, which bumps its version -- the pyramid, the ROIs and their bounding
    boxes never move, because they live in pixel space.

    The calibrated axes correspond 1:1, by position, to the intrinsic axes: that
    is what ties ``scale[i]`` to pixel axis ``i``. Their semantic types must match
    -- a calibration reinterprets an axis, it does not permute or retype them (an
    axis permutation is an explicit MAP_AXIS edge, not a calibration).
    """
    intrinsic = dataset.intrinsic_coordinate_system
    if intrinsic is None:
        raise ValueError(f"Dataset {dataset.pk} has no intrinsic coordinate system to calibrate")

    intrinsic_axes = list(intrinsic.axes.all())
    if len(axes) != len(intrinsic_axes):
        raise ValueError(f"Calibration supplies {len(axes)} axes but the dataset has {len(intrinsic_axes)}")
    for supplied, pixel_axis in zip(axes, intrinsic_axes):  # noqa: B905 - lengths checked above
        supplied_type = supplied.type.value if hasattr(supplied.type, "value") else supplied.type
        if supplied_type != pixel_axis.type:
            raise ValueError(f"Calibrated axis '{supplied.name}' has type {supplied_type} but pixel axis '{pixel_axis.name}' at the same position is {pixel_axis.type}. A calibration reinterprets axes; it does not retype them.")

    n = len(intrinsic_axes)
    if affine is not None and (scale is not None or translation is not None):
        raise ValueError("A calibration takes either an affine matrix or scale/translation, not both")
    if affine is None and scale is None and translation is None:
        raise ValueError("A calibration needs a transformation: scale, translation or affine")
    for vector, label in ((scale, "scale"), (translation, "translation")):
        if vector is not None and len(vector) != n:
            raise ValueError(f"Calibration {label} has {len(vector)} entries but the dataset has {n} axes")
    if affine is not None and any(len(row) != n + 1 for row in affine):
        raise ValueError(f"Calibration affine rows must have {n + 1} entries (N+1, the last column is the translation)")

    system = models.CoordinateSystem.objects.create(
        name=f"{dataset.name}/{name}",
        kind=enums.CoordinateSystemKindChoices.PHYSICAL.value,
        dataset=dataset,
        creator=ctx.user,
        organization=ctx.organization,
    )
    create_calibrated_axes(system, axes)

    if affine is not None:
        models.Transformation.objects.create(
            kind=enums.TransformKindChoices.AFFINE.value,
            input=intrinsic,
            output=system,
            params={"affine": affine},
            creator=ctx.user,
            organization=ctx.organization,
        )
    elif scale is not None and translation is not None and any(offset != 0 for offset in translation):
        _sequence(input_system=intrinsic, output_system=system, scale=scale, translation=translation, ctx=ctx)
    elif scale is not None:
        models.Transformation.objects.create(
            kind=enums.TransformKindChoices.SCALE.value,
            input=intrinsic,
            output=system,
            params={"scale": scale},
            creator=ctx.user,
            organization=ctx.organization,
        )
    else:
        models.Transformation.objects.create(
            kind=enums.TransformKindChoices.TRANSLATION.value,
            input=intrinsic,
            output=system,
            params={"translation": translation},
            creator=ctx.user,
            organization=ctx.organization,
        )

    return system


def edges_from(system: "models.CoordinateSystem") -> list["models.Transformation"]:
    """The top-level edges leaving a coordinate system (excluding wrapper children)."""
    return list(models.Transformation.objects.filter(input=system, parent__isnull=True))


def path_to_intrinsic(system: "models.CoordinateSystem") -> list[tuple[str, dict]]:
    """The chain of edges from a system up to its dataset's intrinsic pixel space.

    Scene-independent, calibration-independent and always defined, which is
    exactly why the ROI bounding box is expressed against it rather than against
    a scene's world or a physical calibration: world is scene-owned, and a
    calibration can be refined -- pixel space never moves.

    An INTRINSIC system is already there, so the chain is empty.
    """
    if system.kind == enums.CoordinateSystemKindChoices.INTRINSIC.value:
        return []

    chain: list[tuple[str, dict]] = []
    current = system
    seen: set[int] = set()

    while current and current.kind != enums.CoordinateSystemKindChoices.INTRINSIC.value:
        if current.pk in seen:
            raise ValueError(f"Cycle in the path from coordinate system {system.pk} to its intrinsic space")
        seen.add(current.pk)

        edge = models.Transformation.objects.filter(input=current, parent__isnull=True).select_related("output").first()
        if edge is None or edge.output is None:
            raise ValueError(f"Coordinate system {current.pk} has no edge towards an intrinsic space")

        chain.append(_edge_params(edge))
        current = edge.output

    return chain


def _edge_params(edge: "models.Transformation") -> tuple[str, dict]:
    """An edge as (kind, params), flattening a SEQUENCE's children into the params coords.compose expects."""
    if edge.kind != enums.TransformKindChoices.SEQUENCE.value:
        return edge.kind, edge.params

    params: dict = {}
    for child in edge.children.order_by("order"):
        params.update(child.params)
    return edge.kind, params


def transform_version(system: "models.CoordinateSystem") -> int:
    """The summed version of the edges between a system and its intrinsic space.

    Recorded on an ROI as provenance -- what the geometry was authored against. It
    is never used to resolve a coordinate; it only tells you whether the chain has
    moved under the ROI since.
    """
    total = 0
    current = system
    seen: set[int] = set()

    while current and current.kind != enums.CoordinateSystemKindChoices.INTRINSIC.value:
        if current.pk in seen:
            break
        seen.add(current.pk)
        edge = models.Transformation.objects.filter(input=current, parent__isnull=True).select_related("output").first()
        if edge is None:
            break
        total += edge.version
        current = edge.output

    return total


def compute_intrinsic_bbox(system: "models.CoordinateSystem", vectors: list[list[float]]) -> dict | None:
    """The bounding box of an ROI's geometry, pushed into its dataset's intrinsic space.

    Pushes **every corner** of the box, not just the two extremes. An
    affine-transformed AABB is not an AABB: under any rotation or shear, taking
    only min and max through the matrix yields a box that is strictly too small, so
    geometry that really is inside it tests as outside.
    """
    if not vectors:
        return None

    low, high = coords_logic.vectors_bbox(vectors)

    try:
        chain = path_to_intrinsic(system)
    except ValueError:
        # A PHYSICAL, WORLD or ATLAS system has no path down to a pixel space
        # (calibration edges point away from intrinsic). The box is still
        # meaningful in the system's own coordinates.
        chain = []

    return coords_logic.transformed_bbox(low, high, chain)


def scene_coordinate_systems(scene: "models.Scene") -> set[int]:
    """The ids of the coordinate systems a scene touches, directly or through its edges.

    Seeded from the scene's world system and from each layer's data source, then
    closed over the scene's transformation edges. An edge that no layer and no
    world system can reach is not part of this scene's graph, even if the row exists.
    """
    seeds: set[int] = set()

    world = getattr(scene, "world_coordinate_system", None)
    if world:
        seeds.add(world.pk)

    for layer in scene.layers.select_related("lens__dataset").all():
        lens = layer.lens
        if not lens:
            continue
        lens_system = getattr(lens, "coordinate_system", None)
        if lens_system:
            seeds.add(lens_system.pk)
        intrinsic = lens.dataset.intrinsic_coordinate_system
        if intrinsic:
            seeds.add(intrinsic.pk)

    edges = [(edge.input_id, edge.output_id) for edge in scene.coordinate_transformations.all() if edge.input_id and edge.output_id]

    # Undirected closure: an edge joins two systems, and a client may traverse it in
    # either direction (it inverts the matrix itself).
    reachable = set(seeds)
    changed = True
    while changed:
        changed = False
        for source, target in edges:
            if source in reachable and target not in reachable:
                reachable.add(target)
                changed = True
            elif target in reachable and source not in reachable:
                reachable.add(source)
                changed = True

    return reachable


def reachable_coordinate_systems(scene: "models.Scene") -> list["models.CoordinateSystem"]:
    """The coordinate systems a scene can reach, as rows."""
    return list(models.CoordinateSystem.objects.filter(pk__in=scene_coordinate_systems(scene)))
