"""Mutation for creating a hub coordinate system and registering sources into it.

A hub is the one coordinate system with no owner: a SHARED reference space (an atlas)
built to be registered into and later mirrored into a scene's world by
``createSceneFromCoordinateSystem``. This mutation is the door those registration edges are
authored through -- explicitly, like ``createTransformation``, never fabricated. There is
no kind to choose: every other system is owned by a container and created with it, so the
one thing this mutation can create is a hub.
"""

import datetime

from kante.types import Info
import strawberry
from pydantic import BaseModel

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
            coordinate_system=get_for_org(models.CoordinateSystem, info, id=spec.coordinate_system) if spec.coordinate_system else None,
        )
        store = get_for_org(models.ZarrStore, info, id=spec.store) if spec.store else None
        resolved.append((source_system, store, spec))

    return coordinate_system_logic.create_coordinate_system(
        name=model.name,
        axes=model.axes,
        epoch=model.epoch,
        registrations=resolved,
        ctx=ctx,
    )
