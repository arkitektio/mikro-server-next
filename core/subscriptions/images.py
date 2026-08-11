from typing import AsyncGenerator

import strawberry
from django.core.exceptions import PermissionDenied
from kante.types import Info
from core import models, types, channels
from core.scoping import aget_for_org, for_org


@strawberry.type
class ImageEvent:
    create: types.Image | None = None
    delete: strawberry.ID | None = None
    update: types.Image | None = None


async def images(
    self,
    info: Info,
    folder: strawberry.ID | None = None,
) -> AsyncGenerator[ImageEvent, None]:
    """Join and subscribe to message sent to the given rooms."""

    if folder is None:
        rooms = [channels.org_images_room(info.context.request.organization.id)]
    else:
        if not await for_org(models.Folder, info).filter(id=folder).aexists():
            raise PermissionDenied("Folder does not exist in this organization")
        rooms = [channels.folder_images_room(folder)]

    async for message in channels.image_channel.listen(info.context, rooms):
        if message.create:
            image = await aget_for_org(models.Image, info, id=message.create)
            yield ImageEvent(create=image)

        elif message.delete:
            yield ImageEvent(delete=message.delete)

        elif message.update:
            image = await aget_for_org(models.Image, info, id=message.update)
            yield ImageEvent(update=image)
