from typing import Optional

from pydantic import BaseModel


class RequestMediaUploadInput(BaseModel):
    """Request temporary S3 upload credentials for a media object."""

    original_file_name: str
    file_size: Optional[int] = None
    content_type: Optional[str] = None


class FinishMediaUploadInput(BaseModel):
    """Mark a MediaStore as populated after a successful upload."""

    store_id: str
    valid: bool = True


class RequestBigFileUploadInput(BaseModel):
    """Request temporary S3 upload credentials for a big file."""

    original_file_name: str
    file_size: Optional[int] = None
    content_type: Optional[str] = None


class FinishBigFileUploadInput(BaseModel):
    """Mark a BigFileStore as populated after a successful upload."""

    store_id: str
    valid: bool = True


class RequestZarrUploadInput(BaseModel):
    """Request temporary S3 upload credentials for a Zarr store."""

    shape: Optional[list[int]] = None
    chunks: Optional[list[int]] = None
    version: Optional[str] = None


class FinishZarrUploadInput(BaseModel):
    """Mark a ZarrStore as populated after a successful upload."""

    store_id: str
    valid: bool = True


class RequestParquetUploadInput(BaseModel):
    """Request temporary S3 upload credentials for a Parquet store."""

    original_file_name: str
    content_type: Optional[str] = None


class FinishParquetUploadInput(BaseModel):
    """Mark a ParquetStore as populated after a successful upload."""

    store_id: str
    valid: bool = True


class AccessGrant(BaseModel):
    """Temporary S3 credentials scoped to a datalayer action."""

    status: str = "granted"
    access_key: str
    secret_key: str
    session_token: str
    bucket: str
    key: str
    path: str
    action: str
    expires_in: int
    datalayer: str
    store: str | None = None


class BigFileAccessGrant(AccessGrant):
    """Temporary S3 credentials for an existing big file."""


class MediaAccessGrant(AccessGrant):
    """Temporary S3 credentials for an existing media object."""


class ZarrAccessGrant(AccessGrant):
    """Temporary S3 credentials for an existing Zarr store."""


class ParquetAccessGrant(AccessGrant):
    """Temporary S3 credentials for an existing parquet store."""


class BaseUploadGrant(AccessGrant):
    """Temporary S3 credentials for uploads bound to a specific store."""

    max_bytes: int
    original_file_name: str | None = None
    upload_file_name: str
    upload_content_type: str | None = None
    upload_form_field: str = "file"


class MediaUploadGrant(BaseUploadGrant):
    """Temporary S3 credentials for a media upload."""


class BigFileUploadGrant(BaseUploadGrant):
    """Temporary S3 credentials for a big file upload."""


class ZarrUploadGrant(BaseUploadGrant):
    """Temporary S3 credentials for a Zarr upload."""


class ParquetUploadGrant(BaseUploadGrant):
    """Temporary S3 credentials for a parquet upload."""
