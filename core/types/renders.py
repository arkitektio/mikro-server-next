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
    SNAPSHOT = "snapshot"


@kante.django_interface(models.Render)
class Render:
    created_at: datetime.datetime
    creator: User | None
    created_through: Task | None = kante.django_field(description="The task this render was created through, if any")
    created_through_by: User | None = kante.django_field(description="The assigner of the creating task, if any")


@kante.django_type(models.Snapshot, filters=filters.SnapshotFilter, ordering=order.SnapshotOrder, pagination=True)
class Snapshot(Render):
    id: auto
    store: MediaStore
    name: str
    major_color: list[float] | None


@kante.django_type(models.Video, pagination=True)
class Video(Render):
    id: auto
    store: MediaStore
    thumbnail: MediaStore
