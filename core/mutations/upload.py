import mimetypes
import os
import uuid
from kante.types import Info
import strawberry

from core import types, models, scalars
from core.datalayer import get_current_datalayer
import json
from django.conf import settings
from django.contrib.auth import get_user_model


@strawberry.input()
class RequestMediaUploadInput:
    file_name: str
    datalayer: str


def request_media_upload(info: Info, input: RequestMediaUploadInput) -> types.PresignedPostCredentials:
    """Request upload credentials for a given key"""

    file_name = os.path.basename(input.file_name)
    mime_type, _ = mimetypes.guess_type(file_name)

    key = uuid.uuid4().hex

    datalayer = get_current_datalayer()

    response = datalayer.s3v4.generate_presigned_post(
        Bucket=settings.MEDIA_BUCKET,
        Key=key,
        Fields=None,
        Conditions=None,
        ExpiresIn=50000,
    )

    path = f"s3://{settings.MEDIA_BUCKET}/{key}"

    store = models.MediaStore.objects.create(path=path, key=key, bucket=settings.MEDIA_BUCKET, file_name=file_name, mime_type=mime_type or "application/octet-stream")

    aws = {
        "key": response["fields"]["key"],
        "x_amz_algorithm": response["fields"]["x-amz-algorithm"],
        "x_amz_credential": response["fields"]["x-amz-credential"],
        "x_amz_date": response["fields"]["x-amz-date"],
        "x_amz_signature": response["fields"]["x-amz-signature"],
        "policy": response["fields"]["policy"],
        "bucket": settings.MEDIA_BUCKET,
        "datalayer": input.datalayer,
        "store": store.id,
    }

    return types.PresignedPostCredentials(**aws)
