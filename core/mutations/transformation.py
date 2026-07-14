"""Mutations for the edges of the coordinate graph.

This is where registration lives now. It used to be a 4x4 matrix on the layer,
which meant two layers over one dataset carried two copies of one fact and were
free to disagree; it is now a single edge between two coordinate systems, and a
scene declares which edges it composes with.

Direction is always forward: input to output. Registration libraries routinely
hand you the inverse, so normalize before you call these -- there is deliberately
no flag to record which way round a matrix runs, because half the graph would
end up pointing the wrong way and nothing would tell you.
"""

from kante.types import Info
import strawberry
from pydantic import BaseModel, Field

import kante
from core import enums, models, scalars, types
from core.creation import CreationContext
from core.logic import graph as graph_logic
from core.mutations._generic import make_delete, self_owner
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
    store: str | None = None
    reason: str | None = None
    scene: str | None = None
    validity: enums.PlacementValidity | None = None


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
    input_axes: list[str] | None = strawberry.field(default=None, description="(BY_DIMENSION / MAP_AXIS) The names of the input axes this transformation acts on, e.g. ['z', 'y', 'x']")
    output_axes: list[str] | None = strawberry.field(default=None, description="(BY_DIMENSION / MAP_AXIS) The names of the output axes it produces")
    store: scalars.ArrayLike | None = strawberry.field(
        default=None,
        description="(DISPLACEMENTS / COORDINATES) The Zarr array holding the field: per-point offsets for DISPLACEMENTS, absolute positions for COORDINATES. Neither has a closed-form inverse, so a placement path will only ever walk them forwards",
    )
    reason: str | None = strawberry.field(default=None, description="(UNMAPPABLE) Why nothing corresponds, e.g. 'one row per segmented object'. Purely descriptive: the kind is what the graph acts on")
    scene: strawberry.ID | None = strawberry.field(default=None, description="Optionally add this edge to a scene's composition straight away. An edge exists independently of any scene; membership is a separate statement")
    validity: enums.PlacementValidity | None = strawberry.field(
        default=None,
        description="How much this map is actually known. Defaults to MANUAL -- someone authored it. Say VALIDATED when the registration was checked against the data, INFERRED when the numbers were read from metadata. A layer's validity is the weakest edge on its path to world",
    )


#: The parameters each creatable kind requires. BY_DIMENSION requires none of them: it is
#: the *axis naming* that carries the map, and any parameters it does carry act on the
#: axes it names. UNMAPPABLE requires none because it *has* none, and rejects them below.
_PARAMS_BY_KIND: dict[str, tuple[str, ...]] = {
    enums.TransformKind.IDENTITY.value: (),
    enums.TransformKind.SCALE.value: ("scale",),
    enums.TransformKind.TRANSLATION.value: ("translation",),
    enums.TransformKind.AFFINE.value: ("affine",),
    enums.TransformKind.ROTATION.value: ("affine",),
    enums.TransformKind.MAP_AXIS.value: (),
    enums.TransformKind.BY_DIMENSION.value: (),
    enums.TransformKind.DISPLACEMENTS.value: (),
    enums.TransformKind.COORDINATES.value: (),
    enums.TransformKind.UNMAPPABLE.value: (),
}

#: The parameters a BY_DIMENSION edge may additionally carry, acting on its named axes.
_OPTIONAL_PARAMS_BY_KIND: dict[str, tuple[str, ...]] = {
    enums.TransformKind.BY_DIMENSION.value: ("scale", "translation", "affine"),
}

#: The kinds whose map lives in a Zarr array rather than in parameters.
_FIELD_KINDS = (enums.TransformKind.DISPLACEMENTS.value, enums.TransformKind.COORDINATES.value)

#: The parameter fields an UNMAPPABLE edge must not carry. It declares that no point of one
#: space corresponds to a point of the other; a scale on it would assert a correspondence
#: and deny one in the same breath, and nothing downstream would ever read the number to
#: find out. Better to refuse it than to store a lie no query will ever surface.
_FORBIDDEN_ON_UNMAPPABLE = ("scale", "translation", "affine", "input_axes", "output_axes")


def create_transformation(info: Info, input: CreateTransformationInput) -> types.Transformation:
    """Create one edge of the coordinate graph, optionally adding it to a scene.

    BY_DIMENSION is how a registration crosses a rank boundary: a (c,y,x) dataset placed
    into a (t,z,y,x) world names the axes it acts on (``inputAxes: ["y","x"]``,
    ``outputAxes: ["y","x"]``) and says nothing about the world's `t` and `z`, which is
    exactly the truth -- the dataset has no opinion about them. A square edge between
    systems of different rank cannot express that, and the parameters would be checked
    against the wrong number of axes.
    """
    model = input.to_pydantic()

    kind = model.kind.value
    if kind not in _PARAMS_BY_KIND:
        raise ValueError(f"{kind} cannot be created directly. SEQUENCE, BY_DIMENSION and BIJECTION wrappers are built by the ingest, which writes their children with them")

    if kind == enums.TransformKind.UNMAPPABLE.value:
        offending = [field for field in _FORBIDDEN_ON_UNMAPPABLE if getattr(model, field) is not None]
        if offending:
            raise ValueError(f"An UNMAPPABLE transformation declares that no point of one space corresponds to a point of the other, so it carries no map: drop {', '.join(offending)}, or use a kind that does map.")

    params: dict = {}
    for field in _PARAMS_BY_KIND[kind]:
        value = getattr(model, field)
        if value is None:
            raise ValueError(f"A {kind} transformation requires `{field}`")
        params[field] = value

    for field in _OPTIONAL_PARAMS_BY_KIND.get(kind, ()):
        value = getattr(model, field)
        if value is not None:
            params[field] = value

    if model.reason:
        params["reason"] = model.reason

    ctx = CreationContext.from_info(info)

    input_system = get_for_org(models.CoordinateSystem, info, id=model.input)
    output_system = get_for_org(models.CoordinateSystem, info, id=model.output)

    # The field itself, for the two kinds whose map is an array rather than a formula.
    store = None
    if kind in _FIELD_KINDS:
        if not model.store:
            raise ValueError(f"A {kind} transformation is given by an array, so it requires `store`: the Zarr holding the {'offsets' if kind == enums.TransformKind.DISPLACEMENTS.value else 'positions'}")
        store = get_for_org(models.ZarrStore, info, id=model.store)
    elif model.store:
        raise ValueError(f"A {kind} transformation's map is in its parameters, not in an array, so it takes no `store`")

    graph_logic.assert_edge_rank(
        kind=kind,
        params=params,
        input_axes=model.input_axes,
        output_axes=model.output_axes,
        input_system=input_system,
        output_system=output_system,
    )

    transformation = models.Transformation.objects.create(
        kind=kind,
        name=model.name,
        input=input_system,
        output=output_system,
        input_axes=model.input_axes,
        output_axes=model.output_axes,
        params=params,
        store=store,
        # MANUAL, not the model's VALIDATED default: this edge arrived through the API,
        # so someone authored it -- which is a different claim from "checked against the
        # data", and the caller says so explicitly when it was.
        validity=(model.validity or enums.PlacementValidity.MANUAL).value,
        creator=ctx.user,
        organization=ctx.organization,
    )

    if model.scene:
        scene = get_for_org(models.Scene, info, id=model.scene)
        scene.coordinate_transformations.add(transformation)

    return transformation


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


class SceneTransformationInputModel(BaseModel):
    scene: str
    transformation: str


@kante.pydantic_input(SceneTransformationInputModel, description="Input for adding or removing an edge from a scene's composition")
class SceneTransformationInput:
    """Input for adding or removing an edge from a scene's composition."""

    scene: strawberry.ID = strawberry.field(description="The scene whose composition to change")
    transformation: strawberry.ID = strawberry.field(description="The transformation edge to add or remove")


def add_transformation_to_scene(info: Info, input: SceneTransformationInput) -> types.Scene:
    """Add an existing edge to a scene's composition."""
    model = input.to_pydantic()
    scene = get_for_org(models.Scene, info, id=model.scene)
    transformation = get_for_org(models.Transformation, info, id=model.transformation)
    scene.coordinate_transformations.add(transformation)
    return scene


def remove_transformation_from_scene(info: Info, input: SceneTransformationInput) -> types.Scene:
    """Remove an edge from a scene's composition. The edge itself survives: it is a fact about two coordinate systems."""
    model = input.to_pydantic()
    scene = get_for_org(models.Scene, info, id=model.scene)
    transformation = get_for_org(models.Transformation, info, id=model.transformation)
    scene.coordinate_transformations.remove(transformation)
    return scene


class DeleteTransformationInputModel(BaseModel):
    id: str = Field(description="The ID of the transformation to delete")


@kante.pydantic_input(DeleteTransformationInputModel, description="Input for deleting a transformation by ID")
class DeleteTransformationInput:
    """Input for deleting a transformation by ID."""

    id: strawberry.ID = strawberry.field(description="The ID of the transformation to delete")


delete_transformation = make_delete(models.Transformation, DeleteTransformationInput, owner=self_owner)
