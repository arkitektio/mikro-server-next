from typing import AsyncGenerator

import strawberry
import strawberry_django
from kante.types import Info
from core import models, scalars, types, channels


@strawberry.type
class AffineTransformationViewEvent:
    create: types.AffineTransformationView | None = None
    delete: strawberry.ID | None = None
    update: types.AffineTransformationView | None = None
   


async def affine_transformation_views(
    self,
    info: Info,
    stage: strawberry.ID
) -> AsyncGenerator[AffineTransformationViewEvent, None]:
    """Join and subscribe to message sent to the given rooms."""

    lchannels = ["stage_view_" + str(stage)]
    
    print("Subscribing to affine_transformation_views channel with rooms:", lchannels)

    async for message in channels.affine_transformation_view_channel.listen(info.context, lchannels):
        print("Received message in affine_transformation_views:", message)
        
        
        print("Message content:", message)
        
        if message.create:
            roi = await models.AffineTransformationView.objects.aget(id=message.create)
            yield AffineTransformationViewEvent(create=roi)

        elif message.delete is not None:
            yield AffineTransformationViewEvent(delete=message.delete)

        elif message.update:
            update = await models.AffineTransformationView.objects.aget(id=message.update)
            yield AffineTransformationViewEvent(update=roi)
