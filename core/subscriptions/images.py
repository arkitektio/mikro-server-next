from typing import AsyncGenerator

import strawberry
import strawberry_django
from kante.types import Info
from core import models, scalars, types, channels


@strawberry.type
class ImageEvent:
    create: types.Image | None = None
    delete: strawberry.ID | None = None
    update: types.Image | None = None


async def images(
    self,
    info: Info,
    dataset: strawberry.ID | None = None,
) -> AsyncGenerator[ImageEvent, None]:
    """Join and subscribe to message sent tso the given rooms."""

    if dataset is None:
        schannels = ["images"]
    else:
        schannels = ["dataset_images_" + str(dataset)]

    async for message in channels.image_channel.listen(info.context, schannels):
        if message.create:
            roi = await models.Image.objects.aget(id=message.create)
            yield ImageEvent(create=roi)

        elif message.delete:
            yield ImageEvent(delete=message.delete)

        elif message.update:
            roi = await models.Image.objects.aget(id=message.update)
            yield ImageEvent(update=roi)
