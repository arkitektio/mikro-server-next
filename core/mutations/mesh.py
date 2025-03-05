from kante.types import Info
import strawberry
from core import types, models, scalars
from strawberry.file_uploads import Upload
from django.conf import settings
from core.datalayer import get_current_datalayer


@strawberry.input
class MeshInput:
    mesh: scalars.MeshLike
    name: str


@strawberry.input()
class DeleteMeshInput:
    id: strawberry.ID


@strawberry.input
class PinMeshInput:
    id: strawberry.ID
    pin: bool

@strawberry.input()
class RequestMeshUploadInput:
    key: str
    datalayer: str


def request_mesh_upload(
    info: Info, input: RequestMeshUploadInput
) -> types.PresignedPostCredentials:
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

    response = datalayer.s3v4.generate_presigned_post(
        Bucket=settings.MEDIA_BUCKET,
        Key=input.key,
        Fields=None,
        Conditions=None,
        ExpiresIn=50000,
    )

    path = f"s3://{settings.MEDIA_BUCKET}/{input.key}"

    store, _ = models.MeshStore.objects.get_or_create(
        path=path, key=input.key, bucket=settings.MEDIA_BUCKET
    )

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

def pin_mesh(
    info: Info,
    input: DeleteMeshInput,
) -> types.Snapshot:
    raise NotImplementedError("TODO")


def delete_mesh(
    info: Info,
    input: DeleteMeshInput,
) -> strawberry.ID:
    item = models.Mesh.objects.get(id=input.id)
    item.delete()
    return input.id


def create_mesh(
    info: Info,
    input: MeshInput,
) -> types.Mesh:
    media_store = models.MeshStore.objects.get(id=input.mesh)


    item = models.Mesh.objects.create(
        name=input.name, store=media_store
    )

    return item
