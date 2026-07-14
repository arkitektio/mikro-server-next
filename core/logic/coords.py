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
  enters the model exactly once, as a calibration edge off the intrinsic system,
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
    Physical units never enter here: calibration is its own edge off the
    intrinsic system, so a recalibration cannot move the pyramid.

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


def lens_shape(dataset_shape: Sequence[int], dataset_dims: Sequence[str], slices: Iterable) -> list[int]:
    """The shape a lens' slices cut out of its dataset.

    Uses Python's own slice semantics, so negatives, omitted bounds and
    out-of-range stops resolve exactly as they would on the array itself.
    """
    by_dim = {slice_.dim: slice_ for slice_ in slices}
    shape: list[int] = []

    for dim, size in zip(dataset_dims, dataset_shape, strict=True):
        selection = by_dim.get(dim)
        if selection is None:
            shape.append(size)
            continue
        start, stop, step = slice(selection.start, selection.stop, selection.step).indices(size)
        shape.append(len(range(start, stop, step)))

    return shape


def lens_to_parent(dataset_dims: Sequence[str], slices: Iterable) -> tuple[str, dict]:
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
    by_dim = {slice_.dim: slice_ for slice_ in slices}

    starts = [float(by_dim[dim].start or 0) if dim in by_dim else 0.0 for dim in dataset_dims]
    steps = [float(by_dim[dim].step or 1) if dim in by_dim else 1.0 for dim in dataset_dims]

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

    if kind in (enums.TransformKindChoices.AFFINE.value, enums.TransformKindChoices.ROTATION.value):
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

    raise NonAffineTransformError(f"{kind} has no affine matrix")


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
