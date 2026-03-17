from kante.types import Info
from typing import cast
from datalayer import types, models, inputs
from datalayer.datalayer import get_current_datalayer

from ._stores import finish_store_upload, request_media_store_upload


def request_media_upload(
    info: Info, input: inputs.RequestMediaUploadInput
) -> types.MediaUploadGrant:
    """Request a signed SeaweedFS upload grant for a media file."""
    
    
    dl = get_current_datalayer()
    model = input.to_pydantic()
    
    
    return dl.generate_media_upload_grant(
        input=input
    )
    
    
    
    
    

def finish_media_upload(
    info: Info, input: inputs.FinishMediaUploadInput
) -> types.MediaStore:
    """Mark the MediaStore as populated after a successful upload."""
    del info
    return cast(
        types.MediaStore, finish_store_upload(input, models.MediaStore, "MediaStore")
    )
