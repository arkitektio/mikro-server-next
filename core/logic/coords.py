"""Every spatial derivation in the coordinate graph, in one place.

Nothing in this module may be inlined at a call site. That is not a style
preference: a transposed coordinate or a dropped half-voxel offset does not
raise, it just puts things in the wrong place, plausibly, and it will be found
years later by someone measuring the wrong cell. The permutation between array
order and vertex order in particular is one named, tested function precisely
because every copy of it is a place where the transpose can silently invert.

The conventions this module encodes:

* **The voxel centre is the origin.** Voxel ``n`` occupies ``[n - 0.5, n + 0.5)``,
  so an ROI on voxel 340 has an edge at 340.5. This is the RFC-5 half-open
  convention, and it is why a downsample introduces a half-voxel offset at all.
* **Array order is slowest-varying first** (``..., z, y, x``), which is the order
  of a numpy shape tuple. Vertex/GPU order is ``(x, y, z)``. They are reverses of
  each other over the spatial axes, and confusing them is the failure mode of the
  whole architecture.
* **Pyramid scales are absolute, never relative.** A level's scale is derived from
  the actual shapes, not from a nominal ``2 ** level``, and the derived value is
  what gets stored. It is a dimensionless pixel-to-pixel ratio: physical space
  enters the model exactly once, as a physical-space edge off the intrinsic system,
  never through the pyramid.
"""

from dataclasses import dataclass
from typing import Iterable, Sequence

from kanne_server import scalars as kanne_scalars

from core import enums

# The axis ordering rule (RFC-5 inspired): time first, then channel and custom
# types, then space. Only the relative rank matters; axes of equal rank keep
# their given order.
_AXIS_TYPE_RANK: dict[str, int] = {
    enums.AxisTypeChoices.TIME.value: 0,
    enums.AxisTypeChoices.CHANNEL.value: 1,
    enums.AxisTypeChoices.MICROTIME.value: 1,
    enums.AxisTypeChoices.SPECTRUM.value: 1,
    enums.AxisTypeChoices.COORDINATE.value: 1,
    enums.AxisTypeChoices.DISPLACEMENT.value: 1,
    enums.AxisTypeChoices.SPACE.value: 2,
}

# The axis types a pyramid may downsample: the *continuous* ones. Striding a
# long timelapse, re-binning FLIM arrival times or re-binning a spectrum is as
# meaningful as spatial downsampling and uses the same half-voxel arithmetic.
# Categorical axes stay out: c=0.5 between two channels means nothing.
_DOWNSAMPLABLE_TYPES: frozenset[str] = frozenset(
    {
        enums.AxisTypeChoices.SPACE.value,
        enums.AxisTypeChoices.TIME.value,
        enums.AxisTypeChoices.MICROTIME.value,
        enums.AxisTypeChoices.SPECTRUM.value,
    }
)

# The axis types a phasor may be taken over: the continuous, periodic-ish ones a
# discrete Fourier transform means something over. A DFT along z or c is not a
# slightly-odd rendering choice, it is arithmetic over an axis whose coordinates
# are positions or acquisition indices rather than samples of a periodic signal.
_PHASOR_TYPES: frozenset[str] = frozenset(
    {
        enums.AxisTypeChoices.MICROTIME.value,
        enums.AxisTypeChoices.SPECTRUM.value,
    }
)


# The physical dimension an axis type's unit must have. A TIME axis measured in
# micrometres is not a slightly-off calibration, it is a lie the arithmetic will
# happily propagate: seconds and metres compose into the same matrix. Types absent
# from this map (CHANNEL, COORDINATE, DISPLACEMENT) index into something with no
# agreed dimension, so any parseable unit is allowed.
_UNIT_DIMENSION_BY_TYPE: dict[str, str] = {
    enums.AxisTypeChoices.TIME.value: "[time]",
    enums.AxisTypeChoices.MICROTIME.value: "[time]",
    enums.AxisTypeChoices.SPECTRUM.value: "[length]",
    enums.AxisTypeChoices.SPACE.value: "[length]",
}


class AxisOrderError(ValueError):
    """Raised when a coordinate system's axes violate the RFC-5 type ordering."""


class AxisUnitError(ValueError):
    """Raised when a calibrated axis' unit does not have the dimension its type requires."""


class NonAffineTransformError(ValueError):
    """Raised when a transformation that must be affine is not (e.g. a displacement field)."""


@dataclass(frozen=True)
class AxisSpec:
    """The subset of an axis this module needs, so the logic never touches the ORM.

    ``Axis`` rows, ingest inputs and test fixtures all coerce into this. Only the
    name and the semantic type are load-bearing: units live on calibrated systems'
    axes and never enter a derivation, so they are not carried here.
    """

    name: str
    type: str


@dataclass(frozen=True)
class RenderAxes:
    """The array-axis names a renderer maps to screen x, y, z, time and intensity."""

    x: str
    y: str
    z: str | None
    t: str | None
    intensity: str | None
    phasor: str | None


def axis_type_rank(axis_type: str) -> int:
    """The RFC-5 ordering rank of an axis type: time (0) < channel/custom (1) < space (2)."""
    return _AXIS_TYPE_RANK.get(axis_type, 1)


def is_sorted_by_type(axes: Sequence[AxisSpec]) -> bool:
    """Whether the axes obey the RFC-5 type ordering (time, then channel/custom, then space)."""
    ranks = [axis_type_rank(axis.type) for axis in axes]
    return all(earlier <= later for earlier, later in zip(ranks, ranks[1:]))  # noqa: B905 - pairwise, deliberately ragged


def assert_axis_type_order(axes: Sequence[AxisSpec]) -> None:
    """Enforce the RFC-5 axis ordering MUST at ingest.

    This is a hard validation rather than a test-only assertion because
    :func:`resolve_render_axes` derives x, y and z from the *position* of the
    spatial axes. Out-of-order axes do not make that derivation fail; they make
    it quietly wrong.
    """
    if not is_sorted_by_type(axes):
        given = ", ".join(f"{axis.name}:{axis.type}" for axis in axes)
        raise AxisOrderError(f"Axes must be ordered by type (time, then channel and custom types, then space), but were given as [{given}]")


def assert_axis_names_unique(axes: Sequence[AxisSpec]) -> None:
    """Enforce that no two axes of one coordinate system share a name.

    The database already refuses this -- ``Axis.Meta.unique_together`` carries
    ``("coordinate_system", "name")`` -- but every axis writer uses ``bulk_create``, so
    what the caller gets back is a raw ``IntegrityError`` naming a Postgres constraint.
    A name is how every edge refers to an axis (``inputAxes``, ``outputAxes``, an
    annotation's coordinate pins), so a duplicate is worth a sentence rather than a 500.
    """
    seen: set[str] = set()
    duplicates: set[str] = set()
    for axis in axes:
        if axis.name in seen:
            duplicates.add(axis.name)
        seen.add(axis.name)

    if duplicates:
        given = ", ".join(axis.name for axis in axes)
        raise AxisOrderError(f"The axes of a coordinate system are named uniquely -- an edge names an axis to act on it -- but {sorted(duplicates)} appears more than once in [{given}]")


def assert_unit_matches_type(axis_name: str, axis_type: str, unit: str) -> None:
    """Enforce that a calibrated axis' unit has the dimension its type requires.

    A SPACE axis in seconds and a TIME axis in micrometres are both accepted today,
    and neither fails anywhere: the unit is never read by an arithmetic path, so the
    error surfaces years later as a plot with the wrong axis. Rejected at write time
    instead, where the author is still in the room.

    ``a.u.`` stays the escape hatch, for an axis whose unit genuinely is arbitrary.
    """
    required = _UNIT_DIMENSION_BY_TYPE.get(axis_type)
    if required is None or kanne_scalars.is_arbitrary_unit(unit):
        return

    dimensionality = kanne_scalars.get_registry().Unit(kanne_scalars.normalize_compact_units(unit)).dimensionality
    if dict(dimensionality) != {required: 1}:
        raise AxisUnitError(f"Axis '{axis_name}' is a {axis_type} axis, so its unit must measure {required}, but '{unit}' does not. Use 'a.u.' for a genuinely arbitrary unit.")


def assert_at_most_one_time_axis(axes: Sequence[AxisSpec]) -> None:
    """Enforce that a coordinate system has at most one time axis.

    Two time axes are legal today -- they have equal ordering rank, so nothing
    complains -- and `resolve_render_axes` silently picks the first and drops the
    second. A scene with two clocks has no meaning; it just renders one of them.
    """
    time_axes = [axis.name for axis in axes if axis.type == enums.AxisTypeChoices.TIME.value]
    if len(time_axes) > 1:
        raise AxisOrderError(f"A coordinate system may carry at most one TIME axis, but was given {time_axes}")


def spatial_axes(axes: Sequence[AxisSpec]) -> list[AxisSpec]:
    """The spatial axes, in array order (slowest-varying first, i.e. z, y, x)."""
    return [axis for axis in axes if axis.type == enums.AxisTypeChoices.SPACE.value]


#: The spatial spec each SPACE-axis count denotes. Any count past the table collapses
#: to a single HYPERVOLUME at write time, so the open-ended `>=` is resolved here rather
#: than at query time.
_SPATIAL_SPEC_BY_COUNT: dict[int, enums.ADatasetSpec] = {
    0: enums.ADatasetSpec.SCALAR,
    1: enums.ADatasetSpec.PROFILE,
    2: enums.ADatasetSpec.IMAGE,
    3: enums.ADatasetSpec.VOLUME,
}

#: The spec each acquisition axis type denotes, by its presence alone. The types
#: absent here (COORDINATE, DISPLACEMENT, INDEX) are deliberately unnamed: they
#: describe what an array's *values* are, not what was acquired, and asking for
#: them is what the `hasAxisTypes` filter is for.
_SPEC_BY_AXIS_TYPE: dict[str, enums.ADatasetSpec] = {
    enums.AxisTypeChoices.TIME.value: enums.ADatasetSpec.TIMESERIES,
    enums.AxisTypeChoices.CHANNEL.value: enums.ADatasetSpec.MULTICHANNEL,
    enums.AxisTypeChoices.SPECTRUM.value: enums.ADatasetSpec.SPECTRAL,
    enums.AxisTypeChoices.MICROTIME.value: enums.ADatasetSpec.FLIM,
}


def specs_for_axes(axes: Sequence[AxisSpec]) -> list[enums.ADatasetSpec]:
    """Every spec these axes satisfy: the one spatial member, then a modifier per acquisition axis present.

    The spatial member comes first and the modifiers follow in a fixed order, so
    the list is deterministic and a client may compare it by equality.

    This is the single source of truth for a dataset's spec: ``stored_spec`` is
    materialized *from* it at creation (by :func:`core.logic.graph.create_pixel_axes`)
    and the migration backfill reads it too, so the derivation lives here once and
    the stored column can never disagree with it.
    """
    count = len(spatial_axes(axes))
    specs = [_SPATIAL_SPEC_BY_COUNT.get(count, enums.ADatasetSpec.HYPERVOLUME)]
    present = {axis.type for axis in axes}
    specs.extend(spec for axis_type, spec in _SPEC_BY_AXIS_TYPE.items() if axis_type in present)
    return specs


def array_to_vertex_order(coords: Sequence[float], axes: Sequence[AxisSpec]) -> list[float]:
    """Permute spatial coordinates from array order (z, y, x) to vertex order (x, y, z).

    THE permutation. Array order is slowest-varying first, matching a numpy shape
    tuple; vertex order is what a GPU expects. They are reverses of each other,
    and every inlined copy of this reversal is a place where it can be forgotten
    in one direction only.

    ``coords`` is indexed like the full axis list; only the spatial entries are
    returned, reversed.
    """
    spatial_indices = [index for index, axis in enumerate(axes) if axis.type == enums.AxisTypeChoices.SPACE.value]
    return [coords[index] for index in reversed(spatial_indices)]


def vertex_to_array_order(vertex: Sequence[float], axes: Sequence[AxisSpec]) -> dict[str, float]:
    """The inverse of :func:`array_to_vertex_order`: map (x, y, z) back onto named array axes."""
    spatial = spatial_axes(axes)
    if len(vertex) != len(spatial):
        raise ValueError(f"Expected {len(spatial)} vertex components for spatial axes {[axis.name for axis in spatial]}, got {len(vertex)}")
    return {axis.name: value for axis, value in zip(reversed(spatial), vertex, strict=True)}


def resolve_render_axes(axes: Sequence[AxisSpec]) -> RenderAxes:
    """Derive the x / y / z / time / intensity axis names a renderer needs.

    Spatial axes are in array order, so the **last** spatial axis is x, the
    second-to-last is y and the third-to-last is z. (The previous rule took
    ``spatial[0]`` as x, which under the required ``(z, y, x)`` ordering picks
    z -- and under the flatter ``(c, y, x)`` used by most of the fixtures,
    silently swaps x and y.)

    Requires the axes to obey the RFC-5 ordering; call
    :func:`assert_axis_type_order` at ingest so this cannot be reached with a
    system that does not.
    """
    spatial = spatial_axes(axes)
    if len(spatial) < 2:
        raise ValueError(f"A renderable coordinate system needs at least two spatial axes, got {[axis.name for axis in spatial]}")

    return RenderAxes(
        x=spatial[-1].name,
        y=spatial[-2].name,
        z=spatial[-3].name if len(spatial) >= 3 else None,
        t=next((axis.name for axis in axes if axis.type == enums.AxisTypeChoices.TIME.value), None),
        intensity=next((axis.name for axis in axes if axis.type == enums.AxisTypeChoices.CHANNEL.value), None),
        phasor=next((axis.name for axis in axes if axis.type in _PHASOR_TYPES), None),
    )


def is_phasor_axis(axis_type: str) -> bool:
    """Whether a phasor may be taken over an axis of this type."""
    return axis_type in _PHASOR_TYPES


def pyramid_transform(
    shape_0: Sequence[int],
    shape_level: Sequence[int],
    axes: Sequence[AxisSpec],
) -> tuple[list[float], list[float]]:
    """The scale and translation taking a pyramid level into its dataset's intrinsic pixel space.

    Absolute, not relative -- and dimensionless. A real pyramid does not halve
    cleanly: a 36-voxel z axis floors to 36, 18, 9, 4, 2, 1, so its true factors
    are 1, 2, 4, **9, 18, 36** -- while a nominal ``2 ** level`` claims 1, 2, 4,
    8, 16, 32. Levels 3 and up are compressed in z, and a model that stores the
    nominal factors has no way to say so. It stays invisible for as long as every
    axis happens to be a power of two, which is why xy never showed it.

    The translation is the half-voxel offset a downsample introduces: level 0's
    voxel centres sit at 0, 1, 2, ... while level 1's sit at 0.5, 2.5, ... in
    level-0 coordinates. Without it, every level above 0 draws offset from level 0.

    Every level's output is the *same* intrinsic system -- a star, not a chain.
    Physical units never enter here: they are their own edge off the
    intrinsic system, so refining it cannot move the pyramid.

    Only *continuous* axes (space, time, microtime) may be downsampled -- a
    temporal pyramid over a long timelapse and a re-binned FLIM axis are as
    meaningful as spatial downsampling. Categorical axes (channel, coordinate,
    displacement) must keep their extent: c=0.5 between two channels is nonsense.
    """
    if not len(shape_0) == len(shape_level) == len(axes):
        raise ValueError(f"shape_0 ({len(shape_0)}), shape_level ({len(shape_level)}) and axes ({len(axes)}) must agree in length")

    scale: list[float] = []
    translation: list[float] = []

    for index, axis in enumerate(axes):
        if shape_level[index] == 0:
            raise ValueError(f"Level shape is 0 along axis '{axis.name}'")

        # Kept a float on purpose: a ceil-downsampled pyramid gives 33 -> 17, a
        # factor of 1.941..., and rounding it is exactly the bug this replaces.
        factor = shape_0[index] / shape_level[index]

        if axis.type not in _DOWNSAMPLABLE_TYPES and factor != 1:
            raise ValueError(f"Axis '{axis.name}' is of categorical type {axis.type} and must not be downsampled (shape {shape_0[index]} -> {shape_level[index]}). A fractional coordinate between two categories is meaningless.")

        scale.append(factor)
        translation.append((factor - 1) / 2)

    return scale, translation


def lens_shape(dataset_shape: Sequence[int], dataset_axis_names: Sequence[str], slices: Iterable) -> list[int]:
    """The shape a lens' slices cut out of its dataset.

    Uses Python's own slice semantics, so negatives, omitted bounds and
    out-of-range stops resolve exactly as they would on the array itself.
    """
    by_axis = {slice_.axis: slice_ for slice_ in slices}
    shape: list[int] = []

    for axis, size in zip(dataset_axis_names, dataset_shape, strict=True):
        selection = by_axis.get(axis)
        if selection is None:
            shape.append(size)
            continue
        start, stop, step = slice(selection.start, selection.stop, selection.step).indices(size)
        shape.append(len(range(start, stop, step)))

    return shape


def lens_to_parent(dataset_axis_names: Sequence[str], slices: Iterable) -> tuple[str, dict]:
    """The edge from a lens' coordinate system to its dataset's level-0 array system.

    This closes a live correctness hole: slicing shifts voxel coordinates and
    nothing recorded the shift, so an ROI drawn on a cropped lens had no defined
    path back to the dataset it came from.

    A pure crop is a ``TRANSLATION`` of the slice starts. A *stepped* lens also
    rescales, so it is a ``SEQUENCE[SCALE(step), TRANSLATION(start)]`` -- a
    translation-only edge would mis-place every subsampled lens, and would do it
    without complaining.

    Returns the kind and the params for the edge; the caller builds the rows.
    """
    by_axis = {slice_.axis: slice_ for slice_ in slices}

    starts = [float(by_axis[axis].start or 0) if axis in by_axis else 0.0 for axis in dataset_axis_names]
    steps = [float(by_axis[axis].step or 1) if axis in by_axis else 1.0 for axis in dataset_axis_names]

    if all(step == 1 for step in steps):
        return enums.TransformKindChoices.TRANSLATION.value, {"translation": starts}

    return enums.TransformKindChoices.SEQUENCE.value, {"scale": steps, "translation": starts}


# --- affine composition, for the derived ROI bounding box -------------------


def identity_matrix(n: int) -> list[list[float]]:
    """An (n+1) x (n+1) homogeneous identity matrix."""
    return [[1.0 if row == col else 0.0 for col in range(n + 1)] for row in range(n + 1)]


def matmul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    """Multiply two homogeneous matrices."""
    return [[sum(a[i][k] * b[k][j] for k in range(len(b))) for j in range(len(b[0]))] for i in range(len(a))]


def to_matrix(kind: str, params: dict, n: int) -> list[list[float]]:
    """The homogeneous matrix of an affine transformation kind.

    Raises :class:`NonAffineTransformError` for the kinds that have no matrix.
    Selection stays correct under those anyway -- the ROI box is pushed *forward*,
    and only vertex placement needs the forward map, which is always available.
    """
    matrix = identity_matrix(n)

    if kind == enums.TransformKindChoices.IDENTITY.value:
        return matrix

    if kind == enums.TransformKindChoices.SCALE.value:
        for i, value in enumerate(params["scale"]):
            matrix[i][i] = float(value)
        return matrix

    if kind == enums.TransformKindChoices.TRANSLATION.value:
        for i, value in enumerate(params["translation"]):
            matrix[i][n] = float(value)
        return matrix

    if kind in (enums.TransformKindChoices.AFFINE.value, enums.TransformKindChoices.ROTATION.value, enums.TransformKindChoices.MAP_AXIS.value):
        # MAP_AXIS is a permutation, which is an affine map -- but its permutation lives in
        # the edge's `inputAxes`/`outputAxes` *columns*, not in `params`, and this function
        # only ever sees params. `graph._edge_params` synthesizes the matrix from those two
        # lists, which is why this can be one branch instead of a signature change. Without
        # it, a MAP_AXIS anywhere on an ROI's chain raised, `compute_intrinsic_bbox` caught
        # the raise as "no chain", and the box came back in the wrong frame with an
        # intrinsic label on it.
        rows = params["affine"]
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                matrix[i][j] = float(value)
        return matrix

    if kind == enums.TransformKindChoices.SEQUENCE.value:
        # The SEQUENCE emitted by lens_to_parent: scale, then translate.
        if "scale" in params:
            matrix = matmul(to_matrix(enums.TransformKindChoices.SCALE.value, params, n), matrix)
        if "translation" in params:
            matrix = matmul(to_matrix(enums.TransformKindChoices.TRANSLATION.value, params, n), matrix)
        return matrix

    if kind == enums.TransformKindChoices.UNMAPPABLE.value:
        raise NonAffineTransformError("an UNMAPPABLE edge declares that no point of one space corresponds to a point of the other, so it has no matrix -- not an affine one, and not any other")

    raise NonAffineTransformError(f"{kind} has no affine matrix")


def permutation_matrix(input_axes: list[str], output_axes: list[str], axis_order: list[str]) -> list[list[float]]:
    """The affine matrix of a MAP_AXIS edge, a permutation written out.

    ``axis_order`` is the order the coordinate vector is written in, so a coordinate at
    column `i` is the value of ``axis_order[i]``. The edge maps ``input_axes[k]`` onto
    ``output_axes[k]``; an axis it does not name is one it leaves where it was.
    """
    n = len(axis_order)
    mapping = dict(zip(input_axes, output_axes))

    matrix = [[0.0] * (n + 1) for _ in range(n + 1)]
    matrix[n][n] = 1.0

    for column, axis in enumerate(axis_order):
        target = mapping.get(axis, axis)
        if target not in axis_order:
            raise NonAffineTransformError(f"A MAP_AXIS edge maps '{axis}' onto '{target}', which is not one of the axes {axis_order} its coordinates are written in")
        matrix[axis_order.index(target)][column] = 1.0

    return matrix


def compose(edges: Sequence[tuple[str, dict]], n: int) -> list[list[float]]:
    """Compose a path of edges, applied first to last, into one homogeneous matrix."""
    matrix = identity_matrix(n)
    for kind, params in edges:
        matrix = matmul(to_matrix(kind, params, n), matrix)
    return matrix


def apply(matrix: list[list[float]], point: Sequence[float]) -> list[float]:
    """Apply a homogeneous matrix to a point."""
    n = len(point)
    return [sum(matrix[i][j] * point[j] for j in range(n)) + matrix[i][n] for i in range(n)]


def bbox_corners(mins: Sequence[float], maxs: Sequence[float]) -> list[list[float]]:
    """Every corner of an axis-aligned box: 2**n of them, so eight in 3D."""
    corners: list[list[float]] = [[]]
    for low, high in zip(mins, maxs, strict=True):
        corners = [corner + [bound] for corner in corners for bound in (low, high)]
    return corners


def aabb(points: Sequence[Sequence[float]]) -> tuple[list[float], list[float]]:
    """The axis-aligned bounding box of a set of points."""
    if not points:
        raise ValueError("Cannot take the bounding box of no points")
    return (
        [min(point[i] for point in points) for i in range(len(points[0]))],
        [max(point[i] for point in points) for i in range(len(points[0]))],
    )


def transformed_bbox(mins: Sequence[float], maxs: Sequence[float], edges: Sequence[tuple[str, dict]]) -> dict:
    """The bounding box of a box after a chain of transformations.

    **Transforms all the corners**, not just the two extremes. An affine-transformed
    AABB is not an AABB: under any rotation or shear, pushing only min and max
    through the matrix gives a box that is not merely different but *wrong* --
    strictly too small, so geometry that is really inside it tests as outside.
    """
    matrix = compose(edges, len(mins))
    corners = [apply(matrix, corner) for corner in bbox_corners(mins, maxs)]
    low, high = aabb(corners)
    return {"min": low, "max": high}


def vectors_bbox(vectors: Sequence[Sequence[float]]) -> tuple[list[float], list[float]]:
    """The half-open bounding box of an ROI's vertices.

    The voxel centre is the origin and voxel ``n`` covers ``[n - 0.5, n + 0.5)``,
    so a single-voxel ROI at 340 spans 339.5 to 340.5 -- not 340 to 340.
    """
    low, high = aabb(vectors)
    return [value - 0.5 for value in low], [value + 0.5 for value in high]


# --- axis-aware composition, for pushing a box across a registration ------------------
#
# Everything above composes at one fixed rank, which is exactly right inside a dataset --
# a level, a lens and a physical space all keep the dataset's axes -- and exactly wrong across
# a registration. A BY_DIMENSION edge (what `create_identity_registration` writes for every
# ordinary registration) names the axes it acts on, leaves the ones it does not name
# untouched *by name*, and says nothing whatever about target axes it never mentions.
# Those three cases are distinguishable only with the axis names in hand, which is why
# these carry names where `to_matrix` carries a rank.
#
# `to_matrix`, `compose` and `transformed_bbox` are deliberately NOT widened to cover this.
# They are on the annotation write path, where their stored results are compared against
# each other for years; a change there is a regression surface for every `bbox_cube` already
# in the database, to serve a read path that can afford to be its own thing.


@dataclass(frozen=True)
class AxedStep:
    """One edge of a path, with both endpoints' axis names -- what a rank-changing map needs.

    ``acts_on_input`` / ``acts_on_output`` are the *named subset* a BY_DIMENSION or MAP_AXIS
    edge acts on, and ``input_axes`` / ``output_axes`` are the endpoints' full orders. Both
    are needed and neither substitutes for the other: the subset says which axes the
    parameters apply to, the full orders say which of the rest pass through and which the
    edge never mentions at all.
    """

    kind: str
    params: dict
    input_axes: tuple[str, ...]
    output_axes: tuple[str, ...]
    acts_on_input: tuple[str, ...] | None = None
    acts_on_output: tuple[str, ...] | None = None
    children: tuple[tuple[str, dict], ...] = ()


@dataclass(frozen=True)
class AxedForm:
    """One output axis as an affine functional of the source coordinates: ``sum(c_i * x_i) + k``."""

    coefficients: tuple[float, ...]
    constant: float


def _forms_from_matrix(matrix: list[list[float]], row_labels: Sequence[str], rank: int) -> dict[str, AxedForm]:
    """The rows of a homogeneous matrix as one labelled functional each."""
    return {
        label: AxedForm(coefficients=tuple(float(matrix[index][column]) for column in range(rank)), constant=float(matrix[index][rank]))
        for index, label in enumerate(row_labels)
        if index < len(matrix)
    }


def _identity_form(axis: str, input_axes: Sequence[str]) -> AxedForm:
    """The functional that passes one input axis through unchanged."""
    return AxedForm(coefficients=tuple(1.0 if name == axis else 0.0 for name in input_axes), constant=0.0)


def _by_dimension_forms(step: AxedStep) -> dict[str, AxedForm]:
    """A BY_DIMENSION edge's functionals: its named axes mapped, the rest passed through by name.

    Three populations, and the third is the one that matters. The axes it *names* are mapped
    by its parameters (or by its children). The axes it does not name but both systems have
    pass through unchanged -- that is the rule `edge_axis_names` and `assert_edge_rank`
    already state. Everything else -- an output axis the edge never mentions and the input
    does not have -- gets **no form at all**, because the edge genuinely says nothing about
    where the data sits along it. Absent is not zero: zero would pin a (c,y,x) dataset at
    z=0 in a (z,y,x) world and cull it out of every other slice.
    """
    acts_in = list(step.acts_on_input or ())
    acts_out = list(step.acts_on_output or ())
    rank = len(step.input_axes)

    forms: dict[str, AxedForm] = {}

    if acts_in and acts_out:
        sub = compose(list(step.children), len(acts_in)) if step.children else _params_matrix(step.params, len(acts_in), len(acts_out))
        for row, out_axis in enumerate(acts_out):
            if row >= len(sub):
                continue
            coefficients = [0.0] * rank
            for column, in_axis in enumerate(acts_in):
                if in_axis in step.input_axes:
                    coefficients[step.input_axes.index(in_axis)] = float(sub[row][column])
            forms[out_axis] = AxedForm(coefficients=tuple(coefficients), constant=float(sub[row][len(acts_in)]))

    for out_axis in step.output_axes:
        if out_axis in forms or out_axis in acts_out:
            continue
        if out_axis in step.input_axes and out_axis not in acts_in:
            forms[out_axis] = _identity_form(out_axis, step.input_axes)

    return forms


def _params_matrix(params: dict, rank_in: int, rank_out: int) -> list[list[float]]:
    """The sub-matrix a childless composite carries in its own parameters.

    Scale then translation, the order `to_matrix` already uses for a SEQUENCE, because a
    childless BY_DIMENSION is what `build_registration_edge` writes and
    ``_OPTIONAL_PARAMS_BY_KIND`` lets it carry both.
    """
    if "affine" in params:
        matrix = identity_matrix(max(rank_in, rank_out))
        for i, row in enumerate(params["affine"]):
            for j, value in enumerate(row):
                matrix[i][j] = float(value)
        return matrix

    matrix = identity_matrix(rank_in)
    if "scale" in params:
        matrix = matmul(to_matrix(enums.TransformKindChoices.SCALE.value, params, rank_in), matrix)
    if "translation" in params:
        matrix = matmul(to_matrix(enums.TransformKindChoices.TRANSLATION.value, params, rank_in), matrix)
    return matrix


def step_forms(step: AxedStep) -> dict[str, AxedForm]:
    """One affine functional per output axis this edge constrains, over its input axes.

    An output axis is absent exactly when the edge says nothing about it. Raises
    :class:`NonAffineTransformError` for the kinds with no closed form at all -- a FIELD,
    whose map is an array, and an UNMAPPABLE, which denies the correspondence outright.
    """
    if step.kind == enums.TransformKindChoices.BY_DIMENSION.value:
        return _by_dimension_forms(step)

    rank = len(step.input_axes)
    if step.kind == enums.TransformKindChoices.MAP_AXIS.value:
        # `permutation_matrix` writes its rows in the *input* system's axis order, because a
        # permutation relabels rather than reshapes -- so the row labels are the input's.
        matrix = permutation_matrix(list(step.acts_on_input or ()), list(step.acts_on_output or ()), list(step.input_axes))
        forms = _forms_from_matrix(matrix, step.input_axes, rank)
        return {axis: form for axis, form in forms.items() if axis in step.output_axes}

    if len(step.output_axes) != rank:
        # A square kind between systems of different rank has no matrix to be the matrix of.
        # `assert_edge_rank` checks a scale or translation against the *input* rank only, so
        # such an edge is writable and only shows up here.
        raise NonAffineTransformError(f"a {step.kind} edge maps {rank} axes onto {len(step.output_axes)}, so its parameters are not a square map -- only BY_DIMENSION states a rank change")

    return _forms_from_matrix(to_matrix(step.kind, step.params, rank), step.output_axes, rank)


def compose_forms(steps: Sequence[AxedStep], source_axes: Sequence[str]) -> dict[str, AxedForm]:
    """Compose a path into one functional per destination axis it constrains.

    **Substitution, not per-step boxing.** Re-bounding a box at every step inflates it under
    any rotation -- the very error `transformed_bbox` transforms all the corners to avoid --
    and an over-approximation here is a claim nobody asked for. Composing the functionals
    symbolically and bounding once at the end is exact.

    A destination axis whose functional would need a source axis some earlier step stopped
    constraining is dropped: once the path has let go of an axis, nothing downstream can
    take hold of it again.
    """
    rank = len(source_axes)
    current: dict[str, AxedForm] = {axis: _identity_form(axis, source_axes) for axis in source_axes}

    for step in steps:
        produced = step_forms(step)
        composed: dict[str, AxedForm] = {}
        for out_axis, form in produced.items():
            coefficients = [0.0] * rank
            constant = form.constant
            unconstrained = False
            for index, factor in enumerate(form.coefficients):
                if factor == 0.0:
                    continue
                inner = current.get(step.input_axes[index]) if index < len(step.input_axes) else None
                if inner is None:
                    unconstrained = True
                    break
                for position, value in enumerate(inner.coefficients):
                    coefficients[position] += factor * value
                constant += factor * inner.constant
            if unconstrained:
                continue
            composed[out_axis] = AxedForm(coefficients=tuple(coefficients), constant=constant)
        current = composed

    return current


def form_interval(form: AxedForm, mins: Sequence[float], maxs: Sequence[float]) -> list[float]:
    """The exact range of one affine functional over an axis-aligned box.

    The closed form of what :func:`transformed_bbox` does by enumerating corners: an affine
    functional attains its extremes at a corner, and the sign of each coefficient decides
    which bound that term takes, independently of every other term. O(n) rather than
    O(2**n), which matters because every anchor of every source pays it -- and pinned equal
    to the corner enumeration by test, since "obviously equivalent" is how a half-voxel goes
    missing.
    """
    low = high = form.constant
    for index, factor in enumerate(form.coefficients):
        if factor == 0.0:
            continue
        a, b = factor * mins[index], factor * maxs[index]
        low += min(a, b)
        high += max(a, b)
    return [low, high]


def axed_bbox(mins: Sequence[float], maxs: Sequence[float], forms: dict[str, AxedForm]) -> dict[str, list[float]]:
    """The axis-keyed extent of a box under an already-composed path."""
    return {axis: form_interval(form, mins, maxs) for axis, form in forms.items()}


def boxes_overlap(a: dict[str, list[float]], b: dict[str, list[float]]) -> bool:
    """Whether two axis-keyed boxes overlap: a conjunction over the axes they BOTH constrain.

    An axis only one side constrains cannot exclude anything. A source registered on (y, x)
    alone really is in every z slice of the world, and a region naming only the first two
    axes really does say nothing about the rest -- so in both directions, silence is not a
    zero to be tested against.

    Bounds are inclusive on purpose. A degenerate box -- ``min == max``, the plane probe a
    client sends to ask what is under this slice -- must still meet the sources containing
    it, and a strict comparison answers no to every one of them.
    """
    for axis, (low, high) in a.items():
        other = b.get(axis)
        if other is None:
            continue
        if high < other[0] or other[1] < low:
            return False
    return True
