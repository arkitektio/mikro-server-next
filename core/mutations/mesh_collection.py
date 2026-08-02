"""Mutations for mesh collections.

A collection is immutable and versioned: refining an extraction produces a new
version, it does not edit an old one. Its Parquet goes through the datalayer like
every other Parquet object -- presigned upload, store id back -- so the client can
ask for an access grant and query it directly. There is deliberately no mutation
here that writes meshes one by one, and no field that reads them back that way.
"""

from django.db import transaction
from kante.types import Info
import strawberry
from pydantic import BaseModel, Field

import kante
from core import models, scalars, types
from core.creation import CreationContext
from core.input_unions import prose_errors
from core.inputs.coords import AxisInput, AxisInputModel, DerivedFromInput, DerivedFromSpec
from core.logic import coordinate_system as coordinate_system_logic
from core.logic import graph as graph_logic
from core.mutations._generic import make_delete, self_owner
from core.scoping import get_for_org


class CreateMeshCollectionInputModel(BaseModel):
    version: str
    spec_version: str
    catalog: str
    geometry: list[str] | None = None
    axes: list[AxisInputModel]
    derived_from: list[DerivedFromSpec] | None = None
    grid: dict | None = None
    encoding: dict | None = None
    provenance_metadata: dict | None = None



@prose_errors
@kante.pydantic_input(CreateMeshCollectionInputModel, description="Input for registering an immutable, versioned mesh collection. The collection gets a coordinate system of its own, and an edge relates it to the space the meshes were extracted from")
class CreateMeshCollectionInput:
    """Input for registering a mesh collection."""

    version: str = strawberry.field(description="The immutable version of this collection, e.g. 'v20260713-a3f9'. A refined extraction is a new version, never an edit to an old one")
    spec_version: str = strawberry.field(description="The version of the mesh encoding specification this collection conforms to")
    catalog: scalars.ParquetLike = strawberry.field(
        description="The uploaded Parquet store holding the catalog that describes the meshes. Upload it through the normal parquet path (requestParquetUpload) and pass the store id here; the client then reads it back with an access grant"
    )
    geometry: list[scalars.ParquetLike] | None = strawberry.field(default=None, description="The uploaded Parquet stores holding the geometry shards")
    axes: list[AxisInput] = strawberry.field(description="The axes of the collection's own coordinate system, in order. Required: the collection owns its space, and a derivation no longer implies an identity to copy axes across")
    derived_from: list[DerivedFromInput] | None = strawberry.field(
        default=None,
        description="What this mesh collection was computed from. One entry per source; the first is the primary parent. Each names its source and how this collection's own space relates to that source's: **omit the transform and the edge is UNMAPPABLE**, recording the lineage and claiming no geometry. State IDENTITY when the geometry is expressed directly in the source's grid, SCALE when it was extracted from a downsampled one",
    )
    grid: scalars.Any | None = strawberry.field(default=None, description="The octree grid, e.g. {'cellSize': [64, 64, 64], 'levels': 5, 'sortKey': 'MORTON'}. cellSize is in VOXELS, so the octree aligns to the label grid rather than to an arbitrary physical box")
    encoding: scalars.Any | None = strawberry.field(default=None, description="The geometry encoding, e.g. {'positions': 'UINT16_QUANTIZED_PER_CELL', 'normals': 'OCT16', 'codec': 'MESHOPT'}")
    provenance_metadata: scalars.Any | None = strawberry.field(default=None, description="How this collection was produced: the extraction run, its parameters and its inputs")


def create_mesh_collection(info: Info, input: CreateMeshCollectionInput) -> types.MeshCollection:
    """Register an immutable, versioned mesh collection, in a coordinate system of its own.

    The Parquet arrives the way every other Parquet object in the system does: the
    client requests a presigned upload, writes the object, and hands back the store
    id. ``fill_info`` is what marks the store populated -- the same step
    ``from_parquet_like`` takes for a table.

    The collection *owns* its coordinate system, and ``derivedFrom`` relates that system to
    whatever the meshes were extracted from -- which may now be a table or another
    collection, not only an image's grid. Meshes extracted from a half-resolution grid are a
    SCALE; under the shape this replaced, the only way to record that was to rewrite every
    vertex.

    ``axes`` is required. It used to default to a copy of the source system's, justified by
    "an identity derivation into a system with different axes is not an identity, and the
    rank check would say so" -- but the default edge is UNMAPPABLE now, and copying axes off
    a space you have just declared *unrelated* is a claim nothing would catch:
    ``assert_edge_rank`` returns early for an UNMAPPABLE.
    """
    model = input.to_pydantic()

    ctx = CreationContext.from_info(info)

    catalog = get_for_org(models.ParquetStore, info, id=model.catalog)
    catalog.fill_info()

    geometry = []
    for store_id in model.geometry or []:
        store = get_for_org(models.ParquetStore, info, id=store_id)
        store.fill_info()
        geometry.append(store)

    # Atomic, because the collection row is written before its axes are checked and before
    # its edges are: without this, an axis ordering the space refuses -- or a rank an edge
    # refuses -- leaves an orphan collection behind and returns an error. The same
    # guarantee `create_coordinate_system` keeps for a space and its registrations.
    with transaction.atomic():
        collection = models.MeshCollection.objects.create(
            version=model.version,
            spec_version=model.spec_version,
            catalog=catalog,
            grid=model.grid or {},
            encoding=model.encoding or {},
            provenance_metadata=model.provenance_metadata or {},
            creator=ctx.user,
            organization=ctx.organization,
        )
        if geometry:
            collection.geometry.set(geometry)

        system = graph_logic.create_collection_system(
            name=f"{collection.version}/mesh",
            axes=model.axes,
            owner=collection,
            ctx=ctx,
        )

        # Optional on purpose: a mesh in some absolute space is derived from nothing.
        coordinate_system_logic.write_derivation_edges(info, name=collection.version, own_system=system, derived_from=model.derived_from or [], ctx=ctx)

    return collection


class DeleteMeshCollectionInputModel(BaseModel):
    id: str = Field(description="The ID of the mesh collection to delete")


@kante.pydantic_input(DeleteMeshCollectionInputModel, description="Input for deleting a mesh collection by ID")
class DeleteMeshCollectionInput:
    """Input for deleting a mesh collection by ID."""

    id: strawberry.ID = strawberry.field(description="The ID of the mesh collection to delete")


delete_mesh_collection = make_delete(models.MeshCollection, DeleteMeshCollectionInput, owner=self_owner)
