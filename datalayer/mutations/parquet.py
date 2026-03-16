from kante.types import Info
from typing import cast
from datalayer import inputs, models, types

from ._stores import finish_store_upload, request_parquet_store_upload


def request_parquet_upload(
    info: Info, input: inputs.RequestParquetUploadInput
) -> types.ParquetUploadGrant:
    """Request a signed SeaweedFS upload grant for a parquet store."""
    del info
    model = input.to_pydantic()
    grant, store = request_parquet_store_upload(input)

    return types.ParquetUploadGrant(
        **grant.model_dump(),
        datalayer="parquet",
        key=store.key,
        original_file_name=model.original_file_name,
        upload_file_name=store.get_upload_file_name(),
        upload_content_type=model.content_type,
        upload_form_field="file",
        store=store.pk,
    )


def finish_parquet_upload(
    info: Info, input: inputs.FinishParquetUploadInput
) -> types.ParquetStore:
    """Mark the ParquetStore as populated after a successful upload."""
    del info
    return cast(
        types.ParquetStore,
        finish_store_upload(input, models.ParquetStore, "ParquetStore"),
    )
