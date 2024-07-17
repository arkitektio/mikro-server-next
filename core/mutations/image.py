from kante.types import Info
import strawberry

from core import types, models, scalars
from core.datalayer import get_current_datalayer
import json
from .view import (
    PartialChannelViewInput,
    PartialLabelViewInput,
    PartialTimepointViewInput,
    PartialRGBViewInput,
    PartialOpticsViewInput,
    PartialAcquisitionViewInput,
    PartialAffineTransformationViewInput,
    view_kwargs_from_input,
)
from django.conf import settings
from django.contrib.auth import get_user_model
from core.managers import auto_create_views
@strawberry.input
class SetAsOriginInput:
    child: strawberry.ID
    origin: bool


def set_other_as_origin(
    info: Info,
    input: SetAsOriginInput,
) -> types.Image:
    image = models.Image.objects.get(id=input.child)
    other = models.Image.objects.get(id=input.origin)

    image.origins.add(other)
    return image


def relate_to_dataset(
    info: Info,
    id: strawberry.ID,
    other: strawberry.ID,
) -> types.Image:
    image = models.Image.objects.get(id=id)
    other = models.Dataset.objects.get(id=other)

    return image


@strawberry.input
class PinImageInput:
    id: strawberry.ID
    pin: bool


def pin_image(
    info: Info,
    input: PinImageInput,
) -> types.Image:
    raise NotImplementedError("TODO")


@strawberry.input
class UpdateImageInput:
    id: strawberry.ID
    tags: list[str] | None = None
    name: str | None = None
    

def update_image(
    info: Info,
    input: UpdateImageInput,
) -> types.Image:
    image = models.Image.objects.get(id=input.id)

    if input.tags:
        image.tags.add(*input.tags)

    if input.name:
        image.name = input.name

    image.save()

    return image


@strawberry.input()
class DeleteImageInput:
    id: strawberry.ID


def delete_image(
    info: Info,
    input: DeleteImageInput,
) -> strawberry.ID:
    item = models.Image.objects.get(id=input.id)
    item.delete()
    return input.id


@strawberry.input()
class RequestUploadInput:
    key: str
    datalayer: str


def request_upload(info: Info, input: RequestUploadInput) -> types.Credentials:
    """Request upload credentials for a given key"""

    datalayer = get_current_datalayer()
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AllowAllS3ActionsInUserFolder",
                "Effect": "Allow",
                "Principal": "*",
                "Action": ["s3:*"],
                "Resource": "arn:aws:s3:::*",
            },
        ],
    }

    response = datalayer.sts.assume_role(
        RoleArn="arn:xxx:xxx:xxx:xxxx",
        RoleSessionName="sdfsdfsdf",
        Policy=json.dumps(policy, separators=(",", ":")),
        DurationSeconds=40000,
    )

    print(response)

    path = f"s3://{settings.ZARR_BUCKET}/{input.key}"

    store = models.ZarrStore.objects.create(
        path=path, key=input.key, bucket=settings.ZARR_BUCKET
    )

    aws = {
        "access_key": response["Credentials"]["AccessKeyId"],
        "secret_key": response["Credentials"]["SecretAccessKey"],
        "session_token": response["Credentials"]["SessionToken"],
        "status": "success",
        "key": input.key,
        "bucket": settings.ZARR_BUCKET,
        "datalayer": input.datalayer,
        "store": store.id,
    }

    return types.Credentials(**aws)


@strawberry.input()
class RequestAccessInput:
    store: strawberry.ID
    duration: int | None = None


def request_access(info: Info, input: RequestAccessInput) -> types.AccessCredentials:
    """Request upload credentials for a given key"""

    store = models.ZarrStore.objects.get(id=input.store)

    sts = get_current_datalayer().sts

    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AllowAllS3ActionsInUserFolder",
                "Effect": "Allow",
                "Principal": "*",
                "Action": ["s3:*"],
                "Resource": "arn:aws:s3:::*",
            },
        ],
    }

    response = sts.assume_role(
        RoleArn="arn:xxx:xxx:xxx:xxxx",
        RoleSessionName="sdfsdfsdf",
        Policy=json.dumps(policy, separators=(",", ":")),
        DurationSeconds=input.duration or 40000,
    )

    aws = {
        "access_key": response["Credentials"]["AccessKeyId"],
        "secret_key": response["Credentials"]["SecretAccessKey"],
        "session_token": response["Credentials"]["SessionToken"],
        "key": store.key,
        "bucket": store.bucket,
        "path": store.path,
    }

    return types.AccessCredentials(**aws)


@strawberry.input
class FromArrayLikeInput:
    name: str
    array: scalars.ArrayLike
    origins: list[strawberry.ID] | None = None
    dataset: strawberry.ID | None = None
    channel_views: list[PartialChannelViewInput] | None = None
    transformation_views: list[PartialAffineTransformationViewInput] | None = None
    acquisition_views: list[PartialAcquisitionViewInput] | None = None
    label_views: list[PartialLabelViewInput] | None = None
    rgb_views: list[PartialRGBViewInput] | None = None
    timepoint_views: list[PartialTimepointViewInput] | None = None
    optics_views: list[PartialOpticsViewInput] | None = None
    tags: list[str] | None = None
    file_origins: list[strawberry.ID] | None = None
    roi_origins: list[strawberry.ID] | None = None


def from_array_like(
    info: Info,
    input: FromArrayLikeInput,
) -> types.Image:
    
    datalayer = get_current_datalayer()

    store = models.ZarrStore.objects.get(id=input.array)
    store.fill_info(datalayer)

    dataset = input.dataset or get_image_dataset(info)

    image = models.Image.objects.create(
        dataset_id=dataset,
        creator=info.context.request.user,
        name=input.name,
        store=store,
    )

    if input.tags:
        image.tags.add(*input.tags)

    print(input)

    if input.origins is not None:
        for origin in input.origins:
            image.origins.add(models.Image.objects.get(id=origin))

    if input.file_origins is not None:
        for origin in input.file_origins:
            image.file_origins.add(models.File.objects.get(id=origin))

    if input.roi_origins is not None:
        for origin in input.roi_origins:
            image.roi_origins.add(models.ROI.objects.get(id=origin))

    if input.channel_views is not None:
        for channelview in input.channel_views:
            models.ChannelView.objects.create(
                image=image,
                channel=models.Channel.objects.get(id=channelview.channel),
                **view_kwargs_from_input(channelview),
            )

    if input.timepoint_views is not None:
        for i, timepoint_view in enumerate(input.timepoint_views):
            models.TimepointView.objects.create(
                image=image,
                era=models.Era.objects.get(id=timepoint_view.era)
                if timepoint_view.era
                else models.Era.objects.create(
                    name=f"Unknown for {image.name} and {i}"
                ),
                **view_kwargs_from_input(channelview),
            )

    if input.label_views is not None:
        for labelview in input.label_views:
            models.LabelView.objects.create(
                image=image,
                fluorophore=models.Fluorophore.objects.get(id=labelview.fluorophore)
                if labelview.fluorophore
                else None,
                primary_antibody_id=labelview.primary_antibody,
                secondary_antibody_id=labelview.secondary_antibody,
                **view_kwargs_from_input(labelview),
            )

    if input.rgb_views is not None:

        default_context = None

        for rgb_view in input.rgb_views:
            if rgb_view.context is None and default_context is None:
                default_context = models.RGBRenderContext.objects.create(
                    name=f"Default for {image.name}",
                    image=image,
                )

            print(rgb_view)


            x, _ = models.RGBView.objects.update_or_create(
                image=image,
                c_max=rgb_view.c_max,
                c_min=rgb_view.c_min,
                gamma=rgb_view.gamma,
                contrast_limit_min=rgb_view.contrast_limit_min,
                contrast_limit_max=rgb_view.contrast_limit_max,
                rescale=rgb_view.rescale if rgb_view.rescale is not None else True,
                active=rgb_view.active if rgb_view.active is not None else True,
                color_map=rgb_view.color_map if rgb_view.color_map is not None else "gray",
                base_color=rgb_view.base_color if rgb_view.base_color else None,
            )

            context = models.RGBRenderContext.objects.get(id=rgb_view.context) if rgb_view.context else default_context
            context.views.add(x)

    else:
        auto_create_views(image)


    if input.acquisition_views is not None:
        for acquisitionview in input.acquisition_views:
            models.AcquisitionView.objects.create(
                image=image,
                description=acquisitionview.description,
                acquired_at=acquisitionview.acquired_at,
                operator=get_user_model().objects.get(id=acquisitionview.operator) if acquisitionview.operator else None,
                **view_kwargs_from_input(acquisitionview),
            )

    if input.optics_views is not None:
        for opticsview in input.optics_views:
            models.OpticsView.objects.create(
                image=image,
                instrument_id=opticsview.instrument,
                objective_id=opticsview.objective,
                camera_id=opticsview.camera,
                **view_kwargs_from_input(opticsview),
            )

    if input.transformation_views is not None:
        for i, transformationview in enumerate(input.transformation_views):
            models.AffineTransformationView.objects.create(
                image=image,
                affine_matrix=transformationview.affine_matrix,
                stage=models.Stage.objects.get(id=transformationview.stage)
                if transformationview.stage
                else models.Stage.objects.create(
                    name=f"Unknown for {image.name} and {i}"
                ),
                **view_kwargs_from_input(transformationview),
            )

    return image


def get_image_dataset(info: Info) -> models.Dataset:
    return models.Dataset.objects.get_current_default_for_user(
        info.context.request.user
    ).id
