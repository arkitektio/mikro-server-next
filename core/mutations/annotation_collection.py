"""Mutations for annotation collections.

An annotation collection is the human-drawn counterpart of a mesh collection: it
owns the coordinate system its shapes are drawn in, and an edge relates that
system to whatever the shapes were drawn over. The explicit create here is for
freestanding or dataset-derived collections; the common path -- drawing on a
scene -- goes through ``createAnnotation``, which mints the scene's collection
on first use.
"""

from kante.types import Info
import strawberry
from pydantic import BaseModel, Field

import kante
from core import enums, models, types
from core.creation import CreationContext
from core.inputs.coords import AxisInput, AxisInputModel, DerivationInput, DerivationInputModel
from core.logic import graph as graph_logic
from core.mutations._generic import make_delete, self_owner
from core.scoping import get_for_org


class CreateAnnotationCollectionInputModel(BaseModel):
    name: str
    description: str | None = None
    coordinate_system: str | None = None
    axes: list[AxisInputModel] | None = None
    derived_from: DerivationInputModel | None = None


@kante.pydantic_input(
    CreateAnnotationCollectionInputModel,
    description="Input for creating an annotation collection. The collection gets a coordinate system of its own, and an edge relates it to the space the shapes are drawn over",
)
class CreateAnnotationCollectionInput:
    """Input for creating an annotation collection."""

    name: str = strawberry.field(description="The name of the annotation collection")
    description: str | None = strawberry.field(default=None, description="A free-form description of the collection")
    coordinate_system: strawberry.ID | None = strawberry.field(
        default=None,
        description="The coordinate system the shapes are DRAWN OVER, e.g. a dataset's intrinsic system. The collection does not live in it -- it gets one of its own, and `derivedFrom` says how the two relate (an identity by default). Omit it for a freestanding collection, and then state `axes`",
    )
    axes: list[AxisInput] | None = strawberry.field(default=None, description="The axes of the collection's own coordinate system, in order. Defaults to the axes of the system the shapes are drawn over, which is what an identity derivation means")
    derived_from: DerivationInput | None = strawberry.field(
        default=None,
        description="How the collection's own space relates to the space the shapes are drawn over. Defaults to an IDENTITY -- the shapes are in that grid as drawn",
    )


def create_annotation_collection(info: Info, input: CreateAnnotationCollectionInput) -> types.AnnotationCollection:
    """Create an annotation collection, in a coordinate system of its own.

    The same shape as ``create_mesh_collection``: the collection owns its system, and an
    optional edge relates that system to the one the shapes are drawn over. A collection
    created here has no scene -- the scene-minted collection is ``createAnnotation``'s
    business -- so placing it in a scene is an explicit registration plus an
    ``createAnnotationLayer``.
    """
    model = input.to_pydantic()

    ctx = CreationContext.from_info(info)
    derivation = model.derived_from
    source = get_for_org(models.CoordinateSystem, info, id=model.coordinate_system) if model.coordinate_system else None

    collection = models.AnnotationCollection.objects.create(
        name=model.name,
        description=model.description,
        creator=ctx.user,
        organization=ctx.organization,
        **ctx.provenance_kwargs(),
    )

    # Its axes are the source's unless the client says otherwise: an identity derivation into
    # a system with different axes is not an identity, and the rank check would say so.
    axes = model.axes
    if axes is None:
        if source is None:
            raise ValueError("An annotation collection with no source coordinate system must state its own `axes`: there is nothing to copy them from.")
        axes = [AxisInputModel(name=axis.name, type=enums.AxisType(axis.type), long_name=axis.long_name, description=axis.description) for axis in source.axes.all()]

    system = graph_logic.create_collection_system(
        name=f"{collection.name}/drawing",
        axes=axes,
        owner=collection,
        ctx=ctx,
    )

    # Optional on purpose: a collection in some absolute space is drawn over nothing.
    if source is not None:
        graph_logic.write_relation_edge(
            name=f"{collection.name} <- {source.name}",
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


class DeleteAnnotationCollectionInputModel(BaseModel):
    id: str = Field(description="The ID of the annotation collection to delete")


@kante.pydantic_input(DeleteAnnotationCollectionInputModel, description="Input for deleting an annotation collection by ID")
class DeleteAnnotationCollectionInput:
    """Input for deleting an annotation collection by ID."""

    id: strawberry.ID = strawberry.field(description="The ID of the annotation collection to delete. Its coordinate system, its annotations and its layers cascade with it")


delete_annotation_collection = make_delete(models.AnnotationCollection, DeleteAnnotationCollectionInput, owner=self_owner)
