from kante.types import Info
from typing import cast
from datalayer import inputs, types
from datalayer.datalayer import get_current_datalayer


def request_bigfile_upload(
    info: Info, input: inputs.RequestBigFileUploadInput
) -> types.BigFileUploadGrant:
    """Request temporary S3 upload credentials for a big file."""
    del info
    dl = get_current_datalayer()
    input_model = getattr(input, "to_pydantic")()
    return types.BigFileUploadGrant(**dl.generate_bigfile_upload_grant(input_model).model_dump())


def finish_bigfile_upload(
    info: Info, input: inputs.FinishBigFileUploadInput
) -> types.BigFileStore:
    """Mark the BigFileStore as populated after a successful upload."""
    del info
    dl = get_current_datalayer()
    input_model = getattr(input, "to_pydantic")()
    return cast(types.BigFileStore, dl.finish_bigfile_upload(input_model))
