from kante.types import Info
import strawberry

from core import types, models, scalars
from core.s3 import sts
import json
from django.conf import settings


@strawberry.input()
class RequestTableUploadInput:
    key: str
    datalayer: str


@strawberry.input
class PinTableInput:
    id: strawberry.ID
    pin: bool


def pin_table(
    info: Info,
    input: PinTableInput,
) -> types.Table:
    raise NotImplementedError("TODO")


def request_table_upload(
    info: Info, input: RequestTableUploadInput
) -> types.Credentials:
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

    path = f"s3://{settings.PARQUET_BUCKET}/{input.key}"

    store = models.ParquetStore.objects.create(
        path=path, key=input.key, bucket=settings.PARQUET_BUCKET
    )

    aws = {
        "access_key": response["Credentials"]["AccessKeyId"],
        "secret_key": response["Credentials"]["SecretAccessKey"],
        "session_token": response["Credentials"]["SessionToken"],
        "status": "success",
        "key": input.key,
        "bucket": settings.PARQUET_BUCKET,
        "datalayer": input.datalayer,
        "store": store.id,
    }

    return types.Credentials(**aws)


@strawberry.input()
class RequestTableAccessInput:
    store: strawberry.ID
    duration: int | None


@strawberry.input()
class DeleteTableInput:
    id: strawberry.ID


def delete_table(
    info: Info,
    input: DeleteTableInput,
) -> strawberry.ID:
    item = models.Table.objects.get(id=input.id)
    item.delete()
    return input.id


def request_table_access(
    info: Info, input: RequestTableAccessInput
) -> types.AccessCredentials:
    """Request upload credentials for a given key"""

    store = models.ParquetStore.objects.get(id=input.store)

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
class FromParquetLike:
    name: str
    dataframe: scalars.ParquetLike
    origins: list[strawberry.ID] | None = None
    dataset: strawberry.ID | None = None


def from_parquet_like(
    info: Info,
    input: FromParquetLike,
) -> types.Table:
    store = models.ParquetStore.objects.get(id=input.dataframe)
    store.fill_info()

    table = models.Table.objects.create(
        dataset_id=input.dataset,
        creator=info.context.request.user,
        name=input.name,
        store=store,
    )

    return table
