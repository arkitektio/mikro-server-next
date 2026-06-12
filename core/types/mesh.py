from strawberry import auto
from core import models, filters
import kante
from datalayer.types import BigFileStore

from core import order


@kante.django_type(models.Mesh, filters=filters.MeshFilter, ordering=order.MeshOrder, pagination=True)
class Mesh:
    id: auto
    name: str
    store: BigFileStore
