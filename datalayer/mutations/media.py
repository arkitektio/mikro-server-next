from kante.types import Info
from typing import cast
from datalayer import types, models, inputs

from ._stores import finish_store_upload, request_media_store_upload


def request_media_upload(
    info: Info, input: inputs.RequestMediaUploadInput
) -> types.MediaUploadGrant:
    """Request a signed SeaweedFS upload grant for a media file."""
    del info
    model = input.to_pydantic()
    grant, store = request_media_store_upload(input)

    return types.MediaUploadGrant(
        **grant.model_dump(),
        datalayer="media",
        key=store.key,
        original_file_name=model.original_file_name,
        upload_file_name=store.get_upload_file_name(),
        upload_content_type=model.content_type,
        upload_form_field="file",
        store=store.pk,
    )


def finish_media_upload(
    info: Info, input: inputs.FinishMediaUploadInput
) -> types.MediaStore:
    """Mark the MediaStore as populated after a successful upload."""
    del info
    return cast(
        types.MediaStore, finish_store_upload(input, models.MediaStore, "MediaStore")
    )
