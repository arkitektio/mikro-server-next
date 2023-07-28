from kante.types import Info
from typing import AsyncGenerator
import strawberry
from strawberry_django.optimizer import DjangoOptimizerExtension
from .channel import image_listen
from strawberry_django import mutations
from strawberry import ID
from kante.directives import upper, replace, relation
from strawberry.permission import BasePermission
from typing import Any, Type
from core import types, models, inputs
from core.mutations.image import (
    set_other_as_origin,
    relate_to_dataset,
    request_upload,
    from_array_like,
)
from core.mutations.view import create_new_view, create_new_channel_view
from core.mutations.channel import create_channel
from strawberry.field_extensions import InputMutationExtension
import strawberry_django


class IsAuthenticated(BasePermission):
    message = "User is not authenticated"

    # This method can also be async!
    def has_permission(self, source: Any, info: Info, **kwargs) -> bool:
        print(source, info, kwargs)
        print(info.context.user)
        return info.context.user.is_authenticated


class IsAuthenticated(BasePermission):
    message = "User is not authenticated"

    # This method can also be async!
    def has_permission(self, source: Any, info: Info, **kwargs) -> bool:
        print(source, info, kwargs)
        print(info.context.request.user)
        return info.context.request.user.is_authenticated


class HasScopes(BasePermission):
    message = "User is not authenticated"
    checked_scopes = []

    # This method can also be async!
    def has_permission(self, source: Any, info: Info, **kwargs) -> bool:
        print(source, info, kwargs)
        print(info.context.request.app)
        return info.context.request.app.has_scopes(self.checked_scopes)


def NeedsScopes(scopes: str) -> Type[HasScopes]:
    if isinstance(scopes, str):
        scopes = [scopes]
    return type(
        f"NeedsScopes{'_'.join(scopes)}",
        (HasScopes,),
        dict(
            message=f"App does not have the required scopes: {','.join(scopes)}",
            checked_scopes=scopes,
        ),
    )


@strawberry.type
class Query:
    images: list[types.Image] = strawberry.django.field()
    provenance: list[types.ProvenanceEvent] = strawberry_django.field()
    datasets: list[types.Dataset] = strawberry_django.field()
    views: list[types.View] = strawberry.field()
    channels: list[types.Channel] = strawberry_django.field()
    instruments: list[types.Instrument] = strawberry_django.field()

    @strawberry.django.field(permission_classes=[IsAuthenticated, NeedsScopes("write")])
    def image(self, info, id: ID) -> types.Image:
        print(id)
        return models.Image.objects.get(id=id)


@strawberry.type
class Mutation:
    create_image: types.Image = mutations.create(inputs.ImageInput)
    create_dataset: types.Dataset = mutations.create(inputs.DatasetInput)
    set_other_as_origin: types.Image = strawberry_django.mutation(
        extensions=[InputMutationExtension()], resolver=set_other_as_origin
    )
    relate_to_dataset: types.Image = strawberry_django.mutation(
        extensions=[InputMutationExtension()], resolver=relate_to_dataset
    )
    request_upload: types.Credentials = strawberry_django.mutation(
        extensions=[InputMutationExtension()], resolver=request_upload
    )
    from_array_like = strawberry_django.mutation(
        extensions=[InputMutationExtension()],
        resolver=from_array_like,
    )
    create_new_view: types.View = strawberry_django.mutation(resolver=create_new_view)
    create_new_channel_view: types.View = strawberry_django.mutation(
        resolver=create_new_channel_view
    )
    create_channel = strawberry_django.mutation(
        resolver=create_channel,
    )


@strawberry.type
class ChatRoomMessage:
    room_name: str
    current_user: str
    message: str


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def provenance_events(
        self,
        info: Info,
        user: str,
    ) -> AsyncGenerator[types.Image, None]:
        """Join and subscribe to message sent to the given rooms."""
        async for message in image_listen(info):
            yield await models.Image.objects.aget(id=message)


schema = strawberry.Schema(
    query=Query,
    subscription=Subscription,
    mutation=Mutation,
    directives=[upper, replace, relation],
    extensions=[
        DjangoOptimizerExtension,
    ],
)
