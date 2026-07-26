"""Mutations for the edges of the coordinate graph.

This is where registration lives now. It used to be a 4x4 matrix on the layer,
which meant two layers over one dataset carried two copies of one fact and were
free to disagree; it is now a single edge between two coordinate systems -- and
under RFC-6 that edge is *the* truth: unique per (data-tree, shared space), so
authoring it places the data in every scene over that space, with no membership
to declare. Refining it is `updateTransformation`, in place and audited; a
genuine alternative registers into a fork of the space, never a rival row here.

Direction is always forward: input to output. Registration libraries routinely
hand you the inverse, so normalize before you call these -- there is deliberately
no flag to record which way round a matrix runs, because half the graph would
end up pointing the wrong way and nothing would tell you.
"""

from kante.types import Info
import strawberry
from pydantic import BaseModel, Field

import kante
from core import enums, models, types
from core.creation import CreationContext
from core.logic import coordinate_system as coordinate_system_logic
from core.logic import graph as graph_logic
from core.mutations._generic import assert_can_delete, creator_owner, make_delete
from core.scoping import get_for_org


class CreateTransformationInputModel(BaseModel):
    input: str
    output: str
    kind: enums.TransformKind
    name: str | None = None
    scale: list[float] | None = None
    translation: list[float] | None = None
    affine: list[list[float]] | None = None
    input_axes: list[str] | None = None
    output_axes: list[str] | None = None
    field: str | None = None
    reason: str | None = None
    validity: enums.PlacementValidity | None = None
    value_relation: enums.ValueRelation | None = None


@kante.pydantic_input(CreateTransformationInputModel, description="Input for creating one edge of the coordinate graph, mapping an input coordinate system to an output one")
class CreateTransformationInput:
    """Input for creating one edge of the coordinate graph."""

    input: strawberry.ID = strawberry.field(description="The coordinate system this transformation maps from")
    output: strawberry.ID = strawberry.field(description="The coordinate system this transformation maps to. Direction is always forward -- if your registration library gave you the inverse, invert it before calling")
    kind: enums.TransformKind = strawberry.field(description="The kind of transformation, which fixes which of the parameter fields below are read")
    name: str | None = strawberry.field(default=None, description="Optional name for the transformation")
    scale: list[float] | None = strawberry.field(default=None, description="(SCALE) The per-axis scale factors, in the axis order of the input system")
    translation: list[float] | None = strawberry.field(default=None, description="(TRANSLATION) The per-axis offsets, in the axis order of the input system")
    affine: list[list[float]] | None = strawberry.field(default=None, description="(AFFINE / ROTATION) The matrix, M x (N+1), rows outermost. The last column is the translation")
    input_axes: list[str] | None = strawberry.field(default=None, description="(BY_DIMENSION / MAP_AXIS) The names of the input axes this transformation acts on, e.g. ['z', 'y', 'x']. (FIELD) The input axes the lookup consumes, e.g. ['y', 'x'] for a label mask -- the ones it does not name pass through")
    output_axes: list[str] | None = strawberry.field(default=None, description="(BY_DIMENSION / MAP_AXIS) The names of the output axes it produces. (FIELD) The output axes the field's values produce, e.g. ['i']")
    field: strawberry.ID | None = strawberry.field(
        default=None,
        description="(FIELD) The coordinate system of the array whose values are the map. Its value axis says what they mean -- COORDINATE for absolute positions, DISPLACEMENT for offsets, none at all for a scalar array whose one value is a position. Pass the input's own system when the array's pixels are themselves the map, as for a label mask keying a table of objects. A FIELD has no closed-form inverse, so a placement path only ever walks it forwards",
    )
    reason: str | None = strawberry.field(default=None, description="(UNMAPPABLE) Why nothing corresponds, e.g. 'one row per segmented object'. Purely descriptive: the kind is what the graph acts on")
    validity: enums.PlacementValidity | None = strawberry.field(
        default=None,
        description="How much this map is actually known. Defaults to MANUAL -- someone authored it. Say VALIDATED when the registration was checked against the data, INFERRED when the numbers were read from metadata. A layer's validity is the weakest edge on its path to world",
    )
    value_relation: enums.ValueRelation | None = strawberry.field(
        default=None,
        description="(derivation edges only) What the operation did to the *values*, orthogonal to `kind`: IDENTICAL for a crop, TRANSFORMED for a deconvolution, CATEGORIZED for a threshold or segmentation. Refused on an edge into a shared space -- a registration relates spaces, and values do not cross it",
    )


def create_transformation(info: Info, input: CreateTransformationInput) -> types.Transformation:
    """Create one edge of the coordinate graph.

    A thin request-scoped wrapper: it resolves the two systems and any field node, then
    delegates the parameter validation, rank check, one-truth-per-space collision guard
    and write to :func:`core.logic.graph.build_registration_edge`, which the
    coordinate-system builder shares. An edge into a shared space is a registration and
    places its data in every scene over that space by existing -- there is no scene to
    name and nothing to endorse. BY_DIMENSION is how a registration crosses a rank
    boundary: a (c,y,x) dataset placed into a (t,z,y,x) world names the axes it acts on
    and says nothing about the world's `t` and `z`, which is exactly the truth.
    """
    model = input.to_pydantic()
    ctx = CreationContext.from_info(info)

    input_system = get_for_org(models.CoordinateSystem, info, id=model.input)
    output_system = get_for_org(models.CoordinateSystem, info, id=model.output)
    field = get_for_org(models.CoordinateSystem, info, id=model.field) if model.field else None

    return graph_logic.build_registration_edge(
        input_system=input_system,
        output_system=output_system,
        kind=model.kind,
        name=model.name,
        scale=model.scale,
        translation=model.translation,
        affine=model.affine,
        input_axes=model.input_axes,
        output_axes=model.output_axes,
        field=field,
        reason=model.reason,
        validity=model.validity,
        value_relation=model.value_relation,
        ctx=ctx,
    )


class UpdateTransformationInputModel(BaseModel):
    id: str
    name: str | None = None
    scale: list[float] | None = None
    translation: list[float] | None = None
    affine: list[list[float]] | None = None
    validity: enums.PlacementValidity | None = None


@kante.pydantic_input(UpdateTransformationInputModel, description="Input for refining an edge's parameters. Bumps its version, which is what tells an ROI its chain has moved")
class UpdateTransformationInput:
    """Input for refining an edge's parameters."""

    id: strawberry.ID = strawberry.field(description="The ID of the transformation to refine")
    name: str | None = strawberry.field(default=None, description="A new name for the transformation")
    scale: list[float] | None = strawberry.field(default=None, description="(SCALE) The refined per-axis scale factors")
    translation: list[float] | None = strawberry.field(default=None, description="(TRANSLATION) The refined per-axis offsets")
    affine: list[list[float]] | None = strawberry.field(default=None, description="(AFFINE / ROTATION) The refined matrix")
    validity: enums.PlacementValidity | None = strawberry.field(
        default=None,
        description="A new validity for the edge -- how it stops being an assumption: set MANUAL when a real registration replaces an assumed one in place, VALIDATED when it was checked against the data. Every layer whose path runs through this edge reflects it immediately, because a layer's validity is derived, never stored",
    )


def update_transformation(info: Info, input: UpdateTransformationInput) -> types.Transformation:
    """Refine an edge's parameters, bumping its version.

    The version bump is the signal that every ROI downstream of this edge was
    authored against an older chain. Recomputing their bounding boxes is a separate,
    bulk operation: a registration refinement can touch thousands of them, so it does
    not belong on this request's critical path.
    """
    model = input.to_pydantic()

    transformation = get_for_org(models.Transformation, info, id=model.id)

    supplied = [field for field in ("scale", "translation", "affine") if getattr(model, field) is not None]
    if transformation.kind == enums.TransformKind.UNMAPPABLE.value and supplied:
        # `assert_edge_rank` returns early for an UNMAPPABLE (it has no rank to check), so
        # without this the parameters would be written and simply never read -- a map that
        # exists in the database and nowhere else. If the geometry turns out to survive
        # after all, the edge was the wrong kind, and changing the kind is the honest fix.
        raise ValueError(f"An UNMAPPABLE transformation declares that no point of one space corresponds to a point of the other, so there is nothing to refine: it has no `{supplied[0]}`. If a correspondence does exist, replace the edge with one whose kind can express it.")

    params = dict(transformation.params)
    for field in ("scale", "translation", "affine"):
        value = getattr(model, field)
        if value is not None:
            params[field] = value

    # A refinement is a write like any other: the rank it lands on is the rank the
    # endpoints already fix, and an update that silently changed it would be a back door
    # around the check `create_transformation` makes.
    if transformation.input and transformation.output:
        graph_logic.assert_edge_rank(
            kind=transformation.kind,
            params=params,
            input_axes=transformation.input_axes,
            output_axes=transformation.output_axes,
            input_system=transformation.input,
            output_system=transformation.output,
        )

    if model.name is not None:
        transformation.name = model.name

    if model.validity is not None:
        transformation.validity = model.validity.value

    transformation.params = params
    transformation.version += 1
    transformation.save(update_fields=["params", "version", "name", "validity"])

    return transformation


class DeleteTransformationInputModel(BaseModel):
    id: str = Field(description="The ID of the transformation to delete")


@kante.pydantic_input(DeleteTransformationInputModel, description="Input for deleting a transformation by ID")
class DeleteTransformationInput:
    """Input for deleting a transformation by ID."""

    id: strawberry.ID = strawberry.field(description="The ID of the transformation to delete")


# `creator_owner`, not `self_owner`: a Transformation has a creator but no
# `created_through_by`, which self_owner reads unconditionally.
delete_transformation = make_delete(models.Transformation, DeleteTransformationInput, owner=creator_owner)


class DeleteRegistrationInputModel(BaseModel):
    dataset: str | None = None
    table_dataset: str | None = None
    mesh_collection: str | None = None
    annotation_collection: str | None = None
    coordinate_system: str | None = None
    world: str = Field(description="The shared space the registration goes into")


@kante.pydantic_input(
    DeleteRegistrationInputModel,
    description="Input for un-registering a source from a shared space by naming the source and the space, not the edge. Provide exactly one source -- the same selector registering it took",
)
class DeleteRegistrationInput:
    """Input for un-registering a source from a shared space."""

    dataset: strawberry.ID | None = strawberry.field(default=None, description="Un-register this dataset. Provide exactly one source")
    table_dataset: strawberry.ID | None = strawberry.field(default=None, description="Un-register this table dataset. Provide exactly one source")
    mesh_collection: strawberry.ID | None = strawberry.field(default=None, description="Un-register this mesh collection. Provide exactly one source")
    annotation_collection: strawberry.ID | None = strawberry.field(default=None, description="Un-register this annotation collection. Provide exactly one source")
    coordinate_system: strawberry.ID | None = strawberry.field(default=None, description="Un-register this coordinate system. Provide exactly one source")
    world: strawberry.ID = strawberry.field(description="The shared space to un-register the source from")


def delete_registration(info: Info, input: DeleteRegistrationInput) -> strawberry.ID:
    """Delete the registration placing a source in a shared space, named by source and space.

    The inverse of a `registrations` entry in `createCoordinateSystem`, for the caller who
    knows *what* is registered *where* but not the edge id -- RFC-6 guarantees there is at
    most one edge to mean: one claim per (data-tree, space), matched by the same claim
    root the collision guard checks, so registering through a calibration and
    un-registering by the dataset still meet on the same edge. Deleting it un-places the
    source in every scene over the space (layers drop to UNREGISTERED); an UNMAPPABLE
    declaration is not a placement and is not matched -- delete it by id with
    `deleteTransformation`.
    """
    model = input.to_pydantic()

    world = get_for_org(models.CoordinateSystem, info, id=model.world)
    if not graph_logic.is_registration_target(world):
        raise ValueError(f"Coordinate system {world.pk} is owned by a container, so nothing is registered into it: registrations land exclusively on shared spaces. Edges into an owned system are its container's facts -- delete one by id with deleteTransformation.")

    source_system = coordinate_system_logic.resolve_source_system(
        dataset=get_for_org(models.ADataset, info, id=model.dataset) if model.dataset else None,
        table_dataset=get_for_org(models.TableDataset, info, id=model.table_dataset) if model.table_dataset else None,
        mesh_collection=get_for_org(models.MeshCollection, info, id=model.mesh_collection) if model.mesh_collection else None,
        annotation_collection=get_for_org(models.AnnotationCollection, info, id=model.annotation_collection) if model.annotation_collection else None,
        coordinate_system=get_for_org(models.CoordinateSystem, info, id=model.coordinate_system) if model.coordinate_system else None,
    )

    root = graph_logic.claim_root(source_system)
    claims = (
        models.Transformation.objects.filter(output=world, parent__isnull=True)
        .exclude(kind=enums.TransformKindChoices.UNMAPPABLE.value)
        .select_related("input")
    )
    edge = next((claim for claim in claims if claim.input is not None and graph_logic.claim_root(claim.input) == root), None)
    if edge is None:
        raise ValueError(f"Nothing to delete: this source has no registration in '{world.name}'. One truth per space means at most one edge could have matched, and none does.")

    assert_can_delete(info, edge, creator_owner)
    deleted = strawberry.ID(str(edge.pk))
    edge.delete()
    return deleted
