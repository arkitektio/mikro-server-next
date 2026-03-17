from kante.types import Info
from typing import cast
from datalayer import inputs, types
from datalayer.datalayer import get_current_datalayer


def request_parquet_upload(
    info: Info, input: inputs.RequestParquetUploadInput
) -> types.ParquetUploadGrant:
    """Request temporary S3 upload credentials for a parquet store."""
    del info
    dl = get_current_datalayer()
    input_model = getattr(input, "to_pydantic")()
    return dl.generate_parquet_upload_grant(input_model)


def finish_parquet_upload(
    info: Info, input: inputs.FinishParquetUploadInput
) -> types.ParquetStore:
    """Mark the ParquetStore as populated after a successful upload."""
    del info
    dl = get_current_datalayer()
    input_model = getattr(input, "to_pydantic")()
    return cast(types.ParquetStore, dl.finish_parquet_upload(input_model))
