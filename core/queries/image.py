from kante.types import Info
from core import types, models


def random_image(
    info: Info,
) -> types.Image:
    view = models.Image.objects.order_by("?").first()
    return view