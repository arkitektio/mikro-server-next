from kante.types import Info
import strawberry

from core import types, models, scalars
from core.datalayer import get_current_datalayer
import json
from django.conf import settings
import uuid
import os
import mimetypes

@strawberry.input()
class RequestFileUploadInput:
    file_name: str
    datalayer: str



@strawberry.input
class PinFileInput:
    id: strawberry.ID
    pin: bool


def pin_file(
    info: Info,
    input: PinFileInput,
) -> types.File:
    raise NotImplementedError("TODO")


def request_file_upload(info: Info, input: RequestFileUploadInput) -> types.Credentials:
    """Request upload credentials for a given key"""
    
    file_name = os.path.basename(input.file_name)
    mime_type, _ = mimetypes.guess_type(file_name)

    key = uuid.uuid4().hex



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

    datalayer = get_current_datalayer()

    response = datalayer.sts.assume_role(
        RoleArn="arn:xxx:xxx:xxx:xxxx",
        RoleSessionName="sdfsdfsdf",
        Policy=json.dumps(policy, separators=(",", ":")),
        DurationSeconds=40000,
    )

    path = f"s3://{settings.FILE_BUCKET}/{key}"

    store = models.BigFileStore.objects.create(
        path=path, key=key, bucket=settings.FILE_BUCKET, file_name=file_name, mime_type=mime_type
    )
    
    

    aws = {
        "access_key": response["Credentials"]["AccessKeyId"],
        "secret_key": response["Credentials"]["SecretAccessKey"],
        "session_token": response["Credentials"]["SessionToken"],
        "status": "success",
        "key": key,
        "bucket": settings.FILE_BUCKET,
        "datalayer": input.datalayer,
        "store": store.id,
    }

    return types.Credentials(**aws)


def request_file_upload_presigned(
    info: Info, input: RequestFileUploadInput
) -> types.PresignedPostCredentials:
    """Request upload credentials for a given key with"""
    key = uuid.uuid4().hex
    
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

    datalayer = get_current_datalayer()

    response = datalayer.s3v4.generate_presigned_post(
        Bucket=settings.FILE_BUCKET,
        Key=key,
        Fields=None,
        Conditions=None,
        ExpiresIn=50000,
    )

    path = f"s3://{settings.FILE_BUCKET}/{key}"

    store, _ = models.BigFileStore.objects.get_or_create(
        path=path, key=input.key, bucket=settings.FILE_BUCKET
    )

    aws = {
        "key": response["fields"]["key"],
        "x_amz_algorithm": response["fields"]["x-amz-algorithm"],
        "x_amz_credential": response["fields"]["x-amz-credential"],
        "x_amz_date": response["fields"]["x-amz-date"],
        "x_amz_signature": response["fields"]["x-amz-signature"],
        "policy": response["fields"]["policy"],
        "bucket": settings.FILE_BUCKET,
        "datalayer": input.datalayer,
        "store": store.id,
    }

    return types.PresignedPostCredentials(**aws)


@strawberry.input()
class RequestFileAccessInput:
    store: strawberry.ID
    duration: int | None


def request_file_access(
    info: Info, input: RequestFileAccessInput
) -> types.AccessCredentials:
    """Request upload credentials for a given key"""

    store = models.BigFileStore.objects.get(id=input.store)

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

    datalayer = get_current_datalayer()

    response = datalayer.sts.assume_role(
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
class FromFileLike:
    file: scalars.FileLike
    file_name: str
    dataset: strawberry.ID | None = None
    origins: list[strawberry.ID] | None = None
    


def from_file_like(
    info: Info,
    input: FromFileLike,
) -> types.File:
    store = models.BigFileStore.objects.get(id=input.file)
    store.fill_info()
    
    dataset = models.Dataset.objects.get(id=input.dataset) if input.dataset else models.Dataset.objects.get_current_default_for_user(
        info.context.request.user
    )

    table = models.File.objects.create(
        dataset=dataset,
        creator=info.context.request.user,
        name=store.file_name,
        store=store,
    )

    return table


@strawberry.input
class DeleteFileInput:
    id: strawberry.ID


def delete_file(
    info: Info,
    input: DeleteFileInput,
) -> strawberry.ID:
    item = models.File.objects.get(id=input.id)
    item.delete()
    return input.id
