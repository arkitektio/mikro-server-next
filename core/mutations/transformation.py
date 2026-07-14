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
from core import enums, models, types
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
    scene: str | None = None


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
    scene: strawberry.ID | None = strawberry.field(default=None, description="Optionally add this edge to a scene's composition straight away. An edge exists independently of any scene; membership is a separate statement")


#: The parameters each creatable kind requires. BY_DIMENSION requires none of them: it is
#: the *axis naming* that carries the map, and any parameters it does carry act on the
#: axes it names.
_PARAMS_BY_KIND: dict[str, tuple[str, ...]] = {
    enums.TransformKind.IDENTITY.value: (),
    enums.TransformKind.SCALE.value: ("scale",),
    enums.TransformKind.TRANSLATION.value: ("translation",),
    enums.TransformKind.AFFINE.value: ("affine",),
    enums.TransformKind.ROTATION.value: ("affine",),
    enums.TransformKind.MAP_AXIS.value: (),
    enums.TransformKind.BY_DIMENSION.value: (),
}

#: The parameters a BY_DIMENSION edge may additionally carry, acting on its named axes.
_OPTIONAL_PARAMS_BY_KIND: dict[str, tuple[str, ...]] = {
    enums.TransformKind.BY_DIMENSION.value: ("scale", "translation", "affine"),
}


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
        raise ValueError(f"{kind} cannot be created directly. SEQUENCE and BIJECTION are built by the ingest; DISPLACEMENTS and BIJECTION are not supported in v1")

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

    ctx = CreationContext.from_info(info)

    input_system = get_for_org(models.CoordinateSystem, info, id=model.input)
    output_system = get_for_org(models.CoordinateSystem, info, id=model.output)

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


@kante.pydantic_input(UpdateTransformationInputModel, description="Input for refining an edge's parameters. Bumps its version, which is what tells an ROI its chain has moved")
class UpdateTransformationInput:
    """Input for refining an edge's parameters."""

    id: strawberry.ID = strawberry.field(description="The ID of the transformation to refine")
    name: str | None = strawberry.field(default=None, description="A new name for the transformation")
    scale: list[float] | None = strawberry.field(default=None, description="(SCALE) The refined per-axis scale factors")
    translation: list[float] | None = strawberry.field(default=None, description="(TRANSLATION) The refined per-axis offsets")
    affine: list[list[float]] | None = strawberry.field(default=None, description="(AFFINE / ROTATION) The refined matrix")


def update_transformation(info: Info, input: UpdateTransformationInput) -> types.Transformation:
    """Refine an edge's parameters, bumping its version.

    The version bump is the signal that every ROI downstream of this edge was
    authored against an older chain. Recomputing their bounding boxes is a separate,
    bulk operation: a registration refinement can touch thousands of them, so it does
    not belong on this request's critical path.
    """
    model = input.to_pydantic()

    transformation = get_for_org(models.Transformation, info, id=model.id)

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

    transformation.params = params
    transformation.version += 1
    transformation.save(update_fields=["params", "version", "name"])

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
