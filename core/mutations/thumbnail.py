from kante.types import Info
import strawberry
from core import types, models, scalars
from strawberry.file_uploads import Upload
from django.conf import settings
@strawberry.input
class ThumbnailInput:
    file: Upload


def create_thumbnail(
    info: Info,
    input: ThumbnailInput,
) -> types.Thumbnail:
    media_store, _ = models.MediaStore.objects.get_or_create(bucket=settings.MEDIA_BUCKET, key=input.file.name, path=f"s3://{settings.MEDIA_BUCKET}/{input.file.name}")
    media_store.put_file(input.file)

    item = models.Thumbnail.objects.create(
        name=input.file.name, store=media_store
    )
    return item


