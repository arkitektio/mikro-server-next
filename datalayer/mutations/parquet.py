from kante.types import Info
from datalayer import types, models, inputs

from ._stores import finish_store_upload, request_store_upload


def request_parquet_upload(info: Info, input: inputs.RequestParquetUploadInput) -> types.MediaUploadGrant:
    """Request a signed SeaweedFS upload grant for a media file."""
    model = input.to_pydantic()
    grant, store = request_store_upload(input, models.ParquetStore, "parquet")

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


def finish_parquet_upload(info: Info, input: inputs.FinishParquetUploadInput) -> types.ParquetStore:
    """Mark the ParquetStore as populated after a successful upload."""
    finish_store_upload(input, models.ParquetStore, "ParquetStore")
