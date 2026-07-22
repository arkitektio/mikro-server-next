"""Human-drawn annotations and the collection that owns their drawing space.

An :class:`Annotation` is the CRUD counterpart of the parquet-backed machine
ROIs a :class:`~core.models.TableDataset` carries: an addressable, mutable,
owned shape a person draws and edits, not a million rows a pipeline emits.
Annotations never stand alone -- each belongs to an
:class:`AnnotationCollection`, and the collection owns its own INTRINSIC
coordinate system exactly like a mesh collection owns its vertex space. How the
drawing space relates to anything else -- a scene's world, a dataset's pixel
grid -- is a :class:`~core.models.Transformation` edge, never a second FK on
the shape.
"""

import uuid

from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.postgres.indexes import GinIndex, GistIndex

from authentikate.models import Organization
from koherent.fields import ProvenanceField
from django_choices_field import TextChoicesField

from core import enums
from core.fields import CubeField


class AnnotationCollection(models.Model):
    """A named set of human-drawn annotations, owning the space they are drawn in.

    The collection is the coordinate-system owner (the FK lives on
    ``CoordinateSystem.annotation_collection``, like every other container), so
    all its annotations share one drawing space and one registration story: the
    collection registers into a world, the shapes just have vectors.

    ``scene`` marks a collection minted as that scene's default drawing surface
    by ``createAnnotation(scene:)`` -- one per scene, enforced by the database.
    It is a bookkeeping FK, not placement: placement is the identity
    registration edge authored into the scene's world when the collection is
    minted. SET_NULL keeps the old invariant that deleting a scene never
    deletes what was drawn: the scene's minted world (and with it the
    registration edge) and the layer cascade away, the collection and its
    annotations survive as a freestanding, re-placeable collection. Two scenes
    composing over one shared hub each mint their *own* collection; scene B
    sees scene A's annotations only through reachability, and renders them only
    once it gets its own layer for A's collection.
    """

    name = models.CharField(max_length=255, help_text="The name of this annotation collection")
    description = models.TextField(null=True, blank=True, help_text="A free-form description of this annotation collection")
    scene = models.OneToOneField(
        "Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="annotation_collection",
        help_text="The scene this collection was minted for as its default drawing surface, if any. One per scene; bookkeeping only, placement is the registration edge",
    )

    created_at = models.DateTimeField(auto_now_add=True, help_text="The time this annotation collection was created")
    creator = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="annotation_collections",
        help_text="The user that created this annotation collection",
    )
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, help_text="The organization this annotation collection belongs to")
    created_through = models.ForeignKey(
        "koherent.Task",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_%(class)ss",
        help_text="The task this object was created through, if any",
    )
    created_through_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_%(class)ss",
        help_text="The assigner of the creating task, denormalized for fast filtering",
    )
    provenance = ProvenanceField()

    class Meta:
        """Meta options for the annotation collection."""

        ordering = ["-created_at"]

    def __str__(self) -> str:
        """The collection's name."""
        return self.name

    @property
    def coordinate_system_or_none(self):
        """The coordinate system this collection owns, or None before it is created."""
        # The reverse of CoordinateSystem.annotation_collection, which raises
        # rather than returning None when the system has not been created yet.
        return getattr(self, "coordinate_system", None)


class Annotation(models.Model):
    """A human-drawn shape: an addressable, mutable, owned entity in its collection's space.

    An annotation belongs to a **collection**, never to a scene. There is no
    ``scene_id`` column here and there must never be one: delete the scene and
    the annotation survives, because the space it is drawn in -- its
    collection's own system -- has not gone anywhere.

    ``intrinsic_bbox`` is the axis-aligned box of the shape in the nearest
    intrinsic space its collection's system can reach (the collection's own
    space when no chain resolves), denormalized for joins and culling. It is
    deliberately *not* a world box: world is scene-owned, and the same
    collection can sit in two scenes under two registrations, so a single
    stored world box would be wrong in one of them.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collection = models.ForeignKey(
        AnnotationCollection,
        related_name="annotations",
        on_delete=models.CASCADE,
        help_text="The collection this annotation belongs to; its geometry is expressed in the collection's own coordinate system",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    kind = TextChoicesField(
        choices_enum=enums.RoiKindChoices,
        default=enums.RoiKindChoices.PATH.value,
        help_text="The geometric kind of the annotation (rectangle, polygon, path, ...), which fixes how its vectors are read",
    )
    # The same shape as CoordinateAnchor.coordinates, deliberately: one canonical
    # representation of "pinned to discrete coordinates", and a dict is
    # GIN-indexed (see Meta) so "every annotation on channel 0" is a containment
    # query. The GraphQL type still ships it as a typed [Coordinate] list.
    coordinates = models.JSONField(
        help_text="The discrete coordinates this annotation is pinned to, keyed by coordinate name, e.g. {'t': 0, 'c': 0}. A coordinate the annotation does not pin is one it spans",
        default=dict,
    )
    vectors = models.JSONField(help_text="A list of the annotation's vectors (specific for each kind), in the collection's coordinate system's own units", default=list)
    intrinsic_bbox = models.JSONField(
        null=True,
        blank=True,
        help_text="The annotation's axis-aligned bounding box in the nearest intrinsic space, as {'min': [...], 'max': [...]}. Derived from all corners of the geometry, never from min/max alone",
    )
    bbox_cube = CubeField(
        null=True,
        blank=True,
        editable=False,
        help_text="The intrinsic bounding box as a Postgres cube, denormalized from intrinsic_bbox at write time for GiST-indexed overlap/containment/nearest search. Write-only: the API reads intrinsic_bbox",
    )
    created_with_transforms = models.PositiveIntegerField(
        default=0,
        help_text="The version of the transformation chain this annotation was authored against. Provenance only: it is never used to resolve a coordinate",
    )

    # Per-shape styling lives here, not on the layer: the layer is one per
    # collection, and shapes within one collection may differ visually.
    stroke_color = models.JSONField(default=None, null=True, blank=True, help_text="The stroke (outline) color of the geometry (RGBA)")
    fill_color = models.JSONField(default=None, null=True, blank=True, help_text="The fill color of the geometry (RGBA), or null for no fill")
    stroke_width = models.FloatField(default=1.0, help_text="The stroke width of the geometry, in the drawing space's units")
    filled = models.BooleanField(default=False, help_text="Whether the geometry is filled with fill_color")

    creator = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="annotations",
        help_text="The user that drew this annotation",
    )
    created_through = models.ForeignKey(
        "koherent.Task",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_%(class)ss",
        help_text="The task this object was created through, if any",
    )
    created_through_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_%(class)ss",
        help_text="The assigner of the creating task, denormalized for fast filtering",
    )

    provenance = ProvenanceField()

    class Meta:
        """Meta options for the annotation: the two search indexes.

        Boxes only compare within one frame (a collection's nearest-intrinsic
        space), so every spatial query the GiST index serves is scoped to a
        collection or coordinate system by the filter layer.
        """

        indexes = [
            GinIndex(fields=["coordinates"], name="annotation_coords_gin"),
            GistIndex(fields=["bbox_cube"], name="annotation_bbox_gist"),
        ]

    def __str__(self) -> str:
        """The annotation's name and kind."""
        return f"{self.name} ({self.kind})"
