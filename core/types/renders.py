import strawberry
from strawberry import auto
from core import models, filters
import datetime
from enum import Enum
import kante
from datalayer.types import MediaStore

from core import order

from core.types.auth import Task, User


@strawberry.enum
class RenderKind(str, Enum):
    """The kind of render.

    Renders can be of different kinds. For example, a render can be a snapshot
    that will map a specific image to a specific timepoint. Or a render can be
    a video that will render a 5D image to a 4D video.
    """

    VIDEO = "videos"
    SNAPSHOT = "snapshots"


# The render relations on Image, derived from RenderKind: the enum values are
# the Django related names (GraphQL clients only ever see the member names).
IMAGE_RENDER_RELATIONS: list[str] = [kind.value for kind in RenderKind]


@kante.django_interface(models.Render)
class Render:
    created_at: datetime.datetime
    creator: User | None
    created_through: Task | None = kante.django_field(description="The task this render was created through, if any")
    created_through_by: User | None = kante.django_field(description="The assigner of the creating task, if any")


@kante.django_type(
    models.Snapshot,
    filters=filters.SnapshotFilter,
    ordering=order.SnapshotOrder,
    pagination=True,
    description="A snapshot is a pre-rendered thumbnail image of an image. Clients use snapshots to display previews without loading the full underlying data.",
)
class Snapshot(Render):
    """A snapshot is a pre-rendered thumbnail image of an image. Clients use snapshots to display previews without loading the full underlying data."""

    id: auto
    store: MediaStore
    name: str
    major_color: list[float] | None


@kante.django_type(
    models.Video,
    pagination=True,
    description="A video is a rendered video of an image, accompanied by a thumbnail. Clients use videos to play back multidimensional image data without loading the raw arrays.",
)
class Video(Render):
    """A video is a rendered video of an image, accompanied by a thumbnail. Clients use videos to play back multidimensional image data without loading the raw arrays."""

    id: auto
    store: MediaStore
    thumbnail: MediaStore
