from typing import Optional
from pydantic import BaseModel


class RequestMediaUploadInput(BaseModel):
    """Request a signed SeaweedFS upload grant for a media object."""

    original_file_name: str
    file_size: Optional[int] = None
    content_type: Optional[str] = None


class FinishMediaUploadInput(BaseModel):
    """Mark a MediaStore as populated after a successful upload."""

    store_id: int
    valid: bool = True
