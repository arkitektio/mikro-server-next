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


class RequestBigFileUploadInput(BaseModel):
    """Request a signed SeaweedFS upload grant for a media object."""

    original_file_name: str
    file_size: Optional[int] = None
    content_type: Optional[str] = None


class FinishBigFileUploadInput(BaseModel):
    """Mark a BigFileStore as populated after a successful upload."""

    store_id: int
    valid: bool = True


class RequestZarrUploadInput(BaseModel):
    """Request a signed SeaweedFS upload grant for a Zarr store."""

    original_file_name: str
    content_type: Optional[str] = None
    shape: Optional[list[int]] = None
    chunks: Optional[list[int]] = None
    version: Optional[str] = None


class FinishZarrUploadInput(BaseModel):
    """Mark a ZarrStore as populated after a successful upload."""

    store_id: int
    valid: bool = True


class RequestParquetUploadInput(BaseModel):
    """Request a signed SeaweedFS upload grant for a Parquet store."""

    original_file_name: str
    content_type: Optional[str] = None


class FinishParquetUploadInput(BaseModel):
    """Mark a ParquetStore as populated after a successful upload."""

    store_id: int
    valid: bool = True
