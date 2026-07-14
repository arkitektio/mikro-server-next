"""Mutations for feature collections: per-object measurement tables.

A feature table is the case the coordinate graph could not previously express. Its rows
are objects, not positions -- there is no point of the image that *is* row 7 -- so it does
not live in the image's pixel grid, and saying that it did (by borrowing the dataset's
system, as a mesh collection legitimately can) would assert a correspondence that does not
exist. It gets a coordinate system of its own, whose single INDEX axis enumerates the
objects, and the edge relating it to the image it was computed from is UNMAPPABLE: the two
are related, and nothing maps.

That is the whole reason to record it. The lineage survives -- this table came from that
image, and a client can ask -- while the geometry stays honest.
"""

import strawberry
from kante.types import Info
from pydantic import BaseModel, Field

import kante
from core import enums, models, scalars, types
from core.creation import CreationContext
from core.inputs.coords import AnchorInput, AnchorInputModel, AxisInput, AxisInputModel
from core.logic import graph as graph_logic
from core.mutations._generic import make_delete, self_owner
from core.scoping import get_for_org

#: The default space of a feature table: one axis, enumerating the objects. It has no unit
#: because there is nothing to measure -- the distance between object 3 and object 4 means
#: nothing -- and it has no second axis because the columns are named in the Parquet, not
#: indexed by position.
_DEFAULT_AXES = [AxisInputModel(name="object", type=enums.AxisType.INDEX)]


class CreateFeatureCollectionInputModel(BaseModel):
    name: str
    version: str
    store: str
    coordinate_system: str | None = None
    spec_version: str | None = None
    axes: list[AxisInputModel] | None = None
    anchor: AnchorInputModel | None = None
    provenance_metadata: dict | None = None


@kante.pydantic_input(
    CreateFeatureCollectionInputModel,
    description="Input for registering an immutable, versioned table of per-object measurements. It gets a coordinate system of its own -- its rows are objects, not positions -- and an UNMAPPABLE edge relates it to the data it was measured from",
)
class CreateFeatureCollectionInput:
    """Input for registering a feature collection."""

    name: str = strawberry.field(description="The name of this collection, e.g. 'nuclei morphology'")
    version: str = strawberry.field(description="The immutable version of this collection. A recomputation is a new version, never an edit to an old one")
    store: scalars.ParquetLike = strawberry.field(description="The uploaded Parquet store holding the table. Upload it through the normal parquet path (requestParquetUpload) and pass the store id here; the client then reads it back with an access grant")
    coordinate_system: strawberry.ID | None = strawberry.field(
        default=None,
        description="The coordinate system the objects were MEASURED FROM, e.g. the intrinsic grid of the label array. The table does not live in it -- nothing in it is a position -- so the edge that relates them is UNMAPPABLE by default",
    )
    spec_version: str | None = strawberry.field(default=None, description="The version of the feature-table specification this collection conforms to")
    axes: list[AxisInput] | None = strawberry.field(default=None, description="The axes of the collection's own coordinate system. Defaults to a single INDEX axis named 'object': one row per object, and the columns named in the Parquet rather than indexed here")
    anchor: AnchorInput | None = strawberry.field(
        default=None,
        description="How this table relates to the data it was measured from. Defaults to UNMAPPABLE, which is the truth for a measurement table: it came from that image, and no point of the image is one of its rows. Overriding it means claiming a real point correspondence, and the rank check will hold you to it",
    )
    provenance_metadata: scalars.Any | None = strawberry.field(default=None, description="How this table was produced: the measurement run, its parameters and its inputs")


def create_feature_collection(info: Info, input: CreateFeatureCollectionInput) -> types.FeatureCollection:
    """Register a table of per-object measurements, in a coordinate system of its own."""
    model = input.to_pydantic()

    ctx = CreationContext.from_info(info)
    anchor = model.anchor
    source = get_for_org(models.CoordinateSystem, info, id=model.coordinate_system) if model.coordinate_system else None

    store = get_for_org(models.ParquetStore, info, id=model.store)
    store.fill_info()

    collection = models.FeatureCollection.objects.create(
        name=model.name,
        version=model.version,
        spec_version=model.spec_version,
        store=store,
        provenance_metadata=model.provenance_metadata or {},
        creator=ctx.user,
        organization=ctx.organization,
    )

    system = graph_logic.create_collection_system(
        name=f"{collection.name}/{collection.version}",
        kind=enums.CoordinateSystemKindChoices.FEATURE.value,
        axes=model.axes or _DEFAULT_AXES,
        owner_field="feature_collection",
        owner=collection,
        ctx=ctx,
    )

    if source is not None:
        graph_logic.write_relation_edge(
            name=f"{collection.name} <- {source.name}",
            input_system=system,
            output_system=source,
            kind=(anchor.kind.value if anchor else enums.TransformKind.UNMAPPABLE.value),
            scale=anchor.scale if anchor else None,
            translation=anchor.translation if anchor else None,
            affine=anchor.affine if anchor else None,
            input_axes=anchor.input_axes if anchor else None,
            output_axes=anchor.output_axes if anchor else None,
            reason=anchor.reason if anchor else None,
            ctx=ctx,
        )

    return collection


class DeleteFeatureCollectionInputModel(BaseModel):
    id: str = Field(description="The ID of the feature collection to delete")


@kante.pydantic_input(DeleteFeatureCollectionInputModel, description="Input for deleting a feature collection by ID")
class DeleteFeatureCollectionInput:
    """Input for deleting a feature collection by ID."""

    id: strawberry.ID = strawberry.field(description="The ID of the feature collection to delete")


delete_feature_collection = make_delete(models.FeatureCollection, DeleteFeatureCollectionInput, owner=self_owner)
