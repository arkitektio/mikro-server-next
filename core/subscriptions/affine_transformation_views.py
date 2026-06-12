from typing import AsyncGenerator

import strawberry
from django.core.exceptions import PermissionDenied
from kante.types import Info
from core import models, types, channels
from core.scoping import aget_for_org, for_org


@strawberry.type
class AffineTransformationViewEvent:
    create: types.AffineTransformationView | None = None
    delete: strawberry.ID | None = None
    update: types.AffineTransformationView | None = None


async def affine_transformation_views(
    self,
    info: Info,
    stage: strawberry.ID,
) -> AsyncGenerator[AffineTransformationViewEvent, None]:
    """Join and subscribe to message sent to the given rooms."""

    if not await for_org(models.Stage, info).filter(id=stage).aexists():
        raise PermissionDenied("Stage does not exist in this organization")

    async for message in channels.affine_transformation_view_channel.listen(info.context, [channels.stage_views_room(stage)]):
        if message.create:
            view = await aget_for_org(models.AffineTransformationView, info, id=message.create)
            yield AffineTransformationViewEvent(create=view)

        elif message.delete is not None:
            yield AffineTransformationViewEvent(delete=message.delete)

        elif message.update:
            view = await aget_for_org(models.AffineTransformationView, info, id=message.update)
            yield AffineTransformationViewEvent(update=view)
