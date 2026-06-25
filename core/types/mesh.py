from strawberry import auto
from core import models, filters
import kante
from datalayer.types import BigFileStore

from core import order


@kante.django_type(
    models.Mesh,
    filters=filters.MeshFilter,
    ordering=order.MeshOrder,
    pagination=True,
    description="A 3D mesh belonging to a dataset, with its geometry kept in a big file store. Clients use it to download or visualize surface reconstructions derived from image data.",
)
class Mesh:
    """A 3D mesh belonging to a dataset, with its geometry kept in a big file store. Clients use it to download or visualize surface reconstructions derived from image data."""

    id: auto
    name: str
    store: BigFileStore
