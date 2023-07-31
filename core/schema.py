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
from core import mutations
from strawberry.field_extensions import InputMutationExtension
import strawberry_django
from koherent.extensions import KoherentExtension


class IsAuthenticated(BasePermission):
    message = "User is not authenticated"

    # This method can also be async!
    def has_permission(self, source: Any, info: Info, **kwargs) -> bool:
        return info.context.user.is_authenticated


class IsAuthenticated(BasePermission):
    message = "User is not authenticated"

    # This method can also be async!
    def has_permission(self, source: Any, info: Info, **kwargs) -> bool:
        return info.context.request.user.is_authenticated


class HasScopes(BasePermission):
    message = "User is not authenticated"
    checked_scopes = []

    # This method can also be async!
    def has_permission(self, source: Any, info: Info, **kwargs) -> bool:
        print(info.context.request.scopes)
        return info.context.request.has_scopes(self.checked_scopes)


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
    datasets: list[types.Dataset] = strawberry_django.field()
    timepoint_views: list[types.TimepointView] = strawberry_django.field()
    label_views: list[types.LabelView] = strawberry_django.field()
    channel_views: list[types.ChannelView] = strawberry_django.field()
    transformation_views: list[types.TransformationView] = strawberry_django.field()
    eras: list[types.Era] = strawberry_django.field()
    fluorophores: list[types.Fluorophore] = strawberry_django.field()
    antibodies: list[types.Antibody] = strawberry_django.field()

    channels: list[types.Channel] = strawberry_django.field()
    instruments: list[types.Instrument] = strawberry_django.field()

    @strawberry.django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def image(self, info, id: ID) -> types.Image:
        print(id)
        return models.Image.objects.get(id=id)

    @strawberry.django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def objective(self, info, id: ID) -> types.Objective:
        print(id)
        return models.Objective.objects.get(id=id)

    @strawberry.django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def camera(self, info, id: ID) -> types.Camera:
        print(id)
        return models.Camera.objects.get(id=id)
    
    @strawberry.django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def thumbnail(self, info, id: ID) -> types.Thumbnail:
        print(id)
        return models.Thumbnail.objects.get(id=id)
    
    @strawberry.django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def file(self, info, id: ID) -> types.File:
        print(id)
        return models.File.objects.get(id=id)
    
    @strawberry.django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def table(self, info, id: ID) -> types.Table:
        print(id)
        return models.Table.objects.get(id=id)

    @strawberry.django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def instrument(self, info, id: ID) -> types.Instrument:
        print(id)
        return models.Instrument.objects.get(id=id)

    @strawberry.django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def dataset(self, info, id: ID) -> types.Dataset:
        return models.Dataset.objects.get(id=id)


@strawberry.type
class Mutation:
    set_other_as_origin: types.Image = strawberry_django.mutation(
        extensions=[InputMutationExtension()], resolver=mutations.set_other_as_origin
    )
    relate_to_dataset: types.Image = strawberry_django.mutation(
        extensions=[InputMutationExtension()], resolver=mutations.relate_to_dataset
    )
    request_upload: types.Credentials = strawberry_django.mutation(
        resolver=mutations.request_upload
    )
    request_access: types.AccessCredentials = strawberry_django.mutation(
        resolver=mutations.request_access
    )
    from_array_like = strawberry_django.mutation(
        resolver=mutations.from_array_like,
    )

    request_table_upload: types.Credentials = strawberry_django.mutation(
        resolver=mutations.request_table_upload
    )
    request_table_access: types.AccessCredentials = strawberry_django.mutation(
        resolver=mutations.request_table_access
    )
    from_parquet_like = strawberry_django.mutation(
        resolver=mutations.from_parquet_like,
    )

    request_file_upload: types.Credentials = strawberry_django.mutation(
        resolver=mutations.request_file_upload
    )
    request_file_access: types.AccessCredentials = strawberry_django.mutation(
        resolver=mutations.request_file_access
    )
    from_file_like = strawberry_django.mutation(
        resolver=mutations.from_file_like,
    )


    create_new_view: types.View = strawberry_django.mutation(
        resolver=mutations.create_new_view
    )
    create_channel_view: types.View = strawberry_django.mutation(
        resolver=mutations.create_channel_view
    )
    create_transformation_view: types.View = strawberry_django.mutation(
        resolver=mutations.create_channel_view
    )
    create_channel = strawberry_django.mutation(
        resolver=mutations.create_channel,
    )
    create_stage = strawberry_django.mutation(
        resolver=mutations.create_stage,
    )
    create_dataset = strawberry_django.mutation(
        resolver=mutations.create_dataset,
    )
    update_dataset = strawberry_django.mutation(
        resolver=mutations.update_dataset,
    )
    revert_dataset = strawberry_django.mutation(
        resolver=mutations.revert_dataset,
    )
    ensure_channel = strawberry_django.mutation(
        resolver=mutations.ensure_channel,
    )
    ensure_fluorophore = strawberry_django.mutation(
        resolver=mutations.ensure_fluorophore,
    )
    create_fluorophore = strawberry_django.mutation(
        resolver=mutations.create_fluorophore,
    )
    ensure_antibody = strawberry_django.mutation(
        resolver=mutations.ensure_antibody,
    )
    create_antibody = strawberry_django.mutation(
        resolver=mutations.create_antibody,
    )
    create_view_collection = strawberry_django.mutation(
        resolver=mutations.create_view_collection,
    )
    create_era = strawberry_django.mutation(
        resolver=mutations.create_era,
    )
    create_label_view = strawberry_django.mutation(
        resolver=mutations.create_label_view,
    )
    create_timepoint_view = strawberry_django.mutation(
        resolver=mutations.create_timepoint_view,
    )
    create_optics_view = strawberry_django.mutation(
        resolver=mutations.create_optics_view,
    )
    create_instrument = strawberry_django.mutation(
        resolver=mutations.create_instrument,
    )
    create_objective = strawberry_django.mutation(
        resolver=mutations.create_objective,
    )
    create_camera = strawberry_django.mutation(
        resolver=mutations.create_camera,
    )
    ensure_camera = strawberry_django.mutation(
        resolver=mutations.ensure_camera,
    )
    ensure_objective = strawberry_django.mutation(
        resolver=mutations.ensure_objective,
    )
    ensure_instrument = strawberry_django.mutation(
        resolver=mutations.ensure_instrument,
    )


    create_thumbnail= strawberry_django.mutation(
        resolver=mutations.create_thumbnail,
    )


@strawberry.type
class ChatRoomMessage:
    room_name: str
    current_user: str
    message: str


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def history_events(
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
        KoherentExtension,
    ],
)
