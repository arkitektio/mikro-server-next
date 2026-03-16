from kante.types import Info
from typing import cast
from datalayer import inputs, models, types

from ._stores import finish_store_upload, request_bigfile_store_upload


def request_bigfile_upload(
    info: Info, input: inputs.RequestBigFileUploadInput
) -> types.BigFileUploadGrant:
    """Request a signed SeaweedFS upload grant for a big file."""
    del info
    model = input.to_pydantic()
    grant, store = request_bigfile_store_upload(input)

    return types.BigFileUploadGrant(
        **grant.model_dump(),
        datalayer="bigfile",
        key=store.key,
        original_file_name=model.original_file_name,
        upload_file_name=store.get_upload_file_name(),
        upload_content_type=model.content_type,
        upload_form_field="file",
        store=store.pk,
    )


def finish_bigfile_upload(
    info: Info, input: inputs.FinishBigFileUploadInput
) -> types.BigFileStore:
    """Mark the BigFileStore as populated after a successful upload."""
    del info
    return cast(
        types.BigFileStore,
        finish_store_upload(input, models.BigFileStore, "BigFileStore"),
    )
