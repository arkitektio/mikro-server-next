from typing import AsyncGenerator

import strawberry
import strawberry_django
from kante.types import Info
from core import models, scalars, types, channels


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

    async for message in channels.roi_channel.listen(info.context, ["image_roi_" + str(image)]):
        if message["type"] == "create":
            roi = await models.ROI.objects.prefetch_related("image").aget(
                id=message["id"]
            )
            yield RoiEvent(create=roi)

        elif message["type"] == "delete":
            yield RoiEvent(delete=message["id"])

        elif message["type"] == "update":
            roi = await models.ROI.objects.prefetch_related("image").aget(
                id=message["id"]
            )
            yield RoiEvent(update=roi)
