from kante.types import Info
import strawberry
from core import types, models, scalars
from core.s3 import sts
import json
from .view import ChannelViewInput, TransformationViewInput, view_kwargs_from_input


def set_other_as_origin(
    info: Info,
    id: strawberry.ID,
    other: strawberry.ID,
) -> types.Image:
    image = models.Image.objects.get(id=id)
    other = models.Image.objects.get(id=other)

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


def request_upload(info: Info, key: str) -> types.Credentials:
    """Request upload credentials for a given key"""
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

    aws = {
        "access_key": response["Credentials"]["AccessKeyId"],
        "secret_key": response["Credentials"]["SecretAccessKey"],
        "session_token": response["Credentials"]["SessionToken"],
        "status": "success",
        "key": key,
        "bucket": "zarr",
    }

    return types.Credentials(**aws)


@strawberry.input
class FromArrayLikeInput:
    name: str
    array: scalars.ArrayLike
    origins: list[strawberry.ID] | None = None
    dataset: strawberry.ID | None = None
    channel_views: list[ChannelViewInput] | None = None
    transformation_views: list[TransformationViewInput] | None = None


def from_array_like(
    info: Info,
    input: FromArrayLikeInput,
) -> types.Image:
    image = models.Image.objects.create(origins=input.origins, dataset_id=input.dataset)

    if input.channel_views is not None:
        for channelview in input.channel_views:
            view = models.ChannelView.objects.create(
                image=image,
                channel=models.Channel.objects.get(id=channelview.channel),
                **view_kwargs_from_input(channelview),
            )

    if input.transformation_views is not None:
        for transformationview in input.transformation_views:
            view = models.TransformationView.objects.create(
                image=image,
                stage=models.Stage.objects.get(id=transformationview.stage),
                **view_kwargs_from_input(transformationview),
            )

    return image
