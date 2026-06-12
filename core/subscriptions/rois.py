from typing import AsyncGenerator

import strawberry
from django.core.exceptions import PermissionDenied
from kante.types import Info
from core import models, types, channels
from core.scoping import for_org


@strawberry.type
class RoiEvent:
    create: types.ROI | None = None
    delete: strawberry.ID | None = None
    update: types.ROI | None = None


async def rois(
    self,
    info: Info,
    image: strawberry.ID,
) -> AsyncGenerator[RoiEvent, None]:
    """Join and subscribe to message sent to the given rooms."""

    if not await for_org(models.Image, info).filter(id=image).aexists():
        raise PermissionDenied("Image does not exist in this organization")

    async for message in channels.roi_channel.listen(info.context, [channels.image_rois_room(image)]):
        if message.create:
            roi = await for_org(models.ROI, info).prefetch_related("image").aget(id=message.create)
            yield RoiEvent(create=roi)

        elif message.delete:
            yield RoiEvent(delete=message.delete)

        elif message.update:
            roi = await for_org(models.ROI, info).prefetch_related("image").aget(id=message.update)
            yield RoiEvent(update=roi)
