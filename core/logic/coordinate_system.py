"""Creating a hub coordinate system and the edges that register sources into it.

A hub is the one coordinate system with no owner (see :mod:`core.models.coords`): a
shared reference space (an atlas) that datasets, tables and mesh collections are
registered into, and that a scene later mirrors into its world. This is where those
registration edges are authored -- explicitly, exactly as ``createTransformation``
authors one, never fabricated. :func:`core.logic.scene.bootstrap_scene_from_system`
only *reads* them.
"""

import datetime
from collections.abc import Sequence

from django.db import transaction

from core import models
from core.creation import CreationContext
from core.logic import graph as graph_logic


def create_coordinate_system(
    *,
    name: str,
    axes: list,
    epoch: datetime.datetime | None = None,
    registrations: Sequence[tuple["models.CoordinateSystem", "models.ZarrStore | None", object]] = (),
    ctx: CreationContext,
) -> "models.CoordinateSystem":
    """Create a hub coordinate system, and author one edge per registered source into it.

    A hub is created with no owner FK at all, which is exactly what *makes* it a hub
    (SHARED kind, ``is_hub``): there is no kind to pass because ownership decides it.

    ``registrations`` are ``(source_system, field, spec)`` triples the caller has already
    resolved and scoped; ``spec`` carries the edge kind and parameters. Every edge points
    source -> hub, the direction a placement path walks, and is validated by the same
    :func:`~core.logic.graph.build_registration_edge` the transformation mutation uses.
    """
    with transaction.atomic():
        system = models.CoordinateSystem.objects.create(
            name=name,
            epoch=epoch,
            creator=ctx.user,
            organization=ctx.organization,
        )
        graph_logic.create_calibrated_axes(system, axes)

        for source_system, field, spec in registrations:
            graph_logic.build_registration_edge(
                input_system=source_system,
                output_system=system,
                kind=spec.kind,
                name=spec.name,
                scale=spec.scale,
                translation=spec.translation,
                affine=spec.affine,
                input_axes=spec.input_axes,
                output_axes=spec.output_axes,
                field=field,
                reason=spec.reason,
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
