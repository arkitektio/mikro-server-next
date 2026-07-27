"""Mutations for annotations: the human-drawn, editable shapes.

``createAnnotation`` takes either a collection or a scene, exactly one. The
scene path is the sugar that makes drawing feel direct: the first shape drawn
on a scene mints that scene's collection -- its own coordinate system mirroring
the world's axes, an identity registration into the world, and one annotation
layer -- and every later shape appends to it. The edge is authored here, at
collection creation, the same way the scene bootstrap authors its mirror edge:
this is not a layer mutation fabricating placement, it is a creation flow
stating where a brand-new space sits, once.
"""

from django.db import IntegrityError, transaction
from kante.types import Info
import strawberry
from pydantic import BaseModel
from simple_history.utils import bulk_create_with_history

import kante
from core import enums, models, scalars, types
from core.creation import CreationContext
from core.inputs.coords import AxisInputModel, CoordinateInput, CoordinateInputModel
from core.logic import graph as graph_logic
from core.mutations._generic import make_delete, self_owner
from core.scoping import get_for_org


class CreateAnnotationInputModel(BaseModel):
    collection: str | None = None
    scene: str | None = None
    kind: enums.RoiKind
    name: str | None = None
    description: str | None = None
    vectors: list[list[float]] | None = None
    coordinates: list[CoordinateInputModel] | None = None
    stroke_color: list[int] | None = None
    fill_color: list[int] | None = None
    stroke_width: float | None = None
    filled: bool | None = None


@kante.pydantic_input(
    CreateAnnotationInputModel,
    description="Input for drawing an annotation. Provide exactly one of `collection` (append to it) or `scene` (draw on the scene: its annotation collection is found, or minted on first use together with its coordinate system, its registration into the world, and its layer)",
)
class CreateAnnotationInput:
    """Input for drawing an annotation into a collection or onto a scene."""

    collection: strawberry.ID | None = strawberry.field(default=None, description="The annotation collection to draw into. Exclusive with `scene`")
    scene: strawberry.ID | None = strawberry.field(
        default=None,
        description="The scene to draw on. Its annotation collection is reused when it exists; the first annotation mints it -- a coordinate system mirroring the world's axes, an identity registration into the world, and one annotation layer. Exclusive with `collection`",
    )
    kind: enums.RoiKind = strawberry.field(description="The kind of annotation to draw, e.g. 'polygon', 'path', 'point'. This determines how the vectors are interpreted and drawn")
    name: str | None = strawberry.field(default=None, description="Optional name for the annotation. Defaults to a name derived from its collection")
    description: str | None = strawberry.field(default=None, description="A free-form description of the annotation")
    vectors: list[scalars.ThreeDVector] = strawberry.field(default=None, description="The annotation's vertices, in the collection's own coordinates")
    coordinates: list[CoordinateInput] | None = strawberry.field(
        default=None, description="The discrete coordinates this annotation is pinned to, e.g. [{name: 't', value: 0}, {name: 'c', value: 0}]. A coordinate the annotation does not pin is one it spans"
    )
    stroke_color: list[int] | None = strawberry.field(default=None, description="Stroke (outline) color of the geometry, as RGBA (default white)")
    fill_color: list[int] | None = strawberry.field(default=None, description="Fill color of the geometry, as RGBA, or null for no fill")
    stroke_width: float | None = strawberry.field(default=None, description="Stroke width, in the drawing space's units (default 1.0)")
    filled: bool | None = strawberry.field(default=None, description="Whether the geometry is filled with fill_color (default false)")


def _mint_scene_collection(scene: "models.Scene", ctx: CreationContext) -> "models.AnnotationCollection":
    """The scene's default drawing surface: collection + system + registration + layer, atomically.

    The world's axes are copied onto the collection's own system, which is exactly the
    claim the identity registration then makes -- so the edge is exact by construction
    and wears VALIDATED, like the physical-space mirror in the scene bootstrap. The RFC-6
    collision guard runs inside ``create_identity_registration``; a fresh collection is
    a fresh claim root, so it never collides.
    """
    world = scene.world
    if world is None:
        raise ValueError(f"Scene {scene.pk} has no world coordinate system to draw in.")
    world_axes = list(world.axes.all())

    collection = models.AnnotationCollection.objects.create(
        name=f"{scene.name}/annotations",
        scene=scene,
        creator=ctx.user,
        organization=ctx.organization,
        **ctx.provenance_kwargs(),
    )
    system = graph_logic.create_collection_system(
        name=f"{collection.name}/drawing",
        axes=[AxisInputModel(name=axis.name, type=enums.AxisType(axis.type), long_name=axis.long_name, description=axis.description) for axis in world_axes],
        owner=collection,
        ctx=ctx,
    )
    # Named now, while the answer is unambiguous, because every box this collection stores is
    # a set of numbers against it. Recovering it later means re-walking the chain, and a
    # second copy of that walk is a second chance to name the wrong frame. Stored only when
    # the frame is a system *other* than this collection's own -- see the field, where a
    # self-reference under PROTECT would make the collection undeletable.
    frame = graph_logic.intrinsic_frame(system)
    if frame is not None and frame.pk != system.pk:
        collection.bbox_system = frame
        collection.save_without_historical_record(update_fields=["bbox_system"])

    graph_logic.create_identity_registration(
        input_system=system,
        world=world,
        shared=[axis.name for axis in world_axes],
        name=f"{collection.name} -> {scene.name} (drawn)",
        validity=enums.PlacementValidityChoices.VALIDATED.value,
        ctx=ctx,
    )
    models.Layer.objects.create(
        kind=enums.LayerKind.ANNOTATION,
        scene=scene,
        annotation_collection=collection,
        blending=enums.Blending.NORMAL,
        opacity=1.0,
        visible=True,
        order=0,
    )
    return collection


def _find_or_mint_scene_collection(scene: "models.Scene", ctx: CreationContext) -> "models.AnnotationCollection":
    """The scene's annotation collection, minting it on first use.

    The OneToOne on ``AnnotationCollection.scene`` is what makes this race-safe: a
    concurrent first draw loses on the unique constraint, and the loser re-reads the
    winner's collection instead of forking the scene's annotations.
    """
    existing = getattr(scene, "annotation_collection", None)
    if existing is not None:
        return existing
    try:
        with transaction.atomic():
            return _mint_scene_collection(scene, ctx)
    except IntegrityError:
        scene.refresh_from_db()
        existing = getattr(scene, "annotation_collection", None)
        if existing is None:
            raise
        return existing


def create_annotation(
    info: Info,
    input: CreateAnnotationInput,
) -> types.Annotation:
    """Draw an annotation into a collection or onto a scene, and derive its bounding box."""
    model = input.to_pydantic()

    if bool(model.collection) == bool(model.scene):
        raise ValueError("Provide exactly one of `collection` or `scene`: an annotation is drawn into a collection, and a scene names the collection minted for it.")

    ctx = CreationContext.from_info(info)

    if model.collection:
        collection = get_for_org(models.AnnotationCollection, info, id=model.collection)
    else:
        scene = get_for_org(models.Scene, info, id=model.scene)
        collection = _find_or_mint_scene_collection(scene, ctx)

    system = collection.coordinate_system_or_none
    if system is None:
        raise ValueError(f"Annotation collection {collection.pk} has no coordinate system to draw in.")

    vectors = model.vectors or []

    # Pushed through every corner of the box, not just the two extremes: an
    # affine-transformed AABB is not an AABB, and min/max alone is strictly too
    # small under any rotation or shear. Intrinsic, not world -- see Annotation.
    intrinsic_bbox = graph_logic.compute_intrinsic_bbox(system, vectors)

    annotation = models.Annotation.objects.create(
        collection=collection,
        name=model.name or f"Annotation in {collection.name}",
        description=model.description,
        kind=model.kind.value,
        vectors=vectors,
        # Stored keyed by coordinate name -- the same shape as
        # CoordinateAnchor.coordinates, and GIN-queryable. The API keeps the
        # typed list shape.
        coordinates={coordinate.name: coordinate.value for coordinate in (model.coordinates or [])},
        intrinsic_bbox=intrinsic_bbox,
        # The same box again as a Postgres cube: the GiST-indexed search copy.
        bbox_cube=intrinsic_bbox,
        created_with_transforms=graph_logic.transform_version(system),
        stroke_color=model.stroke_color if model.stroke_color is not None else [255, 255, 255, 255],
        fill_color=model.fill_color,
        stroke_width=model.stroke_width if model.stroke_width is not None else 1.0,
        filled=model.filled if model.filled is not None else False,
        creator=ctx.user,
        **ctx.provenance_kwargs(),
    )

    return annotation


class UpdateAnnotationInputModel(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None
    kind: enums.RoiKind | None = None
    vectors: list[list[float]] | None = None
    coordinates: list[CoordinateInputModel] | None = None
    stroke_color: list[int] | None = None
    fill_color: list[int] | None = None
    stroke_width: float | None = None
    filled: bool | None = None


@kante.pydantic_input(UpdateAnnotationInputModel, description="Input for editing an annotation. Only the supplied fields change; new vectors re-derive the bounding box against the current transform chain")
class UpdateAnnotationInput:
    """Input for editing an annotation."""

    id: strawberry.ID = strawberry.field(description="The ID of the annotation to edit")
    name: str | None = strawberry.field(default=None, description="A new name for the annotation")
    description: str | None = strawberry.field(default=None, description="A new description for the annotation")
    kind: enums.RoiKind | None = strawberry.field(default=None, description="A new kind, changing how the vectors are interpreted")
    vectors: list[scalars.ThreeDVector] | None = strawberry.field(default=None, description="Replacement vertices, in the collection's own coordinates. The bounding box is re-derived")
    coordinates: list[CoordinateInput] | None = strawberry.field(default=None, description="Replacement coordinate pins. The whole set is replaced, not merged")
    stroke_color: list[int] | None = strawberry.field(default=None, description="A new stroke (outline) color, as RGBA")
    fill_color: list[int] | None = strawberry.field(default=None, description="A new fill color, as RGBA")
    stroke_width: float | None = strawberry.field(default=None, description="A new stroke width, in the drawing space's units")
    filled: bool | None = strawberry.field(default=None, description="Whether the geometry is filled with fill_color")


def update_annotation(info: Info, input: UpdateAnnotationInput) -> types.Annotation:
    """Edit an annotation: the CRUD half of being human-drawn."""
    model = input.to_pydantic()

    annotation = get_for_org(models.Annotation, info, id=model.id)

    if model.name is not None:
        annotation.name = model.name
    if model.description is not None:
        annotation.description = model.description
    if model.kind is not None:
        annotation.kind = model.kind.value
    if model.coordinates is not None:
        annotation.coordinates = {coordinate.name: coordinate.value for coordinate in model.coordinates}
    if model.stroke_color is not None:
        annotation.stroke_color = model.stroke_color
    if model.fill_color is not None:
        annotation.fill_color = model.fill_color
    if model.stroke_width is not None:
        annotation.stroke_width = model.stroke_width
    if model.filled is not None:
        annotation.filled = model.filled
    if model.vectors is not None:
        annotation.vectors = model.vectors
        system = annotation.collection.coordinate_system_or_none
        if system is None:
            raise ValueError(f"Annotation collection {annotation.collection.pk} has no coordinate system to derive a bounding box in.")
        annotation.intrinsic_bbox = graph_logic.compute_intrinsic_bbox(system, model.vectors)
        annotation.bbox_cube = annotation.intrinsic_bbox
        annotation.created_with_transforms = graph_logic.transform_version(system)

    annotation.save()
    return annotation


class AnnotationSpecInputModel(BaseModel):
    kind: enums.RoiKind
    name: str | None = None
    description: str | None = None
    vectors: list[list[float]] | None = None
    coordinates: list[CoordinateInputModel] | None = None
    stroke_color: list[int] | None = None
    fill_color: list[int] | None = None
    stroke_width: float | None = None
    filled: bool | None = None


@kante.pydantic_input(AnnotationSpecInputModel, description="One shape of a bulk draw: the per-annotation subset of CreateAnnotationInput, without the collection/scene target")
class AnnotationSpecInput:
    """Input for one shape within a bulk annotation draw."""

    kind: enums.RoiKind = strawberry.field(description="The kind of annotation to draw, e.g. 'polygon', 'path', 'point'. This determines how the vectors are interpreted and drawn")
    name: str | None = strawberry.field(default=None, description="Optional name for the annotation. Defaults to a name derived from its collection")
    description: str | None = strawberry.field(default=None, description="A free-form description of the annotation")
    vectors: list[scalars.ThreeDVector] = strawberry.field(default=None, description="The annotation's vertices, in the collection's own coordinates")
    coordinates: list[CoordinateInput] | None = strawberry.field(default=None, description="The discrete coordinates this annotation is pinned to. A coordinate the annotation does not pin is one it spans")
    stroke_color: list[int] | None = strawberry.field(default=None, description="Stroke (outline) color of the geometry, as RGBA (default white)")
    fill_color: list[int] | None = strawberry.field(default=None, description="Fill color of the geometry, as RGBA, or null for no fill")
    stroke_width: float | None = strawberry.field(default=None, description="Stroke width, in the drawing space's units (default 1.0)")
    filled: bool | None = strawberry.field(default=None, description="Whether the geometry is filled with fill_color (default false)")


class CreateAnnotationsInputModel(BaseModel):
    collection: str | None = None
    scene: str | None = None
    annotations: list[AnnotationSpecInputModel]


@kante.pydantic_input(
    CreateAnnotationsInputModel,
    description="Input for drawing many annotations in one call. Provide exactly one of `collection` or `scene` (same semantics as createAnnotation); the transform chain and version resolve once for the whole batch",
)
class CreateAnnotationsInput:
    """Input for drawing many annotations into one collection or onto one scene."""

    collection: strawberry.ID | None = strawberry.field(default=None, description="The annotation collection to draw into. Exclusive with `scene`")
    scene: strawberry.ID | None = strawberry.field(default=None, description="The scene to draw on; its annotation collection is reused or minted exactly as createAnnotation does. Exclusive with `collection`")
    annotations: list[AnnotationSpecInput] = strawberry.field(description="The shapes to draw, in order")


def create_annotations(
    info: Info,
    input: CreateAnnotationsInput,
) -> list[types.Annotation]:
    """Draw many annotations in one call: one collection resolve, one chain resolve, one insert.

    The per-batch work (find-or-mint the collection, resolve the transform chain,
    read the transform version) happens once; the per-shape work is pure geometry.
    History rows are written through simple_history's bulk path, which fires the
    same pre-create hook single creates do, so provenance attribution is intact.
    """
    model = input.to_pydantic()

    if bool(model.collection) == bool(model.scene):
        raise ValueError("Provide exactly one of `collection` or `scene`: an annotation is drawn into a collection, and a scene names the collection minted for it.")

    ctx = CreationContext.from_info(info)

    if model.collection:
        collection = get_for_org(models.AnnotationCollection, info, id=model.collection)
    else:
        scene = get_for_org(models.Scene, info, id=model.scene)
        collection = _find_or_mint_scene_collection(scene, ctx)

    system = collection.coordinate_system_or_none
    if system is None:
        raise ValueError(f"Annotation collection {collection.pk} has no coordinate system to draw in.")

    chain = graph_logic.intrinsic_chain(system)
    version = graph_logic.transform_version(system)

    rows = []
    for spec in model.annotations:
        vectors = spec.vectors or []
        bbox = graph_logic.bbox_along_chain(chain, vectors)
        rows.append(
            models.Annotation(
                collection=collection,
                name=spec.name or f"Annotation in {collection.name}",
                description=spec.description,
                kind=spec.kind.value,
                vectors=vectors,
                coordinates={coordinate.name: coordinate.value for coordinate in (spec.coordinates or [])},
                intrinsic_bbox=bbox,
                bbox_cube=bbox,
                created_with_transforms=version,
                stroke_color=spec.stroke_color if spec.stroke_color is not None else [255, 255, 255, 255],
                fill_color=spec.fill_color,
                stroke_width=spec.stroke_width if spec.stroke_width is not None else 1.0,
                filled=spec.filled if spec.filled is not None else False,
                creator=ctx.user,
                **ctx.provenance_kwargs(),
            )
        )

    with transaction.atomic():
        return bulk_create_with_history(rows, models.Annotation)


class DeleteAnnotationInputModel(BaseModel):
    id: str


@kante.pydantic_input(DeleteAnnotationInputModel, description="Input for deleting an annotation by ID")
class DeleteAnnotationInput:
    """Input for deleting an annotation by ID."""

    id: strawberry.ID = strawberry.field(description="The ID of the annotation to delete")


delete_annotation = make_delete(models.Annotation, DeleteAnnotationInput, owner=self_owner)
