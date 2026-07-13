"""Mutations for mesh collections.

A collection is immutable and versioned: refining an extraction produces a new
version, it does not edit an old one. It resolves to a catalog URL and a schema,
and the client queries the Parquet directly -- there is deliberately no mutation
here that writes meshes one by one, and no field that reads them back that way.
"""

from kante.types import Info
import strawberry
from pydantic import BaseModel, Field

import kante
from core import models, scalars, types
from core.creation import CreationContext
from core.mutations._generic import make_delete, self_owner
from core.scoping import get_for_org


class CreateMeshCollectionInputModel(BaseModel):
    coordinate_system: str
    version: str
    spec_version: str
    catalog_url: str
    geometry_urls: list[str]
    grid: dict | None = None
    encoding: dict | None = None
    provenance_metadata: dict | None = None


@kante.pydantic_input(CreateMeshCollectionInputModel, description="Input for registering an immutable, versioned mesh collection against a coordinate system")
class CreateMeshCollectionInput:
    """Input for registering a mesh collection."""

    coordinate_system: strawberry.ID = strawberry.field(description="The coordinate system the mesh geometry is expressed in, e.g. that of the label array the meshes were extracted from")
    version: str = strawberry.field(description="The immutable version of this collection, e.g. 'v20260713-a3f9'. A refined extraction is a new version, never an edit to an old one")
    spec_version: str = strawberry.field(description="The version of the mesh encoding specification this collection conforms to")
    catalog_url: str = strawberry.field(description="The URL of the Parquet catalog describing the meshes. The client queries it directly (e.g. with DuckDB) rather than paginating rows through this API")
    geometry_urls: list[str] = strawberry.field(description="The URLs of the Parquet geometry shards")
    grid: scalars.Any | None = strawberry.field(default=None, description="The octree grid, e.g. {'cellSize': [64, 64, 64], 'levels': 5, 'sortKey': 'MORTON'}. cellSize is in VOXELS, so the octree aligns to the label grid rather than to an arbitrary physical box")
    encoding: scalars.Any | None = strawberry.field(default=None, description="The geometry encoding, e.g. {'positions': 'UINT16_QUANTIZED_PER_CELL', 'normals': 'OCT16', 'codec': 'MESHOPT'}")
    provenance_metadata: scalars.Any | None = strawberry.field(default=None, description="How this collection was produced: the extraction run, its parameters and its inputs")


def create_mesh_collection(info: Info, input: CreateMeshCollectionInput) -> types.MeshCollection:
    """Register an immutable, versioned mesh collection against a coordinate system."""
    model = input.to_pydantic()

    ctx = CreationContext.from_info(info)
    system = get_for_org(models.CoordinateSystem, info, id=model.coordinate_system)

    return models.MeshCollection.objects.create(
        coordinate_system=system,
        version=model.version,
        spec_version=model.spec_version,
        catalog_url=model.catalog_url,
        geometry_urls=model.geometry_urls,
        grid=model.grid or {},
        encoding=model.encoding or {},
        provenance_metadata=model.provenance_metadata or {},
        creator=ctx.user,
        organization=ctx.organization,
    )


class DeleteMeshCollectionInputModel(BaseModel):
    id: str = Field(description="The ID of the mesh collection to delete")


@kante.pydantic_input(DeleteMeshCollectionInputModel, description="Input for deleting a mesh collection by ID")
class DeleteMeshCollectionInput:
    """Input for deleting a mesh collection by ID."""

    id: strawberry.ID = strawberry.field(description="The ID of the mesh collection to delete")


delete_mesh_collection = make_delete(models.MeshCollection, DeleteMeshCollectionInput, owner=self_owner)
