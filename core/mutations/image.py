from kante.types import Info
import strawberry

from core import types, models, scalars
from core.s3 import sts
import json
from .view import (
    PartialChannelViewInput,
    PartialLabelViewInput,
    PartialTimepointViewInput,
    PartialOpticsViewInput,
    PartialTransformationViewInput,
    view_kwargs_from_input,
)
from django.conf import settings


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
    print("Desired Datalayer")
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
    duration: int | None


def request_access(info: Info, input: RequestAccessInput) -> types.AccessCredentials:
    """Request upload credentials for a given key"""

    store = models.ZarrStore.objects.get(id=input.store)

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
    transformation_views: list[PartialTransformationViewInput] | None = None
    label_views: list[PartialLabelViewInput] | None = None
    timepoint_views: list[PartialTimepointViewInput] | None = None
    optics_views: list[PartialOpticsViewInput] | None = None


def from_array_like(
    info: Info,
    input: FromArrayLikeInput,
) -> types.Image:
    store = models.ZarrStore.objects.get(id=input.array)
    store.fill_info()

    image = models.Image.objects.create(
        dataset_id=input.dataset,
        creator=info.context.request.user,
        name=input.name,
        store=store,
    )

    print(input)

    if input.origins is not None:
        for origin in input.origins:
            image.origins.add(models.Image.objects.get(id=origin))

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
            models.TransformationView.objects.create(
                image=image,
                matrix=transformationview.matrix,
                stage=models.Stage.objects.get(id=transformationview.stage)
                if transformationview.stage
                else models.Stage.objects.create(
                    name=f"Unknown for {image.name} and {i}"
                ),
                **view_kwargs_from_input(transformationview),
            )

    return image
