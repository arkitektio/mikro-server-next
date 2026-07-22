"""Mutations for the lifecycle of a hub coordinate system.

A hub is the one coordinate system with no owner: a SHARED reference space (an atlas)
built to be registered into and later mirrored into a scene's world by
``createSceneFromCoordinateSystem``. ``createCoordinateSystem`` is the door those
registration edges are authored through -- explicitly, like ``createTransformation``,
never fabricated. There is no kind to choose: every other system is owned by a container
and created with it, so the one thing that mutation can create is a hub.

Being ownerless is also why the hub is the only system with a *lifecycle* here. Every
other system cascades with its container, and the container's own mutations are where it
is named and deleted; a hub answers to nobody, so without ``deleteCoordinateSystem`` and
``updateCoordinateSystem`` a mistyped atlas would outlive every dataset in it. Both are
refused on an owned system for that same reason: an owned system's name is its
container's business, and deleting one would take that container's spatial graph with it.
"""

import datetime

from django.db.models import Q
from kante.types import Info
import strawberry
from pydantic import BaseModel, Field

import kante
from core import models, types
from core.creation import CreationContext
from core.inputs.coords import (
    CalibratedAxisInput,
    CalibratedAxisInputModel,
    RegistrationPathInput,
    RegistrationPathInputModel,
)
from core.logic import coordinate_system as coordinate_system_logic
from core.mutations._generic import assert_can_delete, creator_owner
from core.scoping import get_for_org


class CreateCoordinateSystemInputModel(BaseModel):
    name: str
    axes: list[CalibratedAxisInputModel]
    epoch: datetime.datetime | None = None
    registrations: list[RegistrationPathInputModel] = []


@kante.pydantic_input(
    CreateCoordinateSystemInputModel,
    description="Create a hub coordinate system -- a SHARED reference space with no owner, e.g. an atlas -- and, in the same call, author the edges registering any number of sources (datasets, table datasets, mesh collections, coordinate systems) into it. Every other system is owned by a container and created with it, so a hub is the only system created directly. createSceneFromCoordinateSystem later mirrors the hub into a scene and materializes those sources as layers",
)
class CreateCoordinateSystemInput:
    """Input for creating a hub coordinate system and registering sources into it."""

    name: str = strawberry.field(description="The name of the hub coordinate system")
    axes: list[CalibratedAxisInput] = strawberry.field(description="The hub's axes, with their physical units. Sources registered into it are mapped onto these axes")
    epoch: datetime.datetime | None = strawberry.field(default=None, description="Optional wall-clock instant the hub's time axis has its origin at, so `wall_clock = epoch + t * unit`")
    registrations: list[RegistrationPathInput] = strawberry.field(default_factory=list, description="The sources to register into the hub, each with the edge that places it. Each edge points from the source's own coordinate system to the hub")


def create_coordinate_system(info: Info, input: CreateCoordinateSystemInput) -> types.CoordinateSystem:
    """Create a hub coordinate system and author one edge per registered source into it."""
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


def _assert_is_hub(system: "models.CoordinateSystem", verb: str) -> None:
    """Raise unless ``system`` is an ownerless hub.

    The ownership properties, never the derived ``kind``: ``kind`` reports SHARED for a
    scene's minted world too, and that one cascades with its scene -- renaming or deleting
    it here would reach past the hub these mutations are for.
    """
    if not system.is_hub:
        raise ValueError(f"Coordinate system {system.pk} is {system.kind.value} and owned by a container, so it cannot be {verb} directly. Only a hub -- an ownerless shared space -- has a lifecycle of its own; every other system is named and removed by its owner.")


class UpdateCoordinateSystemInputModel(BaseModel):
    id: str
    name: str | None = None
    epoch: datetime.datetime | None = None


@kante.pydantic_input(
    UpdateCoordinateSystemInputModel,
    description="Input for renaming a hub coordinate system or anchoring its clock. Hubs only: every other system is named by the container that owns it",
)
class UpdateCoordinateSystemInput:
    """Input for updating a hub coordinate system."""

    id: strawberry.ID = strawberry.field(description="The ID of the hub coordinate system to update")
    name: str | None = strawberry.field(default=None, description="A new name for the hub")
    epoch: datetime.datetime | None = strawberry.field(default=None, description="A new wall-clock instant for the hub's time axis to have its origin at, so `wall_clock = epoch + t * unit`")


def update_coordinate_system(info: Info, input: UpdateCoordinateSystemInput) -> types.CoordinateSystem:
    """Rename a hub or anchor its clock.

    Only the two fields that are the *space's* own description. Its axes are not here:
    ``Axis.order`` is written by enumeration and the rest of the graph is measured against
    it, so an axis edit is a different space -- make a new hub. And nothing about where
    data *sits* is here either: that is an edge, and refining one is
    ``updateTransformation``.
    """
    model = input.to_pydantic()

    system = get_for_org(models.CoordinateSystem, info, id=model.id)
    _assert_is_hub(system, "updated")

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
    id: str = Field(description="The ID of the hub coordinate system to delete")


@kante.pydantic_input(DeleteCoordinateSystemInputModel, description="Input for deleting a hub coordinate system by ID")
class DeleteCoordinateSystemInput:
    """Input for deleting a hub coordinate system by ID."""

    id: strawberry.ID = strawberry.field(description="The ID of the hub coordinate system to delete")


def delete_coordinate_system(info: Info, input: DeleteCoordinateSystemInput) -> strawberry.ID:
    """Delete an unused hub. Only hubs can be deleted this way, and only empty ones.

    A guarded, explicit delete rather than a generic one, for the reason
    ``delete_calibration`` gives: a generic delete on CoordinateSystem could reach an
    intrinsic system and take a dataset's whole spatial graph with it.

    Every refusal below guards a CASCADE that would otherwise take something the caller
    did not name -- the edges registered into the hub. This is a door for the atlas
    created by mistake, not a way to unpick a populated one: remove what is in it first,
    deliberately, one `deleteTransformation` at a time. Annotations need no guard of
    their own: they live in their collection's system, and a registered collection is
    already caught by the edge refusal.
    """
    model = input.to_pydantic()

    system = get_for_org(models.CoordinateSystem, info, id=model.id)
    _assert_is_hub(system, "deleted")

    # Scene.world is RESTRICT, so the database would refuse this anyway -- but it would
    # refuse with an IntegrityError naming a constraint, and this names the scenes.
    scenes = list(system.scenes.all()[:5])
    if scenes:
        raise ValueError(f"Coordinate system {system.pk} is the world of {len(scenes)} scene(s) ({', '.join(str(scene.pk) for scene in scenes)}) and cannot be deleted. A hub outlives the scenes that adopt it; delete them first.")

    # Both directions: an edge *into* the hub is a registration of some data-tree, and one
    # *out of* it registers the hub itself into a wider space. Transformation.input and
    # .output are both CASCADE, so either would vanish silently.
    edges = models.Transformation.objects.filter(Q(input=system) | Q(output=system), parent__isnull=True).count()
    if edges:
        raise ValueError(f"Coordinate system {system.pk} has {edges} transformation edge(s) and cannot be deleted: deleting it would delete them, and each is a registration someone authored. Delete them with deleteTransformation first.")

    assert_can_delete(info, system, creator_owner)
    system.delete()
    return model.id
