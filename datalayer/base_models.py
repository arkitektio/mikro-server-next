from typing import Optional
from pydantic import BaseModel


class RequestMediaUploadInput(BaseModel):
    """Request a signed SeaweedFS upload grant for a media object."""

    original_file_name: str
    file_size: Optional[int] = None
    content_type: Optional[str] = None


class FinishMediaUploadInput(BaseModel):
    """Mark a MediaStore as populated after a successful upload."""

    store_id: str
    valid: bool = True


class RequestBigFileUploadInput(BaseModel):
    """Request a signed SeaweedFS upload grant for a media object."""

    original_file_name: str
    file_size: Optional[int] = None
    content_type: Optional[str] = None


class FinishBigFileUploadInput(BaseModel):
    """Mark a BigFileStore as populated after a successful upload."""

    store_id: str
    valid: bool = True


class RequestZarrUploadInput(BaseModel):
    """Request a signed SeaweedFS upload grant for a Zarr store."""

    shape: Optional[list[int]] = None
    chunks: Optional[list[int]] = None
    version: Optional[str] = None


class FinishZarrUploadInput(BaseModel):
    """Mark a ZarrStore as populated after a successful upload."""

    store_id: str
    valid: bool = True


class RequestParquetUploadInput(BaseModel):
    """Request a signed SeaweedFS upload grant for a Parquet store."""

    original_file_name: str
    content_type: Optional[str] = None


class FinishParquetUploadInput(BaseModel):
    """Mark a ParquetStore as populated after a successful upload."""

    store_id: str
    valid: bool = True


class MediaUploadGrant(BaseModel):
    """A signed upload grant for non-media datalayer stores."""
    x_amz_algorithm: str
    x_amz_credential: str
    x_amz_date: str
    x_amz_signature: str
    path: str
    method: str
    action: str
    body_format: str
    expires_in: int
    max_bytes: int
    datalayer: str
    key: str
    original_file_name: str
    upload_file_name: str
    upload_content_type: str | None
    upload_form_field: str
    store: str



class MediaAccessGrant(BaseModel):
    """A signed access grant for media objects."""

    jwt: str



class BigFileUploadGrant(BaseModel):
    """A signed upload grant for non-media datalayer stores."""

    jwt: str
    path: str
    method: str
    action: str
    body_format: str
    expires_in: int
    max_bytes: int
    datalayer: str
    key: str
    original_file_name: str
    upload_file_name: str
    upload_content_type: str | None
    upload_form_field: str
    store: str


class ZarrUploadGrant(BaseModel):
    """A signed upload grant for non-media datalayer stores."""

    jwt: str
    path: str
    method: str
    action: str
    body_format: str
    expires_in: int
    max_bytes: int
    datalayer: str
    key: str
    upload_file_name: str
    upload_form_field: str
    store: str


class ParquetUploadGrant(BaseModel):
    """A signed upload grant for non-media datalayer stores."""

    jwt: str
    path: str
    method: str
    action: str
    body_format: str
    expires_in: int
    max_bytes: int
    datalayer: str
    key: str
    original_file_name: str
    upload_file_name: str
    upload_content_type: str | None
    upload_form_field: str
    store: str
