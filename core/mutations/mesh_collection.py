"""Mutations for mesh collections.

A collection is immutable and versioned: refining an extraction produces a new
version, it does not edit an old one. Its Parquet goes through the datalayer like
every other Parquet object -- presigned upload, store id back -- so the client can
ask for an access grant and query it directly. There is deliberately no mutation
here that writes meshes one by one, and no field that reads them back that way.
"""

from kante.types import Info
import strawberry
from pydantic import BaseModel, Field

import kante
from core import enums, models, scalars, types
from core.creation import CreationContext
from core.inputs.coords import AxisInput, AxisInputModel, DerivationInput, DerivationInputModel
from core.logic import graph as graph_logic
from core.mutations._generic import make_delete, self_owner
from core.scoping import get_for_org


class CreateMeshCollectionInputModel(BaseModel):
    coordinate_system: str | None = None
    version: str
    spec_version: str
    catalog: str
    geometry: list[str] | None = None
    axes: list[AxisInputModel] | None = None
    derived_from: DerivationInputModel | None = None
    grid: dict | None = None
    encoding: dict | None = None
    provenance_metadata: dict | None = None


@kante.pydantic_input(CreateMeshCollectionInputModel, description="Input for registering an immutable, versioned mesh collection. The collection gets a coordinate system of its own, and an edge relates it to the space the meshes were extracted from")
class CreateMeshCollectionInput:
    """Input for registering a mesh collection."""

    coordinate_system: strawberry.ID | None = strawberry.field(
        default=None,
        description="The coordinate system the meshes were EXTRACTED FROM, e.g. that of the label array. The collection does not live in it -- it gets one of its own, and `derivedFrom` says how the two relate (an identity by default, which is what expressing the geometry directly in this system means). Omit it only for a mesh derived from no data at all, and then state `axes`",
    )
    version: str = strawberry.field(description="The immutable version of this collection, e.g. 'v20260713-a3f9'. A refined extraction is a new version, never an edit to an old one")
    spec_version: str = strawberry.field(description="The version of the mesh encoding specification this collection conforms to")
    catalog: scalars.ParquetLike = strawberry.field(
        description="The uploaded Parquet store holding the catalog that describes the meshes. Upload it through the normal parquet path (requestParquetUpload) and pass the store id here; the client then reads it back with an access grant"
    )
    geometry: list[scalars.ParquetLike] | None = strawberry.field(default=None, description="The uploaded Parquet stores holding the geometry shards")
    axes: list[AxisInput] | None = strawberry.field(default=None, description="The axes of the collection's own coordinate system, in order. Defaults to the axes of the system the meshes were extracted from, which is what an identity derivation means")
    derived_from: DerivationInput | None = strawberry.field(
        default=None,
        description="How the collection's own space relates to the space it was extracted from. Defaults to an IDENTITY -- the meshes are in that grid -- but a SCALE says the meshes were extracted from a downsampled grid, which under a borrowed coordinate system could only have been recorded by rewriting every vertex",
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

    The collection *owns* its coordinate system, and an edge relates that system to the one
    the meshes were extracted from. The default is an identity, which is exactly what
    borrowing the source's system used to assert -- so a client that passes only
    ``coordinateSystem``, as before, gets the same geometry it always did. What it now also
    gets is somewhere to say otherwise: meshes extracted from a half-resolution grid are a
    SCALE, and under the old shape the only way to record that was to rewrite every vertex.
    """
    model = input.to_pydantic()

    ctx = CreationContext.from_info(info)
    derivation = model.derived_from
    source = get_for_org(models.CoordinateSystem, info, id=model.coordinate_system) if model.coordinate_system else None

    catalog = get_for_org(models.ParquetStore, info, id=model.catalog)
    catalog.fill_info()

    geometry = []
    for store_id in model.geometry or []:
        store = get_for_org(models.ParquetStore, info, id=store_id)
        store.fill_info()
        geometry.append(store)

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

    # Its axes are the source's unless the client says otherwise: an identity derivation into
    # a system with different axes is not an identity, and the rank check would say so.
    axes = model.axes
    if axes is None:
        if source is None:
            raise ValueError("A mesh collection with no source coordinate system must state its own `axes`: there is nothing to copy them from.")
        axes = [AxisInputModel(name=axis.name, type=enums.AxisType(axis.type), long_name=axis.long_name, description=axis.description) for axis in source.axes.all()]

    system = graph_logic.create_collection_system(
        name=f"{collection.version}/mesh",
        axes=axes,
        owner=collection,
        ctx=ctx,
    )

    # Optional on purpose: a mesh in some absolute space belongs to no dataset and is
    # derived from nothing.
    if source is not None:
        graph_logic.write_relation_edge(
            name=f"{collection.version} <- {source.name}",
            input_system=system,
            output_system=source,
            kind=(derivation.kind.value if derivation else enums.TransformKind.IDENTITY.value),
            scale=derivation.scale if derivation else None,
            translation=derivation.translation if derivation else None,
            affine=derivation.affine if derivation else None,
            input_axes=derivation.input_axes if derivation else None,
            output_axes=derivation.output_axes if derivation else None,
            ctx=ctx,
        )

    return collection


class DeleteMeshCollectionInputModel(BaseModel):
    id: str = Field(description="The ID of the mesh collection to delete")


@kante.pydantic_input(DeleteMeshCollectionInputModel, description="Input for deleting a mesh collection by ID")
class DeleteMeshCollectionInput:
    """Input for deleting a mesh collection by ID."""

    id: strawberry.ID = strawberry.field(description="The ID of the mesh collection to delete")


delete_mesh_collection = make_delete(models.MeshCollection, DeleteMeshCollectionInput, owner=self_owner)
