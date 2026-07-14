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
    coords_logic.assert_at_most_one_time_axis([coords_logic.AxisSpec(name=axis.name, type=axis.type.value if hasattr(axis.type, "value") else axis.type) for axis in axes])

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

    The unit must also *measure the right thing*: a TIME axis in micrometres is
    rejected here rather than left to compose silently into a matrix. And a system
    carries at most one time axis -- a space with two clocks has no meaning, it just
    renders one of them.
    """
    specs = [coords_logic.AxisSpec(name=axis.name, type=axis.type.value if hasattr(axis.type, "value") else axis.type) for axis in axes]
    coords_logic.assert_at_most_one_time_axis(specs)

    rows = []
    for index, axis in enumerate(axes):
        axis_type = axis.type.value if hasattr(axis.type, "value") else axis.type
        if axis.unit is None:
            raise ValueError(f"Axis '{axis.name}' of calibrated system '{system.name}' has no unit. Use 'a.u.' for arbitrary units; a unitless axis belongs to a pixel system.")

        # Parseable first, then dimensionally right: a unit pint cannot read has no
        # dimension to check, and "furlongs_per_fortnight is not a valid unit" is the
        # more useful of the two errors to hand back.
        unit = kanne_scalars.parse_unit(axis.unit)
        coords_logic.assert_unit_matches_type(axis.name, axis_type, unit)

        rows.append(
            models.Axis(
                coordinate_system=system,
                order=index,
                name=axis.name,
                type=axis_type,
                unit=unit,
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


def edge_axis_names(edge: "models.Transformation", side: str) -> list[str]:
    """The axis names an edge's parameters are ordered by, on one side.

    ``scale``, ``translation`` and the columns of ``affine`` are written in the axis
    order of the edge's *input system* -- not in the order of whatever layer happens to
    be reading them. When the two differ (a [z,y,x] physical system under a [t,c,z,y,x]
    layer), a client that indexes the arrays against its own dims puts the numbers on
    the wrong axes, and the result is plausible rather than obviously broken.

    So every edge states its own order, and a client never needs a side index of the
    scene's coordinate systems to recover it. A BY_DIMENSION edge names a *subset* --
    the axes it acts on, the ones it leaves alone being exactly those it does not name
    -- and that stored list is authoritative. Every other kind acts on all of them, in
    order.

    A SEQUENCE's children omit their own endpoints on purpose (the wrapper supplies
    them), so they inherit the wrapper's.
    """
    stored = edge.input_axes if side == "input" else edge.output_axes
    if stored:
        return list(stored)

    system = edge.input if side == "input" else edge.output
    if system is None and edge.parent_id:
        parent = edge.parent
        system = parent.input if side == "input" else parent.output

    return [axis.name for axis in system.axes.all()] if system else []


def is_reverse_traversable(edge: "models.Transformation") -> bool:
    """Whether a path may walk this edge against its stored direction.

    The BFS is happy to traverse an edge backwards and hand the client an
    ``inverted: true`` step to undo. That is only honest for a map that *has* an
    inverse. An edge whose two sides do not have the same number of axes collapses
    dimensions -- placing a (c,y,x) dataset into a (t,z,y,x) world states nothing about
    where `t` and `z` came from -- so there is no inverse to hand back, and emitting the
    step anyway asks the client to invert a non-square matrix.

    A rank-preserving edge inverts fine, whatever its kind; that is the case every edge
    in the graph was until BY_DIMENSION existed, which is why this rule changes no path
    that resolves today.
    """
    return len(edge_axis_names(edge, "input")) == len(edge_axis_names(edge, "output"))


def assert_edge_rank(
    *,
    kind: str,
    params: dict,
    input_axes: list[str] | None,
    output_axes: list[str] | None,
    input_system: "models.CoordinateSystem",
    output_system: "models.CoordinateSystem",
) -> None:
    """Enforce that an edge's parameters have the rank its endpoints imply.

    None of this was checked before: a three-entry scale into a four-axis world was
    written without complaint, and `to_matrix` then wrote its last entry into the
    homogeneous corner of the matrix -- which does not raise, it just quietly scales
    everything. The endpoints already say what the rank must be, so an edge that
    disagrees with them is not a judgement call.
    """
    input_names = [axis.name for axis in input_system.axes.all()]
    output_names = [axis.name for axis in output_system.axes.all()]

    if kind == enums.TransformKindChoices.IDENTITY.value:
        # IDENTITY carries no parameters, so nothing below would check it -- and it is the
        # default for a derivation, where it means "the new pixels ARE the old pixels".
        # Between systems whose axes differ that is not an identity at all, it is a
        # rank-changing claim wearing an identity's clothes. A derivation that drops or
        # adds an axis (a projection) is a BY_DIMENSION naming the axes it keeps.
        if input_names != output_names:
            raise ValueError(f"An IDENTITY transformation says the two spaces are the same, but '{input_system.name}' has axes {input_names} and '{output_system.name}' has {output_names}. Use BY_DIMENSION, naming the axes it acts on, for a map that drops or reorders axes.")
        return

    if kind in (enums.TransformKindChoices.BY_DIMENSION.value, enums.TransformKindChoices.MAP_AXIS.value):
        if not input_axes or not output_axes:
            raise ValueError(f"A {kind} transformation must name the axes it acts on, in `inputAxes` and `outputAxes`. That naming IS the map: the axes it does not name are the ones it leaves untouched.")
        if len(input_axes) != len(output_axes):
            raise ValueError(f"A {kind} transformation maps its input axes onto its output axes one for one, but was given {len(input_axes)} ({input_axes}) and {len(output_axes)} ({output_axes})")
        for names, axes, side, system in ((input_names, input_axes, "input", input_system), (output_names, output_axes, "output", output_system)):
            if len(set(axes)) != len(axes):
                raise ValueError(f"A {kind} transformation names the {side} axis {axes} more than once")
            unknown = [axis for axis in axes if axis not in names]
            if unknown:
                raise ValueError(f"A {kind} transformation names {side} axes {unknown} that do not exist on coordinate system '{system.name}' (its axes are {names})")
        # The parameters, if any, act on the *named* axes -- that is the whole point of
        # naming them -- so the rank they are checked against is the subset's, not the
        # system's.
        rank_in, rank_out = len(input_axes), len(output_axes)
    else:
        rank_in, rank_out = len(input_names), len(output_names)

    for field in ("scale", "translation"):
        vector = params.get(field)
        if vector is not None and len(vector) != rank_in:
            raise ValueError(f"A {kind} transformation's `{field}` has one entry per input axis: expected {rank_in}, got {len(vector)}")

    affine = params.get("affine")
    if affine is not None:
        if len(affine) != rank_out:
            raise ValueError(f"A {kind} transformation's `affine` has one row per output axis: expected {rank_out} rows, got {len(affine)}")
        if any(len(row) != rank_in + 1 for row in affine):
            raise ValueError(f"A {kind} transformation's `affine` rows have one column per input axis plus the translation: expected {rank_in + 1} entries per row, got {[len(row) for row in affine]}")


def derivation_edge(dataset: "models.ADataset") -> "models.Transformation | None":
    """The edge placing a derived dataset's pixels in the space they were derived from.

    A derived dataset -- a deconvolution, a segmentation, a projection, a resample -- is not
    spatially free-floating: its pixels stand in a definite relation to the lens they were
    computed from, and that relation is an edge like any other (IDENTITY for an in-place op,
    TRANSLATION for a crop, SCALE for a resample, BY_DIMENSION for a projection that drops
    an axis). Recording it as an attribute instead would be a second copy of a spatial fact
    that no spatial query could walk.

    It is the edge out of the dataset's intrinsic system that lands in *another dataset*.
    An edge into a scene's WORLD is a registration, not a derivation: a registration says
    where the data was put, a derivation says where it came from.

    Lineage is single-parent by construction: a dataset is derived from one lens, so the
    first such edge is the answer. A fusion of two acquisitions would need a second parent
    and a rule for which one places it -- neither exists, and neither should be invented
    here on the strength of a `.first()`.
    """
    intrinsic = dataset.intrinsic_coordinate_system
    if intrinsic is None:
        return None

    candidates = models.Transformation.objects.filter(input=intrinsic, parent__isnull=True).select_related("output", "output__lens", "output__data_array").order_by("pk")
    for edge in candidates:
        if edge.output is None:
            continue
        source = system_dataset(edge.output)
        if source is not None and source.pk != dataset.pk:
            return edge
    return None


def lineage_ancestors(dataset: "models.ADataset") -> list["models.ADataset"]:
    """The datasets a dataset was derived from, nearest first. Empty for a root dataset."""
    ancestors: list[models.ADataset] = []
    seen: set[int] = {dataset.pk}
    current = dataset

    while True:
        edge = derivation_edge(current)
        if edge is None or edge.output is None:
            return ancestors
        source = system_dataset(edge.output)
        if source is None or source.pk in seen:
            return ancestors  # A cycle is nonsense, but it must not hang the request.
        seen.add(source.pk)
        ancestors.append(source)
        current = source


def lineage_root(dataset: "models.ADataset") -> "models.ADataset":
    """The dataset at the top of a derivation chain -- the one that is not derived from anything."""
    ancestors = lineage_ancestors(dataset)
    return ancestors[-1] if ancestors else dataset


def ensure_registered(scene: "models.Scene", dataset: "models.ADataset", ctx: CreationContext) -> "models.Transformation | None":
    """Place a dataset in a scene by default, if nothing has placed it yet.

    A layer in a scene with no registration edge resolves ``pathToWorld`` to null. The
    client can only degrade -- draw it in its own pixel frame and warn -- which reads as a
    rendering quirk when it is really a missing fact. Placing a layer in a scene *is* a
    claim that it belongs there, so the claim gets an edge.

    The default edge is the identity on the axes the two systems share **by name**: a
    (c,y,x) dataset in a (t,z,y,x) world maps y and x, and says nothing about t, z or c,
    which is exactly as much as anyone actually knows at this point. It is a BY_DIMENSION
    edge for the same reason -- a square edge could not express "and nothing about the
    rest".

    The layer's ``validity`` stays UNKNOWN, which is the badge: this registration was
    assumed, not measured. A real one sets MANUAL or VALIDATED.

    **A derived dataset is never pinned directly.** Its placement is not its own fact -- it
    follows from where the data it was computed from sits, through its derivation edge. So
    the assumption is made about the *root* of the lineage, and the derived data inherits
    it. Pinning the derived dataset instead would be worse than merely redundant: the
    fabricated edge is one hop from world, the real lineage is several, and the placement
    search is a shortest-path BFS -- so the assumption would outrank the truth, including a
    truth authored later.

    Returns None when the dataset is already placed, or when there is nothing to place it
    with (no world, no intrinsic system, or not a single shared axis).
    """
    world = getattr(scene, "world_coordinate_system", None)
    if world is None:
        return None

    # Registering a derived dataset means registering what it came from.
    dataset = lineage_root(dataset)

    intrinsic = dataset.intrinsic_coordinate_system
    if intrinsic is None:
        return None

    from core.logic.scene_graph import SceneGraph

    graph = SceneGraph(scene)
    if _bfs_path(graph.adjacency(dataset.pk), intrinsic.pk, world.pk) is not None:
        return None  # Already placed, by whatever route -- do not second-guess it.

    world_names = [axis.name for axis in world.axes.all()]
    shared = [axis.name for axis in intrinsic.axes.all() if axis.name in world_names]
    if not shared:
        return None

    edge = models.Transformation.objects.create(
        kind=enums.TransformKindChoices.BY_DIMENSION.value,
        name=f"{dataset.name} -> {scene.name} (assumed)",
        input=intrinsic,
        output=world,
        input_axes=shared,
        output_axes=shared,
        params={},
        creator=ctx.user,
        organization=ctx.organization,
    )
    models.Transformation.objects.create(
        kind=enums.TransformKindChoices.IDENTITY.value,
        parent=edge,
        order=0,
        params={},
        creator=ctx.user,
        organization=ctx.organization,
    )
    scene.coordinate_transformations.add(edge)
    return edge


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

    The walk never leaves the dataset. A registration edge points *out* of it -- from a
    lens, an array or the intrinsic system into some scene's world -- and it is not
    ordered behind the edge that goes up towards intrinsic, so an unfiltered "first edge
    out of this system" can pick it. The walk then wanders into world, finds no way on,
    and raises; :func:`compute_intrinsic_bbox` catches that as "no chain" and leaves the
    ROI's box in the frame it was drawn in, silently mislabelled as intrinsic. A
    registration is a fact about a scene, not about the dataset's own pixel geometry, so
    it has no business in this chain at all.
    """
    if system.kind == enums.CoordinateSystemKindChoices.INTRINSIC.value:
        return []

    dataset = system_dataset(system)

    chain: list[tuple[str, dict]] = []
    current = system
    seen: set[int] = set()

    while current and current.kind != enums.CoordinateSystemKindChoices.INTRINSIC.value:
        if current.pk in seen:
            raise ValueError(f"Cycle in the path from coordinate system {system.pk} to its intrinsic space")
        seen.add(current.pk)

        edge = _edge_towards_intrinsic(current, dataset)
        if edge is None or edge.output is None:
            raise ValueError(f"Coordinate system {current.pk} has no edge towards an intrinsic space")

        chain.append(_edge_params(edge))
        current = edge.output

    return chain


def _edge_towards_intrinsic(system: "models.CoordinateSystem", dataset: "models.ADataset | None") -> "models.Transformation | None":
    """The edge leading out of a system and *staying inside* its dataset.

    Ordered by pk so the choice between two candidates is deterministic rather than
    whatever the database happens to return first.
    """
    candidates = models.Transformation.objects.filter(input=system, parent__isnull=True).select_related("output", "output__lens", "output__data_array").order_by("pk")

    for edge in candidates:
        if edge.output is None:
            continue
        if dataset is None or system_dataset(edge.output) == dataset:
            return edge
    return None


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


def layer_source_system(layer: "models.Layer") -> "models.CoordinateSystem | None":
    """The coordinate system a layer's data is expressed in, per kind.

    An image layer's data lives in its lens' space, a shape layer's in its ROI's
    system, a mesh layer's in its collection's, and a point/track layer's in the
    system its table columns were declared against (which is optional -- a table
    without one has no defined space, and no placement).
    """
    if layer.kind == enums.LayerKindChoices.IMAGE.value and layer.lens_id:
        return getattr(layer.lens, "coordinate_system", None)
    if layer.kind == enums.LayerKindChoices.SHAPE.value and layer.data_roi_id:
        return layer.data_roi.coordinate_system
    if layer.kind == enums.LayerKindChoices.MESH.value and layer.mesh_collection_id:
        return layer.mesh_collection.coordinate_system
    if layer.kind in (enums.LayerKindChoices.POINT.value, enums.LayerKindChoices.TRACK.value):
        return layer.coordinate_system
    return None


def system_dataset(system: "models.CoordinateSystem") -> "models.ADataset | None":
    """The dataset a coordinate system belongs to, whichever owner it hangs off."""
    if system.intrinsic_of_id:
        return system.intrinsic_of
    if system.dataset_id:
        return system.dataset
    if system.lens_id:
        return system.lens.dataset
    if system.data_array_id:
        return system.data_array.dataset
    return None


def _bfs_path(
    adjacency: dict[int, list[tuple["models.Transformation", bool, int]]],
    source_pk: int,
    target_pk: int,
) -> list[tuple["models.Transformation", bool]] | None:
    """The shortest path of (edge, inverted) steps from source to target, or None.

    Expands edges in pk order so ties between equal-length paths resolve
    deterministically rather than by dict iteration luck.
    """
    if source_pk == target_pk:
        return []

    parents: dict[int, tuple[int, "models.Transformation", bool] | None] = {source_pk: None}
    frontier = [source_pk]
    while frontier and target_pk not in parents:
        next_frontier: list[int] = []
        for node in frontier:
            for edge, inverted, neighbor in sorted(adjacency.get(node, []), key=lambda step: step[0].pk):
                if neighbor in parents:
                    continue
                parents[neighbor] = (node, edge, inverted)
                next_frontier.append(neighbor)
        frontier = next_frontier

    if target_pk not in parents:
        return None

    steps: list[tuple["models.Transformation", bool]] = []
    node = target_pk
    while node != source_pk:
        previous, edge, inverted = parents[node]
        steps.append((edge, inverted))
        node = previous
    return list(reversed(steps))


# The placement questions -- where a layer sits in its scene, where each pyramid level
# sits, which systems a scene reaches -- are all searches over one scene's edge universe.
# That universe is built and searched by :class:`core.logic.scene_graph.SceneGraph`, which
# fetches it once per scene instead of once per layer per field. These stay as the callable
# names, delegating to it, so a caller with a single question does not have to know that.
# The import is local: scene_graph builds its searches out of the primitives above.


def path_in_scene(
    scene: "models.Scene",
    source: "models.CoordinateSystem",
    dataset: "models.ADataset | None" = None,
) -> list[tuple["models.Transformation", bool]] | None:
    """The path of edges from a source system to a scene's world system.

    This is the one place a "to world" question has a single right answer: the
    scene's membership set fixes which registration applies, so the ambiguity
    that forbids a server-side ``toWorld`` on a dataset does not exist here. The
    server still does not *compose*: it returns the edges (with their versions,
    their kinds, their provenance) and the client multiplies, exactly as it
    would after walking the graph itself.

    Returns ``None`` when there is no path (an unregistered source), and ``[]``
    when the source already *is* the world system.
    """
    from core.logic.scene_graph import SceneGraph

    graph = SceneGraph(scene)
    if graph.world is None:
        return None
    if dataset is None:
        dataset = system_dataset(source)
    return _bfs_path(graph.adjacency(dataset.pk if dataset else None), source.pk, graph.world.pk)


def placement_path(layer: "models.Layer") -> list[tuple["models.Transformation", bool]] | None:
    """The path of edges from a layer's source system to its scene's world system.

    ``None`` when the layer has no source system or no path; ``[]`` when the
    source already is the world system. See :func:`path_in_scene`.
    """
    from core.logic.scene_graph import SceneGraph

    return SceneGraph(layer.scene).placement_path(layer)


def level_placements(layer: "models.Layer") -> list[tuple["models.DataArray", list[tuple["models.Transformation", bool]] | None]]:
    """Per pyramid level, the path from that level's voxel grid to the layer's scene world.

    What a multiscale renderer actually consumes: it picks a level by zoom and
    needs ``level-N -> intrinsic -> ... -> world`` for that level -- not the
    lens-anchored path, whose first legs it would otherwise have to splice off.
    Every level stars into the same intrinsic system, so the registration tail is
    shared; the adjacency is built once and each level is one BFS over it.

    Lives on the layer rather than on DataArray because a data array belongs to
    no scene: a path field there would need a scene argument and reintroduce the
    ambient-toWorld ambiguity the layer scoping avoids.
    """
    from core.logic.scene_graph import SceneGraph

    return SceneGraph(layer.scene).level_placements(layer)


def scene_coordinate_systems(scene: "models.Scene") -> set[int]:
    """The ids of the coordinate systems a scene touches, directly or through its edges."""
    from core.logic.scene_graph import SceneGraph

    return SceneGraph(scene).reachable_system_ids()


def reachable_coordinate_systems(scene: "models.Scene") -> list["models.CoordinateSystem"]:
    """The coordinate systems a scene can reach, as rows."""
    from core.logic.scene_graph import SceneGraph

    return SceneGraph(scene).reachable_systems()
