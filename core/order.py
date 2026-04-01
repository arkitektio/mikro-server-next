import kante
import strawberry_django
from core import models
from strawberry import auto


@strawberry_django.order_type(models.Scene)
class SceneOrder:
    name: auto
    id: auto
