"""Creating coordinate systems: shared spaces, the edges into them, and a lens' own space.

A SHARED system is the one coordinate system with no owner (see
:mod:`core.models.coords`): a reference space (a world, an atlas) that datasets, tables
and mesh collections are registered into, and that scenes later adopt as their world.
This is where those registration edges are authored -- explicitly, exactly as
``createTransformation`` authors one, never fabricated.
:func:`core.logic.scene.bootstrap_scene_from_system` only *reads* them.

Everything here makes *spaces and edges*, and none of it takes a scene. That is the line
this module draws against :mod:`core.logic.scene`, which makes scenes and layers: a lens'
coordinate system is a fact about a dataset's spaces, answerable with no composition in
sight, and it lived in the scene module only because the scene bootstrap happened to be the
caller.
"""

import datetime
from collections.abc import Sequence

from django.db import transaction

from core import enums, models
from core.creation import CreationContext
from core.inputs.coords import IDENTITY_TRANSFORM, PhysicalAxisInputModel
from core.logic import coords as coords_logic
from core.logic import graph as graph_logic


def create_world_space(
    *,
    name: str,
    axes: list | None = None,
    epoch: datetime.datetime | None = None,
    ctx: CreationContext,
) -> "models.CoordinateSystem":
    """Mint an ownerless shared space with physical axes, for a scene to adopt.

    The convenience half of `createScene`: a client that passes no `coordinateSystem` gets
    one of these and a scene over it, which is the same pair of rows `createCoordinateSystem`
    followed by `createScene(coordinateSystem:)` produces. It is a *space* either way -- no
    scene owns it, it outlives every scene over it, and only `deleteCoordinateSystem` removes
    it -- which is why the minting lives here and not in the scene module.

    The epoch lands on this system, not on the scene adopting it: it is the origin of the
    *space's* time axis, and two compositions over one space cannot disagree about it.
    """
    axes = axes or DEFAULT_WORLD_AXES
    axis_specs = [coords_logic.AxisSpec(name=axis.name, type=axis.type.value) for axis in axes]
    coords_logic.assert_axis_type_order(axis_specs)

    with transaction.atomic():
        world = models.CoordinateSystem.objects.create(
            name=name,
            epoch=epoch,
            creator=ctx.user,
            organization=ctx.organization,
        )
        graph_logic.create_physical_axes(world, axes)
    return world


def create_coordinate_system(
    *,
    name: str,
    axes: list,
    epoch: datetime.datetime | None = None,
    registrations: Sequence[tuple["models.CoordinateSystem", "models.ZarrStore | None", object]] = (),
    ctx: CreationContext,
) -> "models.CoordinateSystem":
    """Create a shared coordinate system, and author one edge per registered source into it.

    It is created with no owner FK at all, which is exactly what *makes* it SHARED:
    there is no kind to pass because ownership decides it.

    ``registrations`` are ``(source_system, field, spec)`` triples the caller has already
    resolved and scoped; ``spec.transform`` carries the edge's kind and parameters as the
    flat union, or is None for the identity a source that is simply *in* the space states.
    Every edge points source -> space, the direction a placement path walks, and is
    validated by the same :func:`~core.logic.graph.build_registration_edge` the
    transformation mutation uses.
    """
    with transaction.atomic():
        system = models.CoordinateSystem.objects.create(
            name=name,
            epoch=epoch,
            creator=ctx.user,
            organization=ctx.organization,
        )
        graph_logic.create_physical_axes(system, axes)

        for source_system, field, spec in registrations:
            lowered = spec.transform.lower() if spec.transform else IDENTITY_TRANSFORM
            graph_logic.build_registration_edge(
                input_system=source_system,
                output_system=system,
                kind=lowered.kind,
                name=spec.name,
                scale=lowered.scale,
                translation=lowered.translation,
                affine=lowered.affine,
                input_axes=lowered.input_axes,
                output_axes=lowered.output_axes,
                field=field,
                reason=lowered.reason,
                validity=spec.validity,
                ctx=ctx,
            )

    return system


def resolve_source_system(
    *,
    dataset: "models.ADataset | None" = None,
    table_dataset: "models.TableDataset | None" = None,
    mesh_collection: "models.MeshCollection | None" = None,
    annotation_collection: "models.AnnotationCollection | None" = None,
    coordinate_system: "models.CoordinateSystem | None" = None,
) -> "models.CoordinateSystem":
    """The coordinate system a registration source is placed by, given the already-fetched owner.

    Exactly one owner must be non-null. A dataset is registered through its intrinsic pixel
    grid, a collection through the system it owns, a coordinate system directly.
    """
    provided = [value for value in (dataset, table_dataset, mesh_collection, annotation_collection, coordinate_system) if value is not None]
    if len(provided) != 1:
        raise ValueError("A registration must name exactly one source: a dataset, a table dataset, a mesh collection, an annotation collection, or a coordinate system.")

    if coordinate_system is not None:
        return coordinate_system

    if dataset is not None:
        system = dataset.intrinsic_coordinate_system
        if system is None:
            raise ValueError(f"Dataset '{dataset.name}' has no intrinsic coordinate system to register.")
        return system

    if table_dataset is not None:
        system = table_dataset.coordinate_system_or_none
        if system is None:
            raise ValueError(f"Table dataset '{table_dataset.name}' has no coordinate system to register.")
        return system

    if annotation_collection is not None:
        system = annotation_collection.coordinate_system_or_none
        if system is None:
            raise ValueError(f"Annotation collection '{annotation_collection.name}' has no coordinate system to register.")
        return system

    system = getattr(mesh_collection, "coordinate_system", None)
    if system is None:
        raise ValueError(f"Mesh collection '{mesh_collection.name}' has no coordinate system to register.")
    return system


# The scene's world space, when the caller does not author one. A scene is
# spatio-temporal by default: microscopy data is a timelapse more often than not, and
# a world with nowhere to put time forces every temporal dataset to either drop its t
# axis at the registration or invent a scene-specific convention for it.
#
# Time first, then z/y/x in array order: the RFC-5 type ordering
# (:func:`assert_axis_type_order`) requires it, and array order means the world
# composes with a dataset's intrinsic axes without a permutation.
#
# Seconds, not a frame index: world is a *calibrated* space, and `t` here is a
# duration from the space's origin. The world system's `epoch` anchors that origin to
# wall-clock when it is known.
DEFAULT_WORLD_AXES = [
    PhysicalAxisInputModel(name="t", type=enums.AxisType.TIME, unit="second"),
    PhysicalAxisInputModel(name="z", type=enums.AxisType.SPACE, unit="micrometer"),
    PhysicalAxisInputModel(name="y", type=enums.AxisType.SPACE, unit="micrometer"),
    PhysicalAxisInputModel(name="x", type=enums.AxisType.SPACE, unit="micrometer"),
]

#: The axis types a world has a slider for. A CHANNEL axis is something a layer
#: *samples* (each position its own render node), and a MICROTIME or SPECTRUM axis is
#: something a render node *reduces* -- neither is a place, so neither belongs to a
#: shared space two datasets are registered into.
NAVIGABLE_TYPES = (enums.AxisTypeChoices.TIME.value, enums.AxisTypeChoices.SPACE.value)

def create_lens(
    dataset: "models.ADataset",
    slices: list,
    ctx: CreationContext,
) -> "models.Lens":
    """Create a lens -- and, only if it slices, its coordinate system and the edge recording the shift.

    The lens' shape and axes are not written: they follow from the dataset and the
    slices, and a second copy could only drift from the first. The same rule decides
    whether it gets a coordinate system at all: an unsliced lens selects everything,
    so its space is the dataset's intrinsic space *by definition* -- materializing a
    second node for it, joined by an identity edge, would store nothing. Lenses are
    immutable, so the decision is final at creation.
    """
    intrinsic = dataset.intrinsic_coordinate_system
    if intrinsic is None:
        raise ValueError(f"Dataset {dataset.pk} has no intrinsic coordinate system")

    if dataset.data_arrays.order_by("level").first() is None:
        raise ValueError(f"Dataset {dataset.pk} has no level-0 data array to place the lens against")

    slice_models = [slice.model_dump() for slice in slices]
    sliced = any(slice_models)

    # An unsliced lens lives in the dataset's own grid -- it selects everything, so its space
    # *is* that space -- and points at the same node. Only a sliced one needs a space of its
    # own, and gets it before the lens so there is one write each.
    lens_system = intrinsic
    if sliced:
        lens_system = models.CoordinateSystem.objects.create(
            name=f"{dataset.name}/lens",
            creator=ctx.user,
            organization=ctx.organization,
        )

    lens = models.Lens.objects.create(
        dataset=dataset,
        coordinate_system=lens_system,
        slices=slice_models,
    )

    if not lens.slices_list:
        return lens

    # A lens sees the same axes as the array it slices; only the extent changes.
    graph_logic.create_pixel_axes(lens_system, dataset.axes)

    # Without this edge, slicing shifts voxel coordinates and nothing records the
    # shift: an ROI drawn on a cropped lens has no defined path back to its dataset.
    # The parent is the intrinsic system: it IS the level-0 voxel space.
    graph_logic.create_lens_edge(
        lens_system=lens_system,
        parent_system=intrinsic,
        dataset_axis_names=dataset.axis_names,
        slices=lens.slices_list,
        ctx=ctx,
    )

    return lens
