from kante.types import Info
from typing import AsyncGenerator
import strawberry
from strawberry_django.optimizer import DjangoOptimizerExtension

from core.datalayer import DatalayerExtension
from core.channel import image_listen
from strawberry import ID
from kante.directives import upper, replace, relation
from strawberry.permission import BasePermission
from typing import Any, Type
from core import types, models
from core import mutations
from core import queries
from core import subscriptions
from strawberry.field_extensions import InputMutationExtension
import strawberry_django
from koherent.strawberry.extension import KoherentExtension
from authentikate.strawberry.permissions import IsAuthenticated, NeedsScopes, HasScopes
from core.render.objects import types as render_types

@strawberry.type
class Query:
    images: list[types.Image] = strawberry.django.field(extensions=[])
    rois: list[types.ROI] = strawberry_django.field()
    myimages: list[types.Image] = strawberry.django.field(extensions=[])
    datasets: list[types.Dataset] = strawberry_django.field()
    mydatasets: list[types.Dataset] = strawberry_django.field()
    timepoint_views: list[types.TimepointView] = strawberry_django.field()
    label_views: list[types.LabelView] = strawberry_django.field()
    channel_views: list[types.ChannelView] = strawberry_django.field()
    continous_scan_views: list[types.ContinousScanView] = strawberry_django.field()
    well_position_views: list[types.WellPositionView] = strawberry_django.field()
    acquisition_views: list[types.AcquisitionView] = strawberry_django.field()
    rgb_views: list[types.RGBView] = strawberry_django.field()
    affine_transformation_views: list[
        types.AffineTransformationView
    ] = strawberry_django.field()
    eras: list[types.Era] = strawberry_django.field()
    myeras: list[types.Era] = strawberry_django.field()
    fluorophores: list[types.Fluorophore] = strawberry_django.field()
    antibodies: list[types.Antibody] = strawberry_django.field()

    stages: list[types.Stage] = strawberry_django.field()
    render_trees: list[types.RenderTree] = strawberry_django.field()

    channels: list[types.Channel] = strawberry_django.field()
    rgbcontexts: list[types.RGBContext] = strawberry_django.field()
    mychannels: list[types.Channel] = strawberry_django.field()
    instruments: list[types.Instrument] = strawberry_django.field()
    instruments: list[types.Instrument] = strawberry_django.field()
    multi_well_plates: list[types.MultiWellPlate] = strawberry_django.field()
    objectives: list[types.Objective] = strawberry_django.field()
    myobjectives: list[types.Objective] = strawberry_django.field()

    tables: list[types.Table] = strawberry_django.field()
    mytables: list[types.Table] = strawberry_django.field()

    snapshots: list[types.Snapshot] = strawberry_django.field()
    mysnapshots: list[types.Snapshot] = strawberry_django.field()

    files: list[types.File] = strawberry_django.field()
    myfiles: list[types.File] = strawberry_django.field()
    random_image: types.Image = strawberry_django.field(resolver=queries.random_image)

    @strawberry.django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def image(self, info: Info, id: ID) -> types.Image:
        print(id)
        return models.Image.objects.get(id=id)
    
    @strawberry.django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def roi(self, info: Info, id: ID) -> types.ROI:
        print(id)
        return models.ROI.objects.get(id=id)
    
    @strawberry.django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def render_tree(self, info: Info, id: ID) -> types.RenderTree:
        print(id)
        return models.RenderTree.objects.get(id=id)

    @strawberry.django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def fluorophore(self, info: Info, id: ID) -> types.Fluorophore:
        print(id)
        return models.Fluorophore.objects.get(id=id)

    @strawberry.django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def rgbcontext(self, info: Info, id: ID) -> types.RGBContext:
        print(id)
        return models.RGBRenderContext.objects.get(id=id)

    @strawberry.django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def objective(self, info: Info, id: ID) -> types.Objective:
        print(id)
        return models.Objective.objects.get(id=id)

    @strawberry.django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def camera(self, info: Info, id: ID) -> types.Camera:
        print(id)
        return models.Camera.objects.get(id=id)

    @strawberry.django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def snapshot(self, info: Info, id: ID) -> types.Snapshot:
        print(id)
        return models.Snapshot.objects.get(id=id)

    @strawberry.django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def file(self, info: Info, id: ID) -> types.File:
        print(id)
        return models.File.objects.get(id=id)

    @strawberry_django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def table(self, info: Info, id: ID) -> types.Table:
        print(id)
        return models.Table.objects.get(id=id)

    @strawberry.django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def instrument(self, info: Info, id: ID) -> types.Instrument:
        print(id)
        return models.Instrument.objects.get(id=id)

    @strawberry.django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def dataset(self, info: Info, id: ID) -> types.Dataset:
        return models.Dataset.objects.get(id=id)

    @strawberry.django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def multi_well_plate(self, info: Info, id: ID) -> types.MultiWellPlate:
        return models.MultiWellPlate.objects.get(id=id)

    @strawberry.django.field(
        permission_classes=[IsAuthenticated, NeedsScopes("openid")]
    )
    def stage(self, info: Info, id: ID) -> types.Stage:
        return models.Stage.objects.get(id=id)


@strawberry.type
class Mutation:
    relate_to_dataset: types.Image = strawberry_django.mutation(
        extensions=[InputMutationExtension()], resolver=mutations.relate_to_dataset
    )

    # IMage
    request_upload: types.Credentials = strawberry_django.mutation(
        resolver=mutations.request_upload
    )
    request_access: types.AccessCredentials = strawberry_django.mutation(
        resolver=mutations.request_access,
        description=mutations.request_access.__doc__,
    )
    from_array_like = strawberry_django.mutation(
        resolver=mutations.from_array_like,
    )
    pin_image = strawberry_django.mutation(
        resolver=mutations.pin_image,
    )
    update_image = strawberry_django.mutation(
        resolver=mutations.update_image,
    )

    create_render_tree = strawberry_django.mutation(
        resolver=mutations.create_render_tree,
    )



    request_media_upload: types.PresignedPostCredentials = strawberry_django.mutation(
        resolver=mutations.request_media_upload
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
    request_file_upload_presigned: types.PresignedPostCredentials = strawberry_django.mutation(
        resolver=mutations.request_file_upload_presigned
    )
    request_file_access: types.AccessCredentials = strawberry_django.mutation(
        resolver=mutations.request_file_access
    )
    from_file_like = strawberry_django.mutation(
        resolver=mutations.from_file_like,
    )

    # Channel
    create_channel = strawberry_django.mutation(
        resolver=mutations.create_channel,
    )
    pin_channel = strawberry_django.mutation(
        resolver=mutations.pin_channel,
    )

    ensure_channel = strawberry_django.mutation(
        resolver=mutations.ensure_channel,
    )
    delete_channel = strawberry_django.mutation(
        resolver=mutations.delete_channel,
    )

    # Stage
    create_stage = strawberry_django.mutation(
        resolver=mutations.create_stage,
    )
    pin_stage = strawberry_django.mutation(
        resolver=mutations.pin_stage,
    )
    delete_stage = strawberry_django.mutation(
        resolver=mutations.delete_stage,
    )

     # RGBContext
    create_rgb_context = strawberry_django.mutation(
        resolver=mutations.create_rgb_context,
    )
    delete_rgb_context = strawberry_django.mutation(
        resolver=mutations.delete_rgb_context,
    )
    update_rgb_context = strawberry_django.mutation(
        resolver=mutations.update_rgb_context,
        description="Update RGB Context"
    )

    # Dataset
    create_dataset = strawberry_django.mutation(
        resolver=mutations.create_dataset,
    )
    update_dataset = strawberry_django.mutation(
        resolver=mutations.update_dataset,
    )
    revert_dataset = strawberry_django.mutation(
        resolver=mutations.revert_dataset,
    )
    pin_dataset = strawberry_django.mutation(
        resolver=mutations.pin_dataset,
    )
    delete_dataset = strawberry_django.mutation(
        resolver=mutations.delete_dataset,
    )
    put_datasets_in_dataset = strawberry_django.mutation(
        resolver=mutations.put_datasets_in_dataset,
    )
    release_datasets_from_dataset = strawberry_django.mutation(
        resolver=mutations.release_datasets_from_dataset,
    )
    put_images_in_dataset = strawberry_django.mutation(
        resolver=mutations.put_images_in_dataset,
    )
    release_images_from_dataset = strawberry_django.mutation(
        resolver=mutations.release_images_from_dataset,
    )
    put_files_in_dataset = strawberry_django.mutation(
        resolver=mutations.put_files_in_dataset,
    )
    release_files_from_dataset = strawberry_django.mutation(
        resolver=mutations.release_files_from_dataset,
    )

    # Fluorophore

    create_fluorophore = strawberry_django.mutation(
        resolver=mutations.create_fluorophore,
    )
    ensure_fluorophore = strawberry_django.mutation(
        resolver=mutations.ensure_fluorophore,
    )
    pin_fluorophore = strawberry_django.mutation(
        resolver=mutations.pin_fluorophore,
    )
    delete_fluorophore = strawberry_django.mutation(
        resolver=mutations.delete_fluorophore,
    )

    # MultiWellPlate

    create_multi_well_plate = strawberry_django.mutation(
        resolver=mutations.create_multi_well_plate,
    )
    ensure_multi_well_plate = strawberry_django.mutation(
        resolver=mutations.ensure_multi_well_plate,
    )
    pin_multi_well_plate = strawberry_django.mutation(
        resolver=mutations.pin_multi_well_plate,
    )
    delete_multi_well_plate = strawberry_django.mutation(
        resolver=mutations.delete_multi_well_plate,
    )

    # Antibody
    ensure_antibody = strawberry_django.mutation(
        resolver=mutations.ensure_antibody,
    )
    create_antibody = strawberry_django.mutation(
        resolver=mutations.create_antibody,
    )
    pin_antibody = strawberry_django.mutation(
        resolver=mutations.pin_antibody,
    )
    delete_antibody = strawberry_django.mutation(
        resolver=mutations.delete_antibody,
    )

    # View Collection
    create_view_collection = strawberry_django.mutation(
        resolver=mutations.create_view_collection,
    )
    pin_view_collection = strawberry_django.mutation(
        resolver=mutations.pin_view_collection,
    )
    delete_view_collection = strawberry_django.mutation(
        resolver=mutations.delete_view_collection,
    )

    # Era
    create_era = strawberry_django.mutation(
        resolver=mutations.create_era,
    )
    pin_era = strawberry_django.mutation(
        resolver=mutations.pin_era,
    )
    delete_era = strawberry_django.mutation(
        resolver=mutations.delete_era,
    )

    # Views
    create_label_view = strawberry_django.mutation(
        resolver=mutations.create_label_view,
    )
    create_timepoint_view = strawberry_django.mutation(
        resolver=mutations.create_timepoint_view,
    )
    create_optics_view = strawberry_django.mutation(
        resolver=mutations.create_optics_view,
    )
    create_rgb_view = strawberry_django.mutation(
        resolver=mutations.create_rgb_view,
    )
    create_channel_view = strawberry_django.mutation(
        resolver=mutations.create_channel_view
    )
    create_well_position_view = strawberry_django.mutation(
        resolver=mutations.create_well_position_view
    )
    create_continous_scan_view = strawberry_django.mutation(
        resolver=mutations.create_continous_scan_view
    )
    create_affine_transformation_view: types.AffineTransformationView = (
        strawberry_django.mutation(resolver=mutations.create_affine_transformation_view)
    )
    delete_affine_transformation_view = strawberry_django.mutation(
        resolver=mutations.delete_affine_transformation_view
    )
    delete_channel_view = strawberry_django.mutation(
        resolver=mutations.delete_channel_view,
    )
    delete_timepoint_view = strawberry_django.mutation(
        resolver=mutations.delete_timepoint_view,
    )
    delete_optics_view = strawberry_django.mutation(
        resolver=mutations.delete_optics_view,
    )
    delete_rgb_view = strawberry_django.mutation(
        resolver=mutations.delete_rgb_view,
    )

    delete_view = strawberry_django.mutation(
        resolver=mutations.delete_view,
    )
    pin_view = strawberry_django.mutation(
        resolver=mutations.pin_view,
    )

    # Label
    create_instrument = strawberry_django.mutation(
        resolver=mutations.create_instrument,
    )
    delete_instrument = strawberry_django.mutation(
        resolver=mutations.delete_instrument,
    )
    pin_instrument = strawberry_django.mutation(
        resolver=mutations.pin_instrument,
    )

    ensure_instrument = strawberry_django.mutation(
        resolver=mutations.ensure_instrument,
    )

    # Objective
    create_objective = strawberry_django.mutation(
        resolver=mutations.create_objective,
    )
    delete_objective = strawberry_django.mutation(
        resolver=mutations.delete_objective,
    )
    pin_objective = strawberry_django.mutation(
        resolver=mutations.pin_objective,
    )
    ensure_objective = strawberry_django.mutation(
        resolver=mutations.ensure_objective,
    )

    # Camera
    create_camera = strawberry_django.mutation(
        resolver=mutations.create_camera,
    )
    delete_camera = strawberry_django.mutation(
        resolver=mutations.delete_camera,
    )
    pin_camera = strawberry_django.mutation(
        resolver=mutations.pin_camera,
    )
    ensure_camera = strawberry_django.mutation(
        resolver=mutations.ensure_camera,
    )

    # Snapshot
    create_snapshot = strawberry_django.mutation(
        resolver=mutations.create_snapshot,
    )
    delete_snapshot = strawberry_django.mutation(
        resolver=mutations.delete_snapshot,
    )
    pin_snapshot = strawberry_django.mutation(
        resolver=mutations.pin_snapshot,
    )

    # Roi
    create_roi = strawberry_django.mutation(
        resolver=mutations.create_roi,
    )
    delete_roi = strawberry_django.mutation(
        resolver=mutations.delete_roi,
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


    rois = strawberry.subscription(resolver=subscriptions.rois)
    


schema = strawberry.Schema(
    query=Query,
    subscription=Subscription,
    mutation=Mutation,
    directives=[upper, replace, relation],
    extensions=[
        DjangoOptimizerExtension,
        KoherentExtension,
        DatalayerExtension,
    ],
    types=[
        types.RenderNode,
        types.ContextNode,
        types.OverlayNode,
        types.GridNode,
        types.SplitNode,
    ]
)
