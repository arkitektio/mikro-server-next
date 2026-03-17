from kante.types import Info
from typing import cast
from datalayer import types, inputs
from datalayer.datalayer import get_current_datalayer


def request_media_upload(
    info: Info, input: inputs.RequestMediaUploadInput
) -> types.MediaUploadGrant:
    """Request temporary S3 upload credentials for a media file."""
    del info
    dl = get_current_datalayer()
    input_model = getattr(input, "to_pydantic")()
    return types.MediaUploadGrant(**dl.generate_media_upload_grant(input_model).model_dump())
    

def finish_media_upload(
    info: Info, input: inputs.FinishMediaUploadInput
) -> types.MediaStore:
    """Mark the MediaStore as populated after a successful upload."""
    del info
    dl = get_current_datalayer()
    input_model = getattr(input, "to_pydantic")()
    return cast(
        types.MediaStore, dl.finish_media_upload(input_model)
    )
