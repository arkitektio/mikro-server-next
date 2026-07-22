"""Building and querying the coordinate graph.

The ORM-touching half of the coordinate work; the pure arithmetic lives in
:mod:`core.logic.coords`. Every write path that creates a coordinate system, an
axis or an edge goes through here, so that the derivations happen exactly once
and their results are what get stored.

Nothing here composes a path to world. That is the client's job, on purpose: the
same dataset can sit in two scenes under two different registrations, so there is
no single answer the server could give. See :mod:`core.models.coords`.
"""

from typing import TYPE_CHECKING, Iterable

from django.db.models import Q

from kanne_server import scalars as kanne_scalars

from core import enums, models
from core.creation import CreationContext
from core.logic import coords as coords_logic

if TYPE_CHECKING:
    from authentikate.models import Organization


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
    axis_specs = [coords_logic.AxisSpec(name=axis.name, type=axis.type.value if hasattr(axis.type, "value") else axis.type) for axis in axes]
    coords_logic.assert_at_most_one_time_axis(axis_specs)

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
                description=axis.description,
            )
        )
    created = models.Axis.objects.bulk_create(rows)

    # Materialize the dataset's structural spec at the one moment its immutable axes are
    # written. `intrinsic_of` is set only for a dataset's INTRINSIC system (null for the
    # ARRAY systems of pyramid levels, which write the same axes but describe no dataset),
    # so this fires exactly once per dataset and never for a level. The column is the read
    # path for `ADataset.spec`; `specs_for_axes` stays its single source of truth.
    #
    # Written without a historical record: this is part of creating the dataset, not an edit
    # to it. Only `name` and `description` are audited edits, and a provenance row here would
    # read as a post-creation change to something that is fixed at creation.
    dataset = system.intrinsic_of
    if dataset is not None:
        dataset.stored_spec = [spec.value for spec in coords_logic.specs_for_axes(axis_specs)]
        dataset.save_without_historical_record(update_fields=["stored_spec"])

    return created


def create_calibrated_axes(system: "models.CoordinateSystem", axes: list) -> list["models.Axis"]:
    """Write a calibrated (a PHYSICAL calibration, a world, a hub) system's axes, with their units.

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

    The axes must obey the RFC-5 type ordering, like every other axis writer's do: the
    render-axis derivation reads x/y/z off the *position* of the spatial axes, so a
    scrambled declaration does not fail, it renders wrong.
    """
    if not axes:
        # A space with no axes is not a space. It composes into nothing, renders nothing,
        # and every edge into it fails the rank check -- so it is rejected at the door
        # rather than left to be discovered by whatever tries to use it.
        raise ValueError(f"Coordinate system '{system.name}' was given no axes. A coordinate space needs at least one axis.")

    specs = [coords_logic.AxisSpec(name=axis.name, type=axis.type.value if hasattr(axis.type, "value") else axis.type) for axis in axes]
    coords_logic.assert_axis_type_order(specs)
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
                description=axis.description,
            )
        )
    return models.Axis.objects.bulk_create(rows)


def create_table_axes(system: "models.CoordinateSystem", coordinate_columns: list) -> list["models.Axis"]:
    """Write a table dataset's system axes from its coordinate columns.

    Neither pixel nor calibrated: a table's coordinate columns carry a unit exactly
    when the client declared one -- pixel-index centroids do not, an SMLM
    localization in nanometres does -- so this is the one axis writer that treats the
    unit as optional-but-validated. It is all-or-nothing across the spatial axes: a
    half-calibrated space (one axis in nm, its sibling unitless) composes wrongly
    into a single matrix, so it is rejected rather than stored.

    The columns must already obey the RFC-5 type ordering (time first, then space):
    the render-axis derivation reads x/y/z off the *position* of the spatial axes, so
    an out-of-order declaration does not fail, it renders wrong. ``order`` is written
    by enumeration -- for a table it is the coordinate columns' position, there being
    no array shape to index.
    """
    specs = [coords_logic.AxisSpec(name=col.name, type=col.axis_type.value if hasattr(col.axis_type, "value") else col.axis_type) for col in coordinate_columns]
    coords_logic.assert_axis_type_order(specs)
    coords_logic.assert_at_most_one_time_axis(specs)

    spatial_units = [col.unit for col in coordinate_columns if (col.axis_type.value if hasattr(col.axis_type, "value") else col.axis_type) == enums.AxisTypeChoices.SPACE.value]
    if spatial_units and any(u is None for u in spatial_units) and any(u is not None for u in spatial_units):
        raise ValueError("A table's spatial coordinate columns must be all calibrated (each with a unit) or all pixel-index (none with a unit). A half-calibrated space composes wrongly into one matrix.")

    rows = []
    for index, col in enumerate(coordinate_columns):
        axis_type = col.axis_type.value if hasattr(col.axis_type, "value") else col.axis_type
        unit = None
        if col.unit is not None:
            unit = kanne_scalars.parse_unit(col.unit)
            coords_logic.assert_unit_matches_type(col.name, axis_type, unit)
        rows.append(
            models.Axis(
                coordinate_system=system,
                order=index,
                name=col.name,
                type=axis_type,
                unit=unit,
                long_name=col.long_name,
                description=col.description,
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
    validity: str | None = None,
) -> "models.Transformation":
    """A SEQUENCE edge of a scale then a translation, with the children RFC-5 permits to omit their endpoints."""
    sequence = models.Transformation.objects.create(
        kind=enums.TransformKindChoices.SEQUENCE.value,
        input=input_system,
        output=output_system,
        params={},
        validity=validity or enums.PlacementValidityChoices.VALIDATED.value,
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
    dataset_axis_names: list[str],
    slices: list,
    ctx: CreationContext,
) -> "models.Transformation":
    """Store the edge placing a sliced lens back in its dataset's intrinsic pixel space.

    A pure crop is a translation of the slice starts. A *stepped* lens also
    rescales, so it is a sequence -- a translation-only edge would mis-place every
    subsampled lens, and would do it without complaining. An unsliced lens never
    gets here: it owns no system, because its space is the intrinsic space itself.
    """
    kind, params = coords_logic.lens_to_parent(dataset_axis_names, slices)

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
        dataset=dataset,
        creator=ctx.user,
        organization=ctx.organization,
    )
    create_calibrated_axes(system, axes)

    # INFERRED, not VALIDATED: the numbers come from acquisition metadata (a pixel size,
    # a stage pose) that the caller read, not from a derivation the server can vouch for.
    inferred = enums.PlacementValidityChoices.INFERRED.value

    if affine is not None:
        models.Transformation.objects.create(
            kind=enums.TransformKindChoices.AFFINE.value,
            input=intrinsic,
            output=system,
            params={"affine": affine},
            validity=inferred,
            creator=ctx.user,
            organization=ctx.organization,
        )
    elif scale is not None and translation is not None and any(offset != 0 for offset in translation):
        _sequence(input_system=intrinsic, output_system=system, scale=scale, translation=translation, ctx=ctx, validity=inferred)
    elif scale is not None:
        models.Transformation.objects.create(
            kind=enums.TransformKindChoices.SCALE.value,
            input=intrinsic,
            output=system,
            params={"scale": scale},
            validity=inferred,
            creator=ctx.user,
            organization=ctx.organization,
        )
    else:
        models.Transformation.objects.create(
            kind=enums.TransformKindChoices.TRANSLATION.value,
            input=intrinsic,
            output=system,
            params={"translation": translation},
            validity=inferred,
            creator=ctx.user,
            organization=ctx.organization,
        )

    return system


def edge_axis_names(edge: "models.Transformation", side: str) -> list[str]:
    """The axis names an edge's parameters are ordered by, on one side.

    ``scale``, ``translation`` and the columns of ``affine`` are written in the axis
    order of the edge's *input system* -- not in the order of whatever layer happens to
    be reading them. When the two differ (a [z,y,x] physical system under a [t,c,z,y,x]
    layer), a client that indexes the arrays against its own axis names puts the numbers on
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


#: Kinds whose inverse a client can actually compute. A BIJECTION is invertible by
#: construction -- it *carries* its inverse -- which is what that kind is for. A FIELD has
#: no closed-form inverse, so rank alone would wave it through. That refusal is not merely
#: a limit: a FIELD is many-to-one on purpose -- an object is a set of pixels, a track is a
#: set of observations -- so walking one backwards would ask for a point where there is a
#: set. UNMAPPABLE is not walked in any direction.
_INVERTIBLE_KINDS = frozenset(
    {
        enums.TransformKindChoices.IDENTITY.value,
        enums.TransformKindChoices.SCALE.value,
        enums.TransformKindChoices.TRANSLATION.value,
        enums.TransformKindChoices.MAP_AXIS.value,
        enums.TransformKindChoices.AFFINE.value,
        enums.TransformKindChoices.ROTATION.value,
        enums.TransformKindChoices.BIJECTION.value,
    }
)

#: Kinds that are invertible exactly when every one of their children is.
_WRAPPER_KINDS = frozenset(
    {
        enums.TransformKindChoices.SEQUENCE.value,
        enums.TransformKindChoices.BY_DIMENSION.value,
    }
)


def is_traversable(edge: "models.Transformation") -> bool:
    """Whether a placement search may use this edge **at all**, in either direction.

    Exactly one kind says no. An UNMAPPABLE edge declares that no point of its input
    corresponds to a point of its output, so a path that crossed it would be composing a
    map across a stated non-correspondence -- and would come back looking like every
    other path, plausible and wrong. The edge is a real fact and stays in the graph:
    discovery still returns it (that is how a client learns *why* the data cannot be
    placed), and the lineage still reads it. It is only the walk that refuses it.
    """
    return edge.kind != enums.TransformKindChoices.UNMAPPABLE.value


def is_registration_target(system: "models.CoordinateSystem | None") -> bool:
    """Whether a system is a SHARED space -- the one kind of node an edge lands in only
    by a scene's say-so.

    Scenes can compose over one shared space, so an edge into it (a registration) is
    walkable only when the scene holds it in its membership set: the membership is what
    lets two scenes disagree about a dataset's position in the same world. Deliberately
    NOT ``system_dataset(system) is None``: that is also true of a collection-owned
    (mesh/table) system, whose edges are the container's own facts and must stay
    walkable without any scene's blessing. Mirrors ``CoordinateSystem.kind == SHARED``.
    """
    return system is not None and not any(
        (
            system.intrinsic_of_id,
            system.dataset_id,
            system.data_array_id,
            system.lens_id,
            system.mesh_collection_id,
            system.table_dataset_id,
            system.annotation_collection_id,
        )
    )


def is_invertible(edge: "models.Transformation") -> bool:
    """Whether this edge's map can be undone.

    Kind, not rank. A displacement field maps N axes to N axes and has no closed-form
    inverse at all; rank alone would happily offer it for inversion and hand the client
    an `inverted: true` step it cannot honour.

    A wrapper is invertible exactly when all of its children are -- a SEQUENCE whose
    second step is a warp field is not invertible because its first step is a scale. That
    recursion is the reason this is a function and not a set membership test.

    Not caught here, and worth knowing: a **singular** square AFFINE (a projection written
    as a matrix) passes both the kind gate and the rank gate and still has no inverse.
    Catching it needs a determinant, which is numerics inside a metadata predicate.
    """
    if edge.kind in _WRAPPER_KINDS:
        children = list(edge.children.all())
        return all(is_invertible(child) for child in children) if children else True
    return edge.kind in _INVERTIBLE_KINDS


def is_reverse_traversable(edge: "models.Transformation") -> bool:
    """Whether a path may walk this edge against its stored direction.

    The BFS is happy to traverse an edge backwards and hand the client an
    ``inverted: true`` step to undo. That is only honest for a map that *has* an
    inverse, and there are two ways not to have one.

    It may collapse dimensions: an edge whose two sides do not have the same number of
    axes states nothing about where the missing ones came from -- placing a (c,y,x)
    dataset into a (t,z,y,x) world says nothing about `t` and `z` -- so inverting it
    would mean inverting a non-square matrix.

    Or its *kind* may have no inverse to give, at any rank: a FIELD, a declared
    non-correspondence. Rank alone was a sufficient rule only for as long as every
    writable kind happened to be invertible, which stopped being true the moment a
    field became writable.
    """
    return is_traversable(edge) and is_invertible(edge) and len(edge_axis_names(edge, "input")) == len(edge_axis_names(edge, "output"))


def assert_field_produces(*, field: "models.CoordinateSystem", output_axes: list[str]) -> None:
    """Enforce a FIELD's value axis against the rank the edge says its values produce.

    The value axis is deliberately **elidable**. A label mask is a plain (y,x) array whose
    one value is an object id; making it carry a length-1 COORDINATE axis to satisfy a
    schema would add a phantom dimension no reader wants and no writer stores. So absent
    means scalar, and scalar produces exactly one axis. A field that produces more than one
    must say so with a value axis -- whose type is, in the same breath, what says whether
    its numbers are positions or offsets.

    The value axis' *length* is not checked: an ``Axis`` row carries no size (shape lives on
    the DataArray), so "this COORDINATE axis has 3 positions, so the edge must produce 3
    axes" is not answerable from here. The scalar case is, and it is the one a mask hits.
    """
    value_axes = [axis for axis in field.axes.all() if axis.type in _VALUE_AXIS_TYPES]

    if len(value_axes) > 1:
        raise ValueError(
            f"A field's values are one thing, so its system carries at most one value axis, but '{field.name}' has {[axis.name for axis in value_axes]}. Two value axes would be two answers to 'what are these numbers'."
        )

    if not value_axes and len(output_axes) != 1:
        raise ValueError(
            f"Field '{field.name}' carries no value axis, so its values are scalar and produce exactly one axis, but this edge says they produce {output_axes}. Give the field a COORDINATE (positions) or DISPLACEMENT (offsets) value axis to produce more than one."
        )


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

    UNMAPPABLE is the one kind with no rank to disagree with. It maps nothing, so there
    is nothing for a rank to be the rank *of*, and relating a (c,y,x) image to a
    one-axis table of objects is not an error to be caught but the entire point.
    """
    if kind == enums.TransformKindChoices.UNMAPPABLE.value:
        return

    input_names = [axis.name for axis in input_system.axes.all()]
    output_names = [axis.name for axis in output_system.axes.all()]

    # An INDEX axis has no metric -- that is its definition, not an omission -- so the kinds
    # that do arithmetic on a coordinate mean nothing over it. Checked here rather than left
    # to the rank check below, which would happily accept `scale: [2.0]` on a space of object
    # ids and write "object 3 x 2 = object 6" without complaint.
    if kind in _METRIC_KINDS:
        indexed = [
            f"'{axis.name}' on '{system.name}'"
            for system in (input_system, output_system)
            for axis in system.axes.all()
            if axis.type == enums.AxisTypeChoices.INDEX.value
        ]
        if indexed:
            raise ValueError(
                f"A {kind} transformation does arithmetic on a coordinate, but {', '.join(indexed)} is an INDEX axis, which has no metric: the distance between object 3 and object 4 means nothing, so scaling or offsetting it does too. Relate an index space with FIELD (its values are the map) or UNMAPPABLE (nothing corresponds)."
            )

    if kind == enums.TransformKindChoices.IDENTITY.value:
        # IDENTITY carries no parameters, so nothing below would check it -- and it is the
        # default for a derivation, where it means "the new pixels ARE the old pixels".
        # Between systems whose axes differ that is not an identity at all, it is a
        # rank-changing claim wearing an identity's clothes. A derivation that drops or
        # adds an axis (a projection) is a BY_DIMENSION naming the axes it keeps.
        if input_names != output_names:
            raise ValueError(f"An IDENTITY transformation says the two spaces are the same, but '{input_system.name}' has axes {input_names} and '{output_system.name}' has {output_names}. Use BY_DIMENSION, naming the axes it acts on, for a map that drops or reorders axes.")
        return

    if kind == enums.TransformKindChoices.FIELD.value:
        # A FIELD consumes input axes and produces output axes out of the array's values;
        # the axes it does not name pass through by name. That is the entire map, so the
        # endpoints are checkable against it exactly -- no convention, no elided component.
        # Deliberately NOT the one-for-one rule below: a FIELD is many-to-one on purpose,
        # (y,x) collapsing to one object id.
        if not input_axes or not output_axes:
            raise ValueError("A FIELD transformation must name the axes it consumes in `inputAxes` and the axes its values produce in `outputAxes`. That naming IS the map: the axes it does not consume pass through by name.")
        for names, axes, side, system in ((input_names, input_axes, "input", input_system), (output_names, output_axes, "output", output_system)):
            if len(set(axes)) != len(axes):
                raise ValueError(f"A FIELD transformation names the {side} axis {axes} more than once")
            unknown = [axis for axis in axes if axis not in names]
            if unknown:
                raise ValueError(f"A FIELD transformation names {side} axes {unknown} that do not exist on coordinate system '{system.name}' (its axes are {names})")
        implied = [axis for axis in input_names if axis not in set(input_axes)] + list(output_axes)
        if sorted(implied) != sorted(output_names):
            raise ValueError(
                f"A FIELD transformation consuming {input_axes} of '{input_system.name}' {input_names} and producing {list(output_axes)} implies the axes {sorted(implied)}, but '{output_system.name}' has {sorted(output_names)}. The axes it does not consume pass through by name."
            )
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


#: The parameter each relation kind reads, for the edges a client authors when it states
#: where derived data came from. IDENTITY, BY_DIMENSION and UNMAPPABLE take none: an
#: identity has nothing to say, a BY_DIMENSION's map *is* the axes it names, and an
#: UNMAPPABLE has nothing to say by definition.
RELATION_PARAMS_BY_KIND: dict[str, str | None] = {
    enums.TransformKindChoices.IDENTITY.value: None,
    enums.TransformKindChoices.SCALE.value: "scale",
    enums.TransformKindChoices.TRANSLATION.value: "translation",
    enums.TransformKindChoices.AFFINE.value: "affine",
    enums.TransformKindChoices.ROTATION.value: "affine",
    enums.TransformKindChoices.BY_DIMENSION.value: None,
    enums.TransformKindChoices.UNMAPPABLE.value: None,
}


def write_relation_edge(
    *,
    name: str,
    input_system: "models.CoordinateSystem",
    output_system: "models.CoordinateSystem",
    kind: str,
    scale: list[float] | None = None,
    translation: list[float] | None = None,
    affine: list[list[float]] | None = None,
    input_axes: list[str] | None = None,
    output_axes: list[str] | None = None,
    reason: str | None = None,
    value_relation: "enums.ValueRelation | str | None" = None,
    ctx: CreationContext,
) -> "models.Transformation":
    """The one place a client-authored "this came from that" edge is written.

    A derived dataset, a mesh collection and a feature table all say the same kind of
    thing -- *my space, and how it relates to the space I was computed from* -- so they say
    it the same way, and the rank check that catches a projection wearing an identity's
    clothes catches it once for all three.

    ``value_relation`` is the derivation's second, orthogonal statement: what happened
    to the *numbers* (a threshold is spatially IDENTITY with CATEGORIZED values). It
    rides the same row because it is a fact about the same event -- a parallel lineage
    table for it was tried once and deleted (RFC-6).
    """
    if kind not in RELATION_PARAMS_BY_KIND:
        raise ValueError(f"A derivation cannot be a {kind}. Use IDENTITY for an in-place operation, TRANSLATION for a crop, SCALE for a resample, BY_DIMENSION for a projection that drops an axis, or UNMAPPABLE when the geometry does not survive at all.")

    supplied = {"scale": scale, "translation": translation, "affine": affine}

    if kind == enums.TransformKindChoices.UNMAPPABLE.value:
        # An UNMAPPABLE edge that carried a scale would be asserting a correspondence and
        # denying one in the same breath, and `to_matrix` would never read the parameter to
        # find out. Reject it rather than store a number nothing will ever honour.
        offending = sorted(field for field, value in supplied.items() if value is not None)
        if offending or input_axes or output_axes:
            raise ValueError(f"An UNMAPPABLE relation declares that no point of one space corresponds to a point of the other, so it takes no parameters and no axes. Drop {', '.join(offending + (['inputAxes'] if input_axes else []) + (['outputAxes'] if output_axes else []))}, or use a kind that does map.")

    params: dict = {}
    field = RELATION_PARAMS_BY_KIND[kind]
    if field is not None:
        value = supplied[field]
        if value is None:
            raise ValueError(f"A {kind} derivation requires `{field}`")
        params[field] = value
    if reason:
        params["reason"] = reason

    assert_edge_rank(
        kind=kind,
        params=params,
        input_axes=input_axes,
        output_axes=output_axes,
        input_system=input_system,
        output_system=output_system,
    )

    value_relation = value_relation.value if hasattr(value_relation, "value") else value_relation
    return models.Transformation.objects.create(
        kind=kind,
        name=name,
        input=input_system,
        output=output_system,
        input_axes=input_axes,
        output_axes=output_axes,
        params=params,
        # An authored claim about where data came from, not a map the server derived.
        validity=enums.PlacementValidityChoices.MANUAL.value,
        value_relation=value_relation,
        creator=ctx.user,
        organization=ctx.organization,
    )


def create_collection_system(
    *,
    name: str,
    axes: list,
    owner_field: str,
    owner: "models.MeshCollection | models.TableDataset | models.AnnotationCollection",
    ctx: CreationContext,
) -> "models.CoordinateSystem":
    """The coordinate system a collection owns, with its axes.

    Pixel axes, not calibrated ones: a mesh collection's vertices are in the voxel grid
    they were extracted from, a feature table's rows are enumerated, and an annotation
    collection's shapes are drawn in the grid of whatever it registers into. None carries
    a unit, and a unit is the only thing `create_calibrated_axes` would add.
    """
    system = models.CoordinateSystem.objects.create(
        name=name,
        creator=ctx.user,
        organization=ctx.organization,
        **{owner_field: owner},
    )
    create_pixel_axes(system, axes)
    return system


#: The parameters each directly-creatable edge kind requires. BY_DIMENSION requires none:
#: it is the axis *naming* that carries the map, and any parameters it carries act on the
#: axes it names. UNMAPPABLE requires none because it *has* none, and rejects them below.
_PARAMS_BY_KIND: dict[str, tuple[str, ...]] = {
    enums.TransformKind.IDENTITY.value: (),
    enums.TransformKind.SCALE.value: ("scale",),
    enums.TransformKind.TRANSLATION.value: ("translation",),
    enums.TransformKind.AFFINE.value: ("affine",),
    enums.TransformKind.ROTATION.value: ("affine",),
    enums.TransformKind.MAP_AXIS.value: (),
    enums.TransformKind.BY_DIMENSION.value: (),
    enums.TransformKind.FIELD.value: (),
    enums.TransformKind.UNMAPPABLE.value: (),
}

#: The parameters a BY_DIMENSION edge may additionally carry, acting on its named axes.
_OPTIONAL_PARAMS_BY_KIND: dict[str, tuple[str, ...]] = {
    enums.TransformKind.BY_DIMENSION.value: ("scale", "translation", "affine"),
}

#: The axis types that make an array readable as a FIELD's map: its *value* axis, whose
#: positions enumerate the components of each value. The type is the whole statement --
#: COORDINATE for absolute positions, DISPLACEMENT for offsets -- and it lives here, on the
#: array, rather than on the edge, because it is a property of the data. Two edges reading
#: one field cannot disagree about what its numbers mean.
_VALUE_AXIS_TYPES = (enums.AxisTypeChoices.COORDINATE.value, enums.AxisTypeChoices.DISPLACEMENT.value)

#: The metric kinds: the ones whose parameters do arithmetic on a coordinate. None of them
#: may touch an INDEX axis. An INDEX coordinate is an id -- object 3, row 7 -- and it has no
#: metric by definition, so object 3 x 2 = object 6 is not a wrong number but a meaningless
#: one. `assert_edge_rank` cannot catch it: it checks that a scale vector has one entry per
#: axis, never whether scaling *that* axis means anything.
_METRIC_KINDS = (
    enums.TransformKind.SCALE.value,
    enums.TransformKind.TRANSLATION.value,
    enums.TransformKind.AFFINE.value,
    enums.TransformKind.ROTATION.value,
)

#: The parameter fields an UNMAPPABLE edge must not carry: it declares that no point of one
#: space corresponds to a point of the other, so a scale on it would assert a correspondence
#: and deny one in the same breath, and nothing downstream would ever read the number.
_FORBIDDEN_ON_UNMAPPABLE = ("scale", "translation", "affine", "input_axes", "output_axes")


def claim_root(system: "models.CoordinateSystem") -> tuple:
    """The identity a registration claims *for*: the root of the fact tree the input hangs in.

    One truth per space is a rule about data, not about rows: two edges from two systems
    of one dataset's star (its calibration, its intrinsic) into one world are still two
    claims about where the *same pixels* sit, and so are a derived dataset's claim and its
    primary parent's -- the derivation already places the child through the parent. So the
    unit of uniqueness is the primary lineage root for anything dataset-owned, the
    collection for a collection system whose derivation does not place it (an UNMAPPABLE
    feature table has its own grid and needs its own claim), and the system itself for a
    hub -- a shared space is its own tree.
    """
    if system.mesh_collection_id or system.table_dataset_id or system.annotation_collection_id:
        derivation = collection_derivation_edge(system)
        if derivation is None or derivation.output is None or not is_traversable(derivation):
            return ("system", system.pk)
        dataset = system_dataset(derivation.output)
        return ("dataset", primary_lineage_root(dataset).pk) if dataset else ("system", system.pk)

    dataset = system_dataset(system)
    if dataset is not None:
        return ("dataset", primary_lineage_root(dataset).pk)
    return ("system", system.pk)


def _assert_one_claim_per_space(input_system: "models.CoordinateSystem", output_system: "models.CoordinateSystem") -> None:
    """Refuse a second registration of one fact tree into one shared space.

    One truth per space (RFC-6): within a world, where a piece of data sits has exactly
    one current answer. Refining that answer is an ordinary, audited update of the
    existing edge; a genuine alternative is a claim into a *different* space -- fork the
    hub (or mint another scene, whose world is its own space) and register there. Letting
    the rival row in would put the choice back into the walk, which is exactly where it
    must never live.

    Fact edges pass through untouched: an edge into an owned system is not a claim, and
    the fact tree has its own discipline (:func:`fact_edges`).
    """
    if not is_registration_target(output_system):
        return

    root = claim_root(input_system)
    rivals = (
        models.Transformation.objects.filter(output=output_system, parent__isnull=True)
        .exclude(kind=enums.TransformKindChoices.UNMAPPABLE.value)
        .select_related("input", "input__lens", "input__data_array")
    )
    for rival in rivals:
        if rival.input is not None and claim_root(rival.input) == root:
            raise ValueError(
                f"One truth per space: registration {rival.pk}"
                f"{f' ({rival.name!r})' if rival.name else ''} already places this data in "
                f"'{output_system.name}'. Refine it in place (updateTransformation -- the change is "
                "audited), or register into a fork of the space: an alternative alignment is a claim "
                "into a different world, never a rival row in this one."
            )


def build_registration_edge(
    *,
    input_system: "models.CoordinateSystem",
    output_system: "models.CoordinateSystem",
    kind: "enums.TransformKind | str",
    name: str | None = None,
    scale: list[float] | None = None,
    translation: list[float] | None = None,
    affine: list[list[float]] | None = None,
    input_axes: list[str] | None = None,
    output_axes: list[str] | None = None,
    field: "models.CoordinateSystem | None" = None,
    reason: str | None = None,
    validity: "enums.PlacementValidity | str | None" = None,
    value_relation: "enums.ValueRelation | str | None" = None,
    ctx: CreationContext,
) -> "models.Transformation":
    """Validate and write one edge of the coordinate graph, input -> output.

    The shared core of ``createTransformation`` and ``createCoordinateSystem``: it checks
    the parameters against the kind, forbids a map on an UNMAPPABLE edge, enforces the rank
    the endpoints imply, and writes the row. The systems and the field node are already
    resolved by the caller, so this stays an ORM write rather than a request-scoped one.

    BY_DIMENSION is how a registration crosses a rank boundary: a (c,y,x) dataset placed
    into a (t,z,y,x) world names the axes it acts on (``input_axes=["y","x"]``) and says
    nothing about the world's `t` and `z`. Direction is always forward: input to output.

    Validity defaults to MANUAL, not the VALIDATED an axis mirror claims: an edge that
    arrived through the API was *authored*, which is a different claim from "checked against
    the data", and the caller says VALIDATED only when it was.
    """
    kind = kind.value if hasattr(kind, "value") else kind

    if kind not in _PARAMS_BY_KIND:
        raise ValueError(f"{kind} cannot be created directly. SEQUENCE, BY_DIMENSION and BIJECTION wrappers are built by the ingest, which writes their children with them")

    supplied = {"scale": scale, "translation": translation, "affine": affine, "input_axes": input_axes, "output_axes": output_axes}

    if kind == enums.TransformKind.UNMAPPABLE.value:
        offending = [param for param in _FORBIDDEN_ON_UNMAPPABLE if supplied[param] is not None]
        if offending:
            raise ValueError(f"An UNMAPPABLE transformation declares that no point of one space corresponds to a point of the other, so it carries no map: drop {', '.join(offending)}, or use a kind that does map.")

    params: dict = {}
    for param in _PARAMS_BY_KIND[kind]:
        value = supplied[param]
        if value is None:
            raise ValueError(f"A {kind} transformation requires `{param}`")
        params[param] = value

    for param in _OPTIONAL_PARAMS_BY_KIND.get(kind, ()):
        value = supplied[param]
        if value is not None:
            params[param] = value

    if reason:
        params["reason"] = reason

    # The field itself, for the one kind whose map is an array rather than a formula. The
    # caller always states it -- an edge whose map is implicit is an edge nobody can read --
    # but a *self* field is stored as null: see `Transformation.field`, where PROTECT would
    # otherwise make a dereferenced mask undeletable.
    if kind == enums.TransformKind.FIELD.value:
        if field is None:
            raise ValueError("A FIELD transformation's map is the values of an array, so it requires `field`: the coordinate system of that array. Pass the input's own system when the array's pixels are themselves the map, as for a label mask.")
        assert_field_produces(field=field, output_axes=output_axes or [])
        if field.pk == input_system.pk:
            field = None
    elif field is not None:
        raise ValueError(f"A {kind} transformation's map is in its parameters, not in an array, so it takes no `field`")

    assert_edge_rank(
        kind=kind,
        params=params,
        input_axes=input_axes,
        output_axes=output_axes,
        input_system=input_system,
        output_system=output_system,
    )

    if kind != enums.TransformKind.UNMAPPABLE.value:
        _assert_one_claim_per_space(input_system, output_system)

    # A value relation is a statement about a *derivation*: what the operation did to
    # the numbers. A registration relates spaces -- values never cross it -- so carrying
    # one there would be a claim nothing can honour, like a scale on an UNMAPPABLE.
    if value_relation is not None and is_registration_target(output_system):
        raise ValueError(
            "A registration into a shared space relates spaces, not values: `valueRelation` belongs on a "
            "derivation edge (this data came from that data), where it states what the operation did to the numbers."
        )

    validity = validity.value if hasattr(validity, "value") else validity
    value_relation = value_relation.value if hasattr(value_relation, "value") else value_relation
    return models.Transformation.objects.create(
        kind=kind,
        name=name,
        input=input_system,
        output=output_system,
        input_axes=input_axes,
        output_axes=output_axes,
        params=params,
        field=field,
        validity=validity or enums.PlacementValidityChoices.MANUAL.value,
        value_relation=value_relation,
        creator=ctx.user,
        organization=ctx.organization,
    )


def derivation_edges(dataset: "models.ADataset") -> list["models.Transformation"]:
    """The edges placing a derived dataset's pixels in the spaces they were derived from.

    A derived dataset -- a deconvolution, a segmentation, a projection, a resample -- is not
    spatially free-floating: its pixels stand in a definite relation to the lenses they were
    computed from, and each such relation is an edge like any other (IDENTITY for an in-place
    op, TRANSLATION for a crop, SCALE for a resample, BY_DIMENSION for a projection that
    drops an axis). Recording them as attributes instead would be a second copy of spatial
    facts that no spatial query could walk.

    They are the edges out of the dataset's intrinsic system that land in *another dataset*.
    An edge into a scene's world is a registration, not a derivation: a registration says
    where the data was put, a derivation says where it came from.

    **The order is the priority, and the first edge is the primary parent.** A fusion of
    two acquisitions has two real parents, but lineage needs a rule for which one is
    primary -- and that rule is the creator's declared order, written at ingest as pk
    order, not an accident of a `.first()`. The primary is the fact tree's one parent
    edge: it alone places (RFC-6); the rest are recorded facts that ``derivedFrom``
    reports and no placement walk crosses.

    **Kind-blind, and it must stay that way.** An UNMAPPABLE derivation is still a
    derivation -- "this came from that, and the geometry did not survive" is the fact it
    exists to record, and it is the only machine-readable answer to "why can this not be
    placed". The *walks* refuse that edge (see :func:`is_traversable`); this, which merely
    reports it, does not. Filter it here and ``derivedFrom`` omits it, which is the
    silence the kind was invented to break. (Creation refuses an UNMAPPABLE entry ahead of
    a mappable one, so a kind-blind first element is still the placing parent.)
    """
    intrinsic = dataset.intrinsic_coordinate_system
    if intrinsic is None:
        return []

    candidates = models.Transformation.objects.filter(input=intrinsic, parent__isnull=True).select_related("output", "output__lens", "output__data_array").order_by("pk")
    edges: list[models.Transformation] = []
    for edge in candidates:
        if edge.output is None:
            continue
        source = system_dataset(edge.output)
        if source is not None and source.pk != dataset.pk:
            edges.append(edge)
    return edges


def _datasets_derived_into(output_filter: "Q", exclude_pk: int) -> list["models.ADataset"]:
    """The datasets whose derivation edges land in the systems `output_filter` selects.

    The other end of :func:`derivation_edges`, read from the source's side: a derivation
    edge's input is the derived dataset's intrinsic system, so an edge landing here names
    a child. Requiring the input to *be* an intrinsic system is what keeps this to datasets:
    a mesh collection or a table dataset derives from data the same way, but its edge starts
    at the collection's own system and it is not an ADataset.

    Kind-blind and priority-blind, exactly as the forward is. An UNMAPPABLE child still came
    from here, and so did a fusion that named this source second -- both are facts this
    reports; neither is a path any placement walk crosses.
    """
    edges = (
        models.Transformation.objects.filter(output_filter, parent__isnull=True, input__intrinsic_of__isnull=False)
        .select_related("input__intrinsic_of")
        .order_by("pk")
    )

    seen: set[int] = {exclude_pk}
    derived: list[models.ADataset] = []
    for edge in edges:
        # A child fused from two lenses of one source has two edges into it, and is one child.
        child = edge.input.intrinsic_of
        if child.pk in seen:
            continue
        seen.add(child.pk)
        derived.append(child)
    return derived


def derived_datasets(dataset: "models.ADataset") -> list["models.ADataset"]:
    """The datasets computed from this one: every dataset whose `derivedFrom` names a space of ours."""
    return _datasets_derived_into(
        Q(output__intrinsic_of=dataset) | Q(output__dataset=dataset) | Q(output__lens__dataset=dataset) | Q(output__data_array__dataset=dataset),
        exclude_pk=dataset.pk,
    )


def lens_derived_datasets(lens: "models.Lens") -> list["models.ADataset"]:
    """The datasets computed from this lens' selection.

    An unsliced lens owns no system -- its space *is* the dataset's intrinsic -- so it
    reports what was derived from the whole grid, and two unsliced lenses over one dataset
    report the same children. That is not a leak: the model has one space there, and
    saying otherwise would invent a distinction nothing stored can support.
    """
    space = lens.space
    if space is None:
        return []
    return _datasets_derived_into(Q(output=space), exclude_pk=lens.dataset_id)


def primary_derivation_edge(dataset: "models.ADataset") -> "models.Transformation | None":
    """The derivation edge that places a derived dataset: the first, by its creator's declared order."""
    edges = derivation_edges(dataset)
    return edges[0] if edges else None


def lineage_ancestors(dataset: "models.ADataset") -> list["models.ADataset"]:
    """The primary-parent chain above a dataset, nearest first. Empty for a root dataset.

    The primary parent only, at every hop: placement walks the fact *tree* (RFC-6), and
    the tree's one parent edge for a derived dataset is its primary derivation. A fusion
    owes its other parents historically -- ``derivation_edges`` reports every one -- but
    it sits where its primary sits, full stop; wanting it placed some other way is a
    re-anchoring (reorder ``derivedFrom`` at ingest, or register the fusion's own system),
    never a path the walk finds on its own.

    This is the *spatial* lineage -- who places whom -- so it stops at an UNMAPPABLE
    primary. Data whose geometry did not survive inherits nothing from that source: it
    has its own pixel grid and nothing relates the two, however much it owes the source
    historically. (``derivation_edges`` still reports that edge; the historical lineage is
    intact. It is only placement that ends there.)
    """
    ancestors: list[models.ADataset] = []
    seen: set[int] = {dataset.pk}
    current = dataset

    while True:
        edge = primary_derivation_edge(current)
        if edge is None or edge.output is None or not is_traversable(edge):
            return ancestors
        source = system_dataset(edge.output)
        if source is None or source.pk in seen:
            return ancestors  # A cycle is nonsense, but it must not hang the request.
        seen.add(source.pk)
        ancestors.append(source)
        current = source


def primary_lineage_root(dataset: "models.ADataset") -> "models.ADataset":
    """The dataset at the top of the primary-parent chain -- the one whose placement carries the rest.

    A fusion has several parents, but "where does this data ultimately come from" must
    name exactly one dataset, and the creator's declared order says which: the first
    entry, at every hop. Registering the root places everything derived from it, which
    is why a client aligning a lineage authors its edge against the root rather than
    against each descendant.
    """
    seen: set[int] = {dataset.pk}
    current = dataset

    while True:
        edge = primary_derivation_edge(current)
        if edge is None or edge.output is None or not is_traversable(edge):
            return current
        source = system_dataset(edge.output)
        if source is None or source.pk in seen:
            return current  # A cycle is nonsense, but it must not hang the request.
        seen.add(source.pk)
        current = source


def _placement_universe(
    scene: "models.Scene", source_system: "models.CoordinateSystem"
) -> tuple["models.CoordinateSystem", list[int], list["models.Transformation"]]:
    """The flat edge universe a single-source placement question searches.

    Fetched in one query: the source system's own edges, every edge owned by a dataset in
    its lineage, and the world's edges -- which include the world's registrations, because
    under RFC-6 those are a property of the *space*, not of any scene's say-so. Shared
    verbatim by :func:`is_placeable_in_scene` (which walks it) and
    :func:`assert_placeable_in_scene` (which classifies a failure), so the two never
    disagree about which edges the walk was allowed to see. Returns
    ``(world, lineage_ids, edges)``.
    """
    world = scene.world

    dataset = system_dataset(source_system)
    lineage_ids = [dataset.pk] + [ancestor.pk for ancestor in lineage_ancestors(dataset)] if dataset else []

    edges = list(
        models.Transformation.objects.filter(parent__isnull=True)
        .filter(
            # The source system itself: a collection-owned (mesh collection / table
            # dataset) system belongs to no dataset, so its derivation edge would not
            # enter through the lineage terms below.
            Q(input=source_system)
            | Q(input__intrinsic_of__in=lineage_ids)
            | Q(input__dataset__in=lineage_ids)
            | Q(input__lens__dataset__in=lineage_ids)
            | Q(input__data_array__dataset__in=lineage_ids)
            | Q(input=world)
            | Q(output=world)
        )
        .distinct()
        .select_related("input", "input__lens", "input__data_array", "output")
        .prefetch_related("children", "input__axes", "output__axes")
    )
    return world, lineage_ids, edges


def _container_key(system: "models.CoordinateSystem | None") -> tuple | None:
    """The container a system belongs to, off preloaded FKs: the node of the fact tree it lives under."""
    if system is None:
        return None
    dataset_id = _fk_dataset_id(system)
    if dataset_id is not None:
        return ("dataset", dataset_id)
    if system.mesh_collection_id:
        return ("mesh", system.mesh_collection_id)
    if system.table_dataset_id:
        return ("table", system.table_dataset_id)
    if system.annotation_collection_id:
        return ("annotation", system.annotation_collection_id)
    return ("system", system.pk)


def fact_edges(edges: list["models.Transformation"]) -> list["models.Transformation"]:
    """The fact tree: registrations dropped, and one walkable parent edge per system.

    Two rules, both RFC-6. An edge into a shared space is a *claim*, not a fact --
    a search adds the claims into its own world and never any other, which is what
    keeps `reg_v1` composed forward and `reg_v2` composed backward from ever
    meeting in one path. And a system leaves its container through **one** edge:
    its primary. A derived dataset has exactly one placing parent -- the first
    derivation edge by its creator's declared order -- and any further parents are
    recorded facts (``derivedFrom`` still reports them) that never place. Within a
    container everything stays: levels, lenses and calibrations are children, and
    a tree has as many of those as it likes.

    The primary is selected kind-blind, exactly like :func:`primary_derivation_edge`:
    if the first cross-container edge is UNMAPPABLE, the data has its own grid and
    *nothing* cross-container walks -- the untraversable edge itself stays in the
    list, inert to the walk, so the unmappable classification can still see it.
    """
    facts = [edge for edge in edges if not is_registration_target(edge.output)]

    primary: dict[int, models.Transformation] = {}
    for edge in facts:
        if edge.input_id is None or edge.output_id is None:
            continue
        if _container_key(edge.input) == _container_key(edge.output):
            continue
        best = primary.get(edge.input_id)
        if best is None or edge.pk < best.pk:
            primary[edge.input_id] = edge

    kept: list[models.Transformation] = []
    for edge in facts:
        if edge.input_id is not None and edge.output_id is not None and _container_key(edge.input) != _container_key(edge.output):
            chosen = primary[edge.input_id]
            if edge.pk != chosen.pk and is_traversable(edge):
                continue
        kept.append(edge)
    return kept


def _fact_reachable(source_system: "models.CoordinateSystem", edges: list["models.Transformation"]) -> set[int]:
    """Every system the source reaches across fact edges alone."""
    adjacency = adjacency_of(fact_edges(edges))
    reachable = {source_system.pk}
    frontier = [source_system.pk]
    while frontier:
        next_frontier: list[int] = []
        for node in frontier:
            for _edge, _inverted, neighbor in adjacency.get(node, ()):
                if neighbor not in reachable:
                    reachable.add(neighbor)
                    next_frontier.append(neighbor)
        frontier = next_frontier
    return reachable


def is_placeable_in_scene(scene: "models.Scene", source_system: "models.CoordinateSystem | None") -> bool:
    """Whether the registration into the scene's world that places this source exists.

    True when the world's registration anchors a space the source fact-reaches, or when
    the source fact-reaches the world outright (it *is* the world system). Singular by
    construction: a registration is unique per (data-tree, world) -- the collision guard
    in :func:`build_registration_edge` refuses a rival -- so this is an existence check,
    never a choice. The boolean core of :func:`assert_placeable_in_scene`, and the single
    source of truth the ``placeableIn`` filter shares with creation-time refusal.
    A sourceless layer is never placeable.
    """
    if source_system is None:
        return False
    world, _lineage_ids, edges = _placement_universe(scene, source_system)
    reachable = _fact_reachable(source_system, edges)
    if world.pk in reachable:
        return True
    return any(edge.output_id == world.pk and is_traversable(edge) and edge.input_id in reachable for edge in edges)


def assert_placeable_in_scene(scene: "models.Scene", source_system: "models.CoordinateSystem | None") -> None:
    """Reject a layer whose source system nothing places in the scene's world.

    Creating a layer in a scene *is* a claim that the data belongs there, and the graph
    must already hold that claim: a registration is authored exactly once, explicitly
    (``createTransformation`` into the world), never fabricated as a side effect of a
    layer mutation. There is nothing to choose here -- one truth per space: the
    registration is unique per (data-tree, world), so a source is placed or it is not,
    and when it is not the error says which of the two very different gaps it is:

    **Unregistered** -- placeable, but nobody has authored the registration yet. The
    error points at the mutation that closes the gap.

    **Unmappable** -- the source's data reaches other spaces only across an UNMAPPABLE
    relation, which declares that no point correspondence exists. There is no missing
    registration to author, and the error says so instead of sending someone to look
    for one. The classification mirrors :meth:`core.logic.scene_graph.SceneGraph.placement_state`
    so that creation-time refusal and query-time state never disagree.

    Flat cost, deliberately: one edge query over the source's lineage universe plus the
    world's edges -- never the scene's layers -- so creating a layer does not get slower
    with every layer already in the scene.
    """
    if source_system is None:
        raise ValueError("The layer's data has no coordinate system, so it has no space to be placed by. Nothing sourceless can be composed into a scene.")

    if is_placeable_in_scene(scene, source_system):
        return

    world, lineage_ids, edges = _placement_universe(scene, source_system)
    if _blocked_by_unmappable(source_system, set(lineage_ids), edges):
        raise ValueError(
            f"'{source_system.name}' can not be placed in the world of scene '{scene.name}': "
            "its data reaches other spaces only across an UNMAPPABLE relation, which declares that "
            "no point correspondence exists. There is no missing registration to author here."
        )
    raise ValueError(
        f"Nothing places '{source_system.name}' in the world of scene '{scene.name}'. "
        "Author the registration -- createTransformation from the data's system (or any system it "
        "reaches through its own facts) into the scene's world -- then create the layer."
    )


def _blocked_by_unmappable(
    source_system: "models.CoordinateSystem",
    lineage_ids: set[int],
    edges: list["models.Transformation"],
) -> bool:
    """Whether an unplaced source is unplaced because of a stated non-correspondence.

    Mirrors :meth:`~core.logic.scene_graph.SceneGraph.placement_state` against the flat
    universe already fetched: a collection system whose derivation edge (the earliest
    edge leaving it) is UNMAPPABLE, or a dataset one of whose lineage-owned edges is.
    Like there, this is a coarse honesty check, not a proof of impossibility -- a fusion
    with one UNMAPPABLE parent classifies as unmappable even though registering its
    other parent would place it.
    """
    if source_system.mesh_collection_id or source_system.table_dataset_id or source_system.annotation_collection_id:
        own = [edge for edge in edges if edge.input_id == source_system.pk]
        derivation = min(own, key=lambda edge: edge.pk) if own else None
        if derivation is not None and not is_traversable(derivation):
            return True

    def owner_dataset_id(system: "models.CoordinateSystem | None") -> int | None:
        if system is None:
            return None
        if system.intrinsic_of_id:
            return system.intrinsic_of_id
        if system.dataset_id:
            return system.dataset_id
        if system.lens_id:
            return system.lens.dataset_id
        if system.data_array_id:
            return system.data_array.dataset_id
        return None

    return any(not is_traversable(edge) and owner_dataset_id(edge.input) in lineage_ids for edge in edges if edge.input_id)


def _fk_dataset_id(system: "models.CoordinateSystem | None") -> int | None:
    """The dataset a system belongs to by its ownership FK -- no derivation-edge follow.

    The FK-only sibling of :func:`system_dataset`: a collection's own (mesh / table) system
    is anchored to a dataset by an *edge*, not an FK, so this returns None for it. That is
    the wanted behaviour for the lens key -- a lens always lives on a dataset-owned system --
    and it keeps the batch a pure in-memory read over the already-fetched FKs.
    """
    if system is None:
        return None
    if system.intrinsic_of_id:
        return system.intrinsic_of_id
    if system.dataset_id:
        return system.dataset_id
    if system.lens_id:
        return system.lens.dataset_id
    if system.data_array_id:
        return system.data_array.dataset_id
    return None


def _derivation_descendants(dataset_ids: set[int]) -> set[int]:
    """Every dataset the fact tree hangs below one of these -- primary derivations only.

    The dual of :func:`lineage_ancestors`, which walks the primary chain *up* from a
    candidate; this walks it *down* from a registered source to everything it places. A
    child descends from its **primary** parent only: a fusion whose primary is elsewhere
    is not placed by its secondary, however real that edge is as history. And it stops at
    an UNMAPPABLE primary for the same reason lineage does: a derivation whose geometry
    did not survive places nothing downstream.

    Two bounded queries per generation: one finds the candidate children (any derivation
    edge landing in the frontier), one fetches the candidates' own derivation edges so the
    primary -- the first cross-dataset edge by the creator's declared (pk) order, exactly
    :func:`primary_derivation_edge`'s rule -- is decided in memory, never per child.
    """
    descendants: set[int] = set()
    frontier = set(dataset_ids)
    seen = set(dataset_ids)

    while frontier:
        edges = (
            models.Transformation.objects.filter(parent__isnull=True)
            .filter(
                Q(output__intrinsic_of__in=frontier)
                | Q(output__dataset__in=frontier)
                | Q(output__lens__dataset__in=frontier)
                | Q(output__data_array__dataset__in=frontier)
            )
            .select_related("input", "input__lens", "input__data_array", "output", "output__lens", "output__data_array")
        )
        candidates: set[int] = set()
        for edge in edges:
            child = _fk_dataset_id(edge.input)
            parent = _fk_dataset_id(edge.output)
            # A same-dataset edge (a lens, level or calibration edge) is not a derivation;
            # only a cross-dataset one carries placement downstream.
            if child is None or parent is None or child == parent or child in seen:
                continue
            candidates.add(child)

        next_frontier: set[int] = set()
        if candidates:
            out_edges = (
                models.Transformation.objects.filter(parent__isnull=True, input__intrinsic_of__in=candidates)
                .select_related("input", "output", "output__lens", "output__data_array")
                .order_by("pk")
            )
            primary: dict[int, models.Transformation] = {}
            for edge in out_edges:
                child = _fk_dataset_id(edge.input)
                parent = _fk_dataset_id(edge.output)
                if child is None or parent is None or child == parent:
                    continue
                primary.setdefault(child, edge)
            for child, edge in primary.items():
                if child in seen or not is_traversable(edge):
                    continue
                if _fk_dataset_id(edge.output) in seen:
                    seen.add(child)
                    descendants.add(child)
                    next_frontier.add(child)
        frontier = next_frontier

    return descendants


def placeable_system_ids(scene: "models.Scene") -> set[int]:
    """The ids of every coordinate system with a traversable path to the scene's world.

    The batched dual of :func:`is_placeable_in_scene`: rather than ask "can *this* source
    reach world", it computes the whole set that can, in a bounded fetch and one walk, so a
    filter over thousands of candidates costs a constant number of queries instead of one BFS
    each. It shares the fact-tree rule and the traversal predicates with the single-source
    path, so the two never disagree -- a candidate is in this set exactly when
    ``is_placeable_in_scene`` says yes (pinned by ``tests/test_placeable_in_filter.py``).

    The universe is the world's registrations -- a property of the *space*, shared by every
    scene over it (RFC-6) -- closed over the datasets they anchor and those datasets'
    primary-derivation *descendants* (a derived dataset is placed through its primary
    parent's registration), plus the collection edges landing in any anchored dataset (a
    mesh or table reaches world through the image it was extracted from). Reachability is
    then a single reverse walk from world over that universe: every node from which world
    is reachable.
    """
    world = scene.world
    if world is None:
        return set()

    registrations = list(
        models.Transformation.objects.filter(parent__isnull=True, output=world)
        .select_related("input", "input__lens", "input__data_array", "output")
        .prefetch_related("children", "input__axes", "output__axes")
    )

    # The datasets the world's registrations anchor, and everything derived from them.
    seeds = {dataset.pk for edge in registrations if edge.input and is_traversable(edge) and (dataset := system_dataset(edge.input))}
    # An owned world (a scene rooted at a dataset's intrinsic pixels or a calibration)
    # anchors its own container with no registration at all: the data is in its own
    # space by construction, so the container seeds the set directly. A collection
    # world seeds the dataset it was extracted from only across a *traversable*
    # derivation -- an UNMAPPABLE one places nothing, and seeding through it would
    # make this set disagree with `is_placeable_in_scene`.
    world_dataset_id = _fk_dataset_id(world)
    if world_dataset_id is None and (world.mesh_collection_id or world.table_dataset_id or world.annotation_collection_id):
        derivation = collection_derivation_edge(world)
        if derivation is not None and derivation.output is not None and is_traversable(derivation):
            source = system_dataset(derivation.output)
            world_dataset_id = source.pk if source else None
    if world_dataset_id is not None:
        seeds.add(world_dataset_id)
    dataset_ids = seeds | _derivation_descendants(seeds)

    # Edges *into* an anchored dataset as well as *out of* one: the out-edges carry a
    # dataset's own facts (its lenses, levels, calibrations) and its descendants'; the
    # in-edges carry a collection's derivation (a mesh or table system -> the image's
    # intrinsic), the one edge a registered image's own bucket would otherwise miss.
    edges = list(
        models.Transformation.objects.filter(parent__isnull=True)
        .filter(
            Q(input__intrinsic_of__in=dataset_ids)
            | Q(input__dataset__in=dataset_ids)
            | Q(input__lens__dataset__in=dataset_ids)
            | Q(input__data_array__dataset__in=dataset_ids)
            | Q(output__intrinsic_of__in=dataset_ids)
            | Q(output__dataset__in=dataset_ids)
            | Q(output__lens__dataset__in=dataset_ids)
            | Q(output__data_array__dataset__in=dataset_ids)
            | Q(input=world)
            | Q(output=world)
        )
        .distinct()
        .select_related("input", "input__lens", "input__data_array", "output")
        .prefetch_related("children", "input__axes", "output__axes")
    )

    # The walkable universe: the fact tree, plus this world's own claims. A claim into
    # any *other* shared space stays out -- a placement crosses exactly one registration,
    # and it is this world's.
    walkable = fact_edges(edges) + [edge for edge in edges if edge.output_id == world.pk]
    adjacency = adjacency_of(walkable)

    # Reverse the adjacency and walk out from world: a node is placeable exactly when world
    # is reachable *from* it, which is world reaching it in the reversed graph.
    reverse: dict[int, list[int]] = {}
    for node, steps in adjacency.items():
        for _edge, _inverted, neighbor in steps:
            reverse.setdefault(neighbor, []).append(node)

    reachable = {world.pk}
    frontier = [world.pk]
    while frontier:
        next_frontier: list[int] = []
        for node in frontier:
            for previous in reverse.get(node, ()):
                if previous not in reachable:
                    reachable.add(previous)
                    next_frontier.append(previous)
        frontier = next_frontier

    return reachable


def _placeable_systems(scene: "models.Scene") -> list["models.CoordinateSystem"]:
    """The placeable coordinate systems as rows, with the owner FKs the id keys read."""
    return list(
        models.CoordinateSystem.objects.filter(pk__in=placeable_system_ids(scene)).select_related(
            "intrinsic_of", "dataset", "lens__dataset", "data_array__dataset", "table_dataset"
        )
    )


def placeable_lens_dataset_ids(scene: "models.Scene") -> set[int]:
    """The datasets every one of whose lenses is placeable in the scene.

    Placeability is a property of the *dataset*, not the individual lens: an unsliced lens'
    space is the intrinsic system, a sliced lens' system reaches it across a crop/scale, and
    a calibration-anchored dataset reaches world through its PHYSICAL system -- so if any of a
    dataset's systems reaches world, every lens of it does. Keying on ``dataset_id`` is
    therefore both correct and indexed, and needs no ``distinct()``.
    """
    return {dataset_id for system in _placeable_systems(scene) if (dataset_id := _fk_dataset_id(system)) is not None}


def placeable_table_dataset_ids(scene: "models.Scene") -> set[int]:
    """The table datasets whose own coordinate system is placeable in the scene.

    A table owns its system one-to-one, so there is no dataset reduction as there is for a
    lens: the placeable table datasets are exactly those whose system is in the placeable set.
    """
    return {system.table_dataset_id for system in _placeable_systems(scene) if system.table_dataset_id}


def scenes_by_sole_dataset(scenes: "Iterable[models.Scene]") -> dict[int, list["models.Scene"]]:
    """Each dataset id, mapped to the scenes whose *only* placed dataset it is.

    Sole occupancy is what lets a picture of a *composition* stand in as a preview of one
    dataset. A snapshot depicts a scene, so there is no picture of a dataset to fall back
    on -- but a scene holding only this dataset is a picture of it, while a scene blending
    five is a picture of none of them in particular and is offered for none. This is the
    whole basis of ``ADataset.latestSnapshot``.

    Two things it deliberately does not promise, both inherited from what "placed" means:

    * **Placed, not drawn.** A dataset registered into a scene's world but never layered
      is still that scene's only placed dataset -- and the scene's picture is empty. Sole
      occupancy narrows the frame; it does not guarantee anything is in it.
    * **Datasets only.** Mesh collections and table datasets are not counted, so a scene
      may still draw tracks or surfaces over the one dataset. That is a picture of it
      *with annotations*, which is why they do not disqualify the scene.

    A map rather than a per-dataset predicate, because the cost lives per *scene*: each
    one walks the placement graph (a Transformation query, plus one per lineage hop). One
    pass answers for every dataset at once, so a list query resolving ``latestSnapshot``
    over a page of datasets pays once per scene instead of once per scene per row. The
    caller supplies ``scenes`` and must scope them to the request's organization -- never
    every scene in the table.

    Reuses :func:`placeable_lens_dataset_ids` rather than inverting the walk, so it cannot
    drift from what layer creation would accept.
    """
    by_dataset: dict[int, list[models.Scene]] = {}
    for scene in scenes:
        placed = placeable_lens_dataset_ids(scene)
        if len(placed) == 1:
            by_dataset.setdefault(next(iter(placed)), []).append(scene)
    return by_dataset


def adjacency_of(edges) -> dict[int, list[tuple["models.Transformation", bool, int]]]:
    """Build the BFS adjacency of an edge collection.

    Forwards, unless the edge says there is nothing to walk: an UNMAPPABLE edge relates
    two systems while declaring that no point of one corresponds to a point of the other,
    so a path across it would be composing a map out of a stated non-correspondence.
    Backwards only if the edge has an inverse to offer -- a rank-changing edge does not,
    and neither does a warp field at any rank.
    """
    adjacency: dict[int, list[tuple[models.Transformation, bool, int]]] = {}
    seen: set[int] = set()
    for edge in edges:
        if edge.pk in seen or not edge.input_id or not edge.output_id:
            continue
        seen.add(edge.pk)
        if is_traversable(edge):
            adjacency.setdefault(edge.input_id, []).append((edge, False, edge.output_id))
        if is_reverse_traversable(edge):
            adjacency.setdefault(edge.output_id, []).append((edge, True, edge.input_id))
    return adjacency


def create_identity_registration(
    *,
    input_system: "models.CoordinateSystem",
    world: "models.CoordinateSystem",
    shared: list[str],
    name: str,
    validity: str = enums.PlacementValidityChoices.UNKNOWN.value,
    ctx: CreationContext,
) -> "models.Transformation":
    """One identity placement edge on the named shared axes.

    A BY_DIMENSION wrapper around an IDENTITY child, because that is the only shape that
    can say "these axes correspond one-to-one, and I claim nothing about the rest" -- a
    square edge between systems of different rank cannot. Its one caller in the product
    is the scene bootstrap, which mirrors the staged dataset's axes into the world it
    creates: VALIDATED when the world mirrors a calibration (the identity is exact by
    construction), UNKNOWN when it mirrors bare pixels under default units (an assumed
    interpretation, and the badge a layer's derived validity surfaces).
    """
    _assert_one_claim_per_space(input_system, world)
    edge = models.Transformation.objects.create(
        kind=enums.TransformKindChoices.BY_DIMENSION.value,
        name=name,
        input=input_system,
        output=world,
        input_axes=shared,
        output_axes=shared,
        params={},
        validity=validity,
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
    return edge


def edges_from(system: "models.CoordinateSystem") -> list["models.Transformation"]:
    """The top-level edges leaving a coordinate system (excluding wrapper children)."""
    return list(models.Transformation.objects.filter(input=system, parent__isnull=True))


def traverse(
    root: "models.CoordinateSystem",
    *,
    organization: "Organization",
    max_depth: int | None = None,
) -> tuple[list["models.CoordinateSystem"], list["models.Transformation"]]:
    """The connected component around a coordinate system: every system it reaches, and every edge between them.

    Reachability here is **undirected**, and deliberately so. Direction is a fact about how an
    edge composes, not about what it touches: standing on a PHYSICAL system and asking what
    transforms relate to it, the answer plainly includes the calibration edge that points
    *into* it. Walking only forward would return the empty set for exactly the systems a user
    is most likely to start from. The edges come back with their true stored direction and
    their axis names, so a client can still tell what is invertible (`is_reverse_traversable`)
    and what is not -- which is the placement question, and a different one.

    This does not compose anything, and it is not scene-scoped. It hands back the subgraph;
    what to do with it is the client's, in keeping with the rest of this module.

    The walk is batched -- one query per level of the search rather than one per node -- so a
    graph of any width costs O(depth) queries, and the two closing queries fetch the systems
    with their axes and the edges with everything a `Transformation` selection can ask for.
    Without those the discovery query would be a per-edge N+1 the moment a client selected
    `inputAxes` or a SEQUENCE's `children`: this returns a list, and a plain list is invisible
    to the optimizer.
    """
    reached: set[int] = {root.pk}
    frontier: set[int] = {root.pk}
    depth = 0

    while frontier and (max_depth is None or depth < max_depth):
        # Only the endpoints matter for the walk, so do not drag whole rows through it.
        endpoints = models.Transformation.objects.filter(parent__isnull=True, organization=organization).filter(Q(input_id__in=frontier) | Q(output_id__in=frontier)).values_list("input_id", "output_id")

        discovered: set[int] = set()
        for input_id, output_id in endpoints:
            for endpoint_id in (input_id, output_id):
                # A cycle (a BIJECTION, or any loop) is a graph the walk must survive, not an
                # error: `reached` is what makes the search terminate.
                if endpoint_id is not None and endpoint_id not in reached:
                    reached.add(endpoint_id)
                    discovered.add(endpoint_id)

        frontier = discovered
        depth += 1

    systems = list(models.CoordinateSystem.objects.filter(pk__in=reached).prefetch_related("axes").order_by("pk"))

    # Both endpoints inside the component, so no edge dangles off a node that is not in
    # `systems` -- at a `maxDepth` cutoff the boundary edges are precisely the ones that
    # would.
    edges = list(
        models.Transformation.objects.filter(
            parent__isnull=True,
            organization=organization,
            input_id__in=reached,
            output_id__in=reached,
        )
        .select_related("input", "output", "parent")
        .prefetch_related("children", "input__axes", "output__axes", "parent__input__axes", "parent__output__axes")
        .order_by("pk")
    )

    return systems, edges


#: The SQL mirror of :func:`is_registration_target`, per edge side: a SHARED system is one
#: with every owner FK null (a scene-minted world sets only `scene`, which is not an owner
#: in this sense -- it is SHARED too). Used to keep a walk from ever *standing on* a shared
#: space: excluding only registration edges (fact -> SHARED) is not enough, because one
#: stray edge OUT of a hub would put the hub in the frontier and the next level would pull
#: in every dataset registered there.
_SHARED_SIDE_MIRROR: dict[str, bool] = {
    "intrinsic_of__isnull": True,
    "dataset__isnull": True,
    "data_array__isnull": True,
    "lens__isnull": True,
    "mesh_collection__isnull": True,
    "table_dataset__isnull": True,
}


def fact_paths(
    root: "models.CoordinateSystem",
    *,
    organization: "Organization",
    max_depth: int | None = None,
) -> dict[int, list[tuple["models.Transformation", bool]]]:
    """Every system fact-reachable from ``root``, each with its ``(edge, inverted)`` path.

    The scene-independent sibling of :func:`traverse`: the same batched frontier walk, but
    over the **fact component** only -- derivations, pyramid levels, lenses, calibrations --
    so a probe on a source image can find the instance mask derived from it. Three refusals
    define the component. Registrations are never crossed and a SHARED system is never even
    stood on (either side, see ``_SHARED_SIDE_MIRROR``): which claims compose is a scene's
    say-so, and this walk has no scene. UNMAPPABLE never walks, in either direction. And a
    FIELD edge is payload, not connectivity -- it is what a caller collects *at* the reached
    systems, and crossing it would put a table's index space in the frontier.

    Two phases. The frontier walk over-reaches on purpose (it knows endpoints, not
    primaries or invertibility); the second fetch pulls every edge *touching* the reached
    set -- one endpoint, deliberately, because an UNMAPPABLE primary's far side is
    unreached, and hiding that edge from :func:`fact_edges` would wrongly promote a later
    mappable edge to primary. `fact_edges` then drops non-primary cross-container edges,
    :func:`adjacency_of` refuses the untraversable directions, and a single BFS tree
    yields one deterministic shortest path per reached system. Nothing is composed: the
    steps come back in stored direction with the inversions flagged, exactly like
    ``pathToWorld``, and composing them is the client's job for the reason it always is.
    """
    reached: set[int] = {root.pk}
    frontier: set[int] = {root.pk}
    depth = 0

    while frontier and (max_depth is None or depth < max_depth):
        endpoints = (
            models.Transformation.objects.filter(parent__isnull=True, organization=organization)
            .filter(Q(input_id__in=frontier) | Q(output_id__in=frontier))
            .exclude(kind__in=[enums.TransformKindChoices.UNMAPPABLE.value, enums.TransformKindChoices.FIELD.value])
            .exclude(**{f"input__{lookup}": value for lookup, value in _SHARED_SIDE_MIRROR.items()})
            .exclude(**{f"output__{lookup}": value for lookup, value in _SHARED_SIDE_MIRROR.items()})
            .values_list("input_id", "output_id")
        )

        discovered: set[int] = set()
        for input_id, output_id in endpoints:
            for endpoint_id in (input_id, output_id):
                if endpoint_id is not None and endpoint_id not in reached:
                    reached.add(endpoint_id)
                    discovered.add(endpoint_id)

        frontier = discovered
        depth += 1

    edges = list(
        models.Transformation.objects.filter(parent__isnull=True, organization=organization)
        .filter(Q(input_id__in=reached) | Q(output_id__in=reached))
        .select_related("input", "output")
        .prefetch_related("children", "input__axes", "output__axes")
        .order_by("pk")
    )

    connectivity = fact_edges([edge for edge in edges if edge.kind != enums.TransformKindChoices.FIELD.value and not is_registration_target(edge.input)])
    parents = _bfs_tree(adjacency_of(connectivity), root.pk, max_depth=max_depth)

    return {pk: _steps_from_parents(parents, root.pk, pk) for pk in parents}


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
    # The FK, not the derived kind: a mesh collection's or table's native space is
    # INTRINSIC-kind too, but only `intrinsic_of` marks the dataset pixel grid this
    # walk terminates at -- a collection's space still has a derivation edge to cross.
    if system.intrinsic_of_id:
        return []

    dataset = system_dataset(system)

    chain: list[tuple[str, dict]] = []
    current = system
    seen: set[int] = set()

    while current and not current.intrinsic_of_id:
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
    whatever the database happens to return first. An edge nothing can be walked across
    is not a candidate: an UNMAPPABLE edge out of this system leads nowhere a coordinate
    can follow, and taking it would compose an ROI's box through a map that does not
    exist.
    """
    candidates = models.Transformation.objects.filter(input=system, parent__isnull=True).select_related("output", "output__lens", "output__data_array").order_by("pk")

    for edge in candidates:
        if edge.output is None or not is_traversable(edge):
            continue
        if dataset is None or system_dataset(edge.output) == dataset:
            return edge
    return None


def _edge_params(edge: "models.Transformation") -> tuple[str, dict]:
    """An edge as (kind, params), in the shape :func:`coords.to_matrix` expects.

    A SEQUENCE's children are flattened into one params dict. A MAP_AXIS's permutation is
    written out as an `affine`: it lives in the `input_axes` / `output_axes` *columns*,
    which `to_matrix` never sees, so composing it any other way would mean threading two
    more arguments through every caller for the one kind that needs them.
    """
    if edge.kind == enums.TransformKindChoices.MAP_AXIS.value:
        axis_order = [axis.name for axis in edge.input.axes.all()] if edge.input else []
        return edge.kind, {"affine": coords_logic.permutation_matrix(edge.input_axes or [], edge.output_axes or [], axis_order)}

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
    dataset = system_dataset(system)
    seen: set[int] = set()

    while current and not current.intrinsic_of_id:
        if current.pk in seen:
            break
        seen.add(current.pk)
        # The same walk `path_to_intrinsic` takes, and it must be the *same* walk: this
        # used to take the first edge out of the system by no particular rule, so it
        # could count a registration's version while the chain it claims to describe
        # went somewhere else entirely.
        edge = _edge_towards_intrinsic(current, dataset)
        if edge is None:
            break
        total += edge.version
        current = edge.output

    return total


def intrinsic_chain(system: "models.CoordinateSystem") -> list:
    """The resolved edge chain from a system down to intrinsic space, or [] when none exists.

    Resolving the chain is the per-*system* half of a bbox computation; a bulk write
    of many shapes into one system resolves it once and applies it per shape.
    """
    try:
        return path_to_intrinsic(system)
    except ValueError:
        # A PHYSICAL, WORLD or ATLAS system has no path down to a pixel space
        # (calibration edges point away from intrinsic). A box is still
        # meaningful in the system's own coordinates.
        return []


def bbox_along_chain(chain: list, vectors: list[list[float]]) -> dict | None:
    """The bounding box of one shape's geometry, pushed along an already-resolved chain.

    Pushes **every corner** of the box, not just the two extremes. An
    affine-transformed AABB is not an AABB: under any rotation or shear, taking
    only min and max through the matrix yields a box that is strictly too small, so
    geometry that really is inside it tests as outside.
    """
    if not vectors:
        return None
    low, high = coords_logic.vectors_bbox(vectors)
    return coords_logic.transformed_bbox(low, high, chain)


def compute_intrinsic_bbox(system: "models.CoordinateSystem", vectors: list[list[float]]) -> dict | None:
    """The bounding box of a shape's geometry, pushed into the nearest intrinsic space."""
    return bbox_along_chain(intrinsic_chain(system), vectors)


def lens_source_system(lens: "models.Lens") -> "models.CoordinateSystem | None":
    """The space a lens' data is expressed in.

    An unsliced lens owns no system: its space is the dataset's intrinsic space.
    """
    return getattr(lens, "coordinate_system", None) or lens.dataset.intrinsic_coordinate_system


def layer_source_system(layer: "models.Layer") -> "models.CoordinateSystem | None":
    """The coordinate system a layer's data is expressed in, per kind.

    An image layer's data lives in its lens' space, an annotation layer's in its
    collection's drawing space, a mesh layer's in its collection's, and a
    point/track layer's in the space of the table dataset it draws from.
    """
    if layer.kind == enums.LayerKindChoices.IMAGE.value and layer.lens_id:
        return lens_source_system(layer.lens)
    if layer.kind == enums.LayerKindChoices.ANNOTATION.value and layer.annotation_collection_id:
        return getattr(layer.annotation_collection, "coordinate_system", None)
    if layer.kind == enums.LayerKindChoices.MESH.value and layer.mesh_collection_id:
        # A reverse one-to-one now, since the collection owns its system: Django raises
        # (an AttributeError subclass) rather than returning None when there is none.
        return getattr(layer.mesh_collection, "coordinate_system", None)
    if layer.kind in (enums.LayerKindChoices.POINT.value, enums.LayerKindChoices.TRACK.value) and layer.table_dataset_id:
        # The table dataset owns its space, the same way a mesh collection does.
        return getattr(layer.table_dataset, "coordinate_system", None)
    return None


def system_dataset(system: "models.CoordinateSystem") -> "models.ADataset | None":
    """The dataset a coordinate system belongs to, whichever owner it hangs off.

    A collection or table dataset's system belongs to no dataset *directly* -- a mesh
    collection, a feature table and a table dataset own their spaces -- so the dataset is
    the one its derivation edge lands in. That indirection is the price of owning the
    system, and it is what keeps a mesh or point layer bucketed with the dataset its data
    was extracted from, which is what lets the placement search find its way to world.

    Following the derivation edge regardless of kind is deliberate: for a measurement table
    the edge is UNMAPPABLE, so this still answers "that image", and the *walk* is what
    refuses to cross it. Bucketing is the scope of a search, not a claim about geometry;
    keeping the edge inside the scope is what lets the gate be the thing that says no.
    """
    if system.intrinsic_of_id:
        return system.intrinsic_of
    if system.dataset_id:
        return system.dataset
    if system.lens_id:
        return system.lens.dataset
    if system.data_array_id:
        return system.data_array.dataset
    if system.mesh_collection_id or system.table_dataset_id or system.annotation_collection_id:
        return collection_source_dataset(system)
    return None


def collection_derivation_edge(system: "models.CoordinateSystem") -> "models.Transformation | None":
    """The edge relating a collection's own system to the data it was derived from.

    Optional by design: a mesh in some absolute space, belonging to no dataset, has none,
    and that is a freestanding collection rather than an error.
    """
    return models.Transformation.objects.filter(input=system, parent__isnull=True).select_related("output", "output__lens", "output__data_array").order_by("pk").first()


def collection_source_dataset(system: "models.CoordinateSystem") -> "models.ADataset | None":
    """The dataset a collection's system was derived from, or None if it is freestanding."""
    edge = collection_derivation_edge(system)
    if edge is None or edge.output is None:
        return None
    return system_dataset(edge.output)


def _bfs_tree(
    adjacency: dict[int, list[tuple["models.Transformation", bool, int]]],
    source_pk: int,
    *,
    max_depth: int | None = None,
    target_pk: int | None = None,
) -> dict[int, tuple[int, "models.Transformation", bool] | None]:
    """The BFS parents map from a source: node -> (previous node, edge, inverted).

    Expands edges in pk order so ties between equal-length paths resolve
    deterministically rather than by dict iteration luck. Stops early when the
    optional target is reached, or when the optional depth cap is hit.
    """
    parents: dict[int, tuple[int, "models.Transformation", bool] | None] = {source_pk: None}
    frontier = [source_pk]
    depth = 0
    while frontier and (max_depth is None or depth < max_depth) and (target_pk is None or target_pk not in parents):
        next_frontier: list[int] = []
        for node in frontier:
            for edge, inverted, neighbor in sorted(adjacency.get(node, []), key=lambda step: step[0].pk):
                if neighbor in parents:
                    continue
                parents[neighbor] = (node, edge, inverted)
                next_frontier.append(neighbor)
        frontier = next_frontier
        depth += 1
    return parents


def _steps_from_parents(
    parents: dict[int, tuple[int, "models.Transformation", bool] | None],
    source_pk: int,
    node: int,
) -> list[tuple["models.Transformation", bool]]:
    """Read the (edge, inverted) steps source -> node back out of a BFS parents map."""
    steps: list[tuple["models.Transformation", bool]] = []
    while node != source_pk:
        previous, edge, inverted = parents[node]
        steps.append((edge, inverted))
        node = previous
    return list(reversed(steps))


def _bfs_path(
    adjacency: dict[int, list[tuple["models.Transformation", bool, int]]],
    source_pk: int,
    target_pk: int,
) -> list[tuple["models.Transformation", bool]] | None:
    """The shortest path of (edge, inverted) steps from source to target, or None."""
    if source_pk == target_pk:
        return []

    parents = _bfs_tree(adjacency, source_pk, target_pk=target_pk)
    if target_pk not in parents:
        return None
    return _steps_from_parents(parents, source_pk, target_pk)


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

    A "to world" question has a single right answer by construction now: the fact
    tree gives the source one chain, and the registration into the world is unique
    per data-tree (one truth per space), so there is nothing for the search to
    choose. The server still does not *compose*: it returns the edges (with their
    versions, their kinds, their provenance) and the client multiplies, exactly as
    it would after walking the graph itself.

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
