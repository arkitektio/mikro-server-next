"""Mutations for the lifecycle of a SHARED coordinate system.

A SHARED system is the one coordinate system with no owner: a reference space (a world,
an atlas) built to be registered into and later adopted as a scene's world by
``createSceneFromCoordinateSystem``. ``createCoordinateSystem`` is the door those
registration edges are authored through -- explicitly, like ``createTransformation``,
never fabricated. There is no kind to choose: every other system is owned by a container
and created with it, so the one thing that mutation can create is a shared space.

Being ownerless is also why a shared space is the only system with a *lifecycle* here.
Every other system cascades with its container, and the container's own mutations are
where it is named and deleted; a shared space answers to nobody -- scenes adopt it but
never own it, and no scene's deletion touches it -- so without
``deleteCoordinateSystem`` and ``updateCoordinateSystem`` a mistyped atlas would outlive
every dataset in it. Both are refused on an owned system for that same reason: an owned
system's name is its container's business, and deleting one would take that container's
spatial graph with it.
"""

import datetime

from django.db.models import Exists, OuterRef, Q
from kante.types import Info
import strawberry
from pydantic import BaseModel, Field

import kante
from core import enums, models, types
from core.creation import CreationContext
from core.inputs.coords import (
    CalibratedAxisInput,
    CalibratedAxisInputModel,
    RegistrationPathInput,
    RegistrationPathInputModel,
)
from core.logic import coordinate_system as coordinate_system_logic
from core.mutations._generic import assert_can_delete, creator_owner, user_is_org_admin
from core.scoping import for_org, get_for_org


class CreateCoordinateSystemInputModel(BaseModel):
    name: str
    axes: list[CalibratedAxisInputModel]
    epoch: datetime.datetime | None = None
    registrations: list[RegistrationPathInputModel] = []


@kante.pydantic_input(
    CreateCoordinateSystemInputModel,
    description="Create a SHARED coordinate system -- a reference space with no owner, e.g. a world or an atlas -- and, in the same call, author the edges registering any number of sources (datasets, table datasets, mesh collections, coordinate systems) into it. Every other system is owned by a container and created with it, so a shared space is the only system created directly. createSceneFromCoordinateSystem later builds a scene over it and materializes those sources as layers",
)
class CreateCoordinateSystemInput:
    """Input for creating a shared coordinate system and registering sources into it."""

    name: str = strawberry.field(description="The name of the shared coordinate system")
    axes: list[CalibratedAxisInput] = strawberry.field(description="The space's axes, with their physical units. Sources registered into it are mapped onto these axes")
    epoch: datetime.datetime | None = strawberry.field(default=None, description="Optional wall-clock instant the space's time axis has its origin at, so `wall_clock = epoch + t * unit`")
    registrations: list[RegistrationPathInput] = strawberry.field(default_factory=list, description="The sources to register into the space, each with the edge that places it. Each edge points from the source's own coordinate system to the shared space")


def create_coordinate_system(info: Info, input: CreateCoordinateSystemInput) -> types.CoordinateSystem:
    """Create a shared coordinate system and author one edge per registered source into it."""
    model = input.to_pydantic()

    ctx = CreationContext.from_info(info)

    resolved: list[tuple[models.CoordinateSystem, models.ZarrStore | None, object]] = []
    for spec in model.registrations:
        source_system = coordinate_system_logic.resolve_source_system(
            dataset=get_for_org(models.ADataset, info, id=spec.dataset) if spec.dataset else None,
            table_dataset=get_for_org(models.TableDataset, info, id=spec.table_dataset) if spec.table_dataset else None,
            mesh_collection=get_for_org(models.MeshCollection, info, id=spec.mesh_collection) if spec.mesh_collection else None,
            annotation_collection=get_for_org(models.AnnotationCollection, info, id=spec.annotation_collection) if spec.annotation_collection else None,
            coordinate_system=get_for_org(models.CoordinateSystem, info, id=spec.coordinate_system) if spec.coordinate_system else None,
        )
        field = get_for_org(models.CoordinateSystem, info, id=spec.field) if spec.field else None
        resolved.append((source_system, field, spec))

    return coordinate_system_logic.create_coordinate_system(
        name=model.name,
        axes=model.axes,
        epoch=model.epoch,
        registrations=resolved,
        ctx=ctx,
    )


def _assert_shared(system: "models.CoordinateSystem", verb: str) -> None:
    """Raise unless ``system`` is an ownerless SHARED space.

    ``kind`` falls through to SHARED exactly when no owner FK is set, so the derived
    kind is the ownership check.
    """
    if system.kind != enums.CoordinateSystemKind.SHARED:
        raise ValueError(f"Coordinate system {system.pk} is {system.kind.value} and owned by a container, so it cannot be {verb} directly. Only a shared space -- an ownerless system -- has a lifecycle of its own; every other system is named and removed by its owner.")


class UpdateCoordinateSystemInputModel(BaseModel):
    id: str
    name: str | None = None
    epoch: datetime.datetime | None = None


@kante.pydantic_input(
    UpdateCoordinateSystemInputModel,
    description="Input for renaming a shared coordinate system or anchoring its clock. Shared spaces only: every other system is named by the container that owns it",
)
class UpdateCoordinateSystemInput:
    """Input for updating a shared coordinate system."""

    id: strawberry.ID = strawberry.field(description="The ID of the shared coordinate system to update")
    name: str | None = strawberry.field(default=None, description="A new name for the space")
    epoch: datetime.datetime | None = strawberry.field(default=None, description="A new wall-clock instant for the space's time axis to have its origin at, so `wall_clock = epoch + t * unit`")


def update_coordinate_system(info: Info, input: UpdateCoordinateSystemInput) -> types.CoordinateSystem:
    """Rename a shared space or anchor its clock.

    Only the two fields that are the *space's* own description. Its axes are not here:
    ``Axis.order`` is written by enumeration and the rest of the graph is measured against
    it, so an axis edit is a different space -- make a new one. And nothing about where
    data *sits* is here either: that is an edge, and refining one is
    ``updateTransformation``.
    """
    model = input.to_pydantic()

    system = get_for_org(models.CoordinateSystem, info, id=model.id)
    _assert_shared(system, "updated")

    if model.name is not None:
        system.name = model.name
    # Distinguishing "not supplied" from "explicitly cleared" would need a sentinel, and an
    # unanchored clock is the model's own default -- so re-anchoring is supported and
    # un-anchoring is not, rather than silently doing the wrong one of the two.
    if model.epoch is not None:
        system.epoch = model.epoch

    system.save(update_fields=["name", "epoch"])

    return system


class DeleteCoordinateSystemInputModel(BaseModel):
    id: str = Field(description="The ID of the shared coordinate system to delete")


@kante.pydantic_input(DeleteCoordinateSystemInputModel, description="Input for deleting a shared coordinate system by ID")
class DeleteCoordinateSystemInput:
    """Input for deleting a shared coordinate system by ID."""

    id: strawberry.ID = strawberry.field(description="The ID of the shared coordinate system to delete")


def delete_coordinate_system(info: Info, input: DeleteCoordinateSystemInput) -> strawberry.ID:
    """Delete an unused shared space. Only shared spaces can be deleted this way, and only empty ones.

    A guarded, explicit delete rather than a generic one, for the reason
    ``delete_calibration`` gives: a generic delete on CoordinateSystem could reach an
    intrinsic system and take a dataset's whole spatial graph with it.

    Every refusal below guards a CASCADE that would otherwise take something the caller
    did not name -- the edges registered into the space. This is a door for the atlas
    created by mistake, not a way to unpick a populated one: remove what is in it first,
    deliberately, one `deleteTransformation` at a time. Annotations need no guard of
    their own: they live in their collection's system, and a registered collection is
    already caught by the edge refusal.
    """
    model = input.to_pydantic()

    system = get_for_org(models.CoordinateSystem, info, id=model.id)
    _assert_shared(system, "deleted")

    # Scene.world is RESTRICT, so the database would refuse this anyway -- but it would
    # refuse with an IntegrityError naming a constraint, and this names the scenes.
    scenes = list(system.scenes.all()[:5])
    if scenes:
        raise ValueError(f"Coordinate system {system.pk} is the world of {len(scenes)} scene(s) ({', '.join(str(scene.pk) for scene in scenes)}) and cannot be deleted. A shared space outlives the scenes that adopt it; delete them first.")

    # Both directions: an edge *into* the space is a registration of some data-tree, and one
    # *out of* it registers the space itself into a wider one. Transformation.input and
    # .output are both CASCADE, so either would vanish silently.
    edges = models.Transformation.objects.filter(Q(input=system) | Q(output=system), parent__isnull=True).count()
    if edges:
        raise ValueError(f"Coordinate system {system.pk} has {edges} transformation edge(s) and cannot be deleted: deleting it would delete them, and each is a registration someone authored. Delete them with deleteTransformation first.")

    assert_can_delete(info, system, creator_owner)
    system.delete()
    return model.id


class ClearCoordinateSystemInputModel(BaseModel):
    id: str = Field(description="The ID of the shared coordinate system to clear")


@kante.pydantic_input(
    ClearCoordinateSystemInputModel,
    description="Input for clearing a shared coordinate system: delete every registration INTO it in one call, keeping the space, its scenes, and its own claims into wider spaces",
)
class ClearCoordinateSystemInput:
    """Input for clearing a shared coordinate system of its registrations."""

    id: strawberry.ID = strawberry.field(description="The ID of the shared coordinate system to clear")


def clear_coordinate_system(info: Info, input: ClearCoordinateSystemInput) -> list[strawberry.ID]:
    """Delete every registration into a shared space, returning the deleted edge ids.

    The bulk counterpart of one `deleteTransformation` per edge: it empties the space so
    it can be re-registered from scratch or handed to `deleteCoordinateSystem`. Only edges
    *into* the space go -- an edge *out of* it is the space's own claim into a wider one
    and stays, as do the scenes over the space (their layers drop to UNREGISTERED, the
    same degradation deleting a single registration causes).

    Clearing is the space-owner's act even when the edges have other authors: the guard
    runs against the *system's* creator, mirroring how deleting the space would take the
    same edges with it.
    """
    model = input.to_pydantic()

    system = get_for_org(models.CoordinateSystem, info, id=model.id)
    _assert_shared(system, "cleared")
    assert_can_delete(info, system, creator_owner)

    edges = models.Transformation.objects.filter(output=system, parent__isnull=True)
    deleted = [strawberry.ID(str(pk)) for pk in edges.values_list("pk", flat=True)]
    edges.delete()
    return deleted


def delete_orphaned_coordinate_systems(info: Info) -> list[strawberry.ID]:
    """Delete every orphaned shared space in the organization, returning the deleted ids.

    The sweep the never-GC deletion policy calls for: no scene deletion ever deletes a
    space, so ownerless SHARED systems that nothing points at anymore -- no scene rooted
    in them, no transformation edge touching them -- accumulate by design, and this is
    the one call that takes them all back. Exactly the systems `deleteCoordinateSystem`
    would delete one at a time, found instead of named.

    An org admin sweeps every orphan; anyone else sweeps only the orphans they created --
    a foreign orphan is *skipped*, not refused, because a sweep names nothing and so has
    nothing to fail on. Returns a list (possibly empty), unlike the single-ID deletes:
    the caller did not know the ids going in.
    """
    touched = models.Transformation.objects.filter(Q(input=OuterRef("pk")) | Q(output=OuterRef("pk")), parent__isnull=True)
    orphans = (
        for_org(models.CoordinateSystem, info)
        .filter(
            datasets__isnull=True,
            lenses__isnull=True,
            data_arrays__isnull=True,
            mesh_collections__isnull=True,
            table_datasets__isnull=True,
            annotation_collections__isnull=True,
            scenes__isnull=True,
        )
        .exclude(Exists(touched))
    )
    if not user_is_org_admin(info):
        orphans = orphans.filter(creator=info.context.request.user)

    deleted = [strawberry.ID(str(pk)) for pk in orphans.values_list("pk", flat=True)]
    models.CoordinateSystem.objects.filter(pk__in=deleted).delete()
    return deleted
