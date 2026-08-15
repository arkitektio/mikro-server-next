import strawberry
from strawberry.scalars import JSON
from datalayer import models
from kante.types import Info
import kante
from typing import cast
from datalayer import base_models
from datalayer.datalayer import get_current_datalayer


@kante.pydantic_type(base_models.BigFileAccessGrant, description="Temporary S3 credentials for reading a big file.")
class BigFileAccessGrant:
    """Temporary S3 credentials for a big file."""

    status: str
    access_key: str
    secret_key: str
    session_token: str
    region: str

    bucket: str
    key: str
    path: str
    expires_in: int
    store: str | None


@kante.pydantic_type(base_models.MediaAccessGrant, description="Temporary S3 credentials for reading a media object.")
class MediaAccessGrant:
    """Temporary S3 credentials for a media object."""

    status: str
    access_key: str
    secret_key: str
    session_token: str
    region: str
    bucket: str
    key: str
    path: str
    expires_in: int
    store: str | None


@kante.pydantic_type(base_models.GeneralMediaAccessGrant, description="Temporary S3 credentials for reading a media object.")
class GeneralMediaAccessGrant:
    """Temporary S3 credentials for a media object."""

    status: str
    access_key: str
    secret_key: str
    session_token: str
    region: str
    bucket: str
    path: str
    expires_in: int
    store: str | None


@kante.pydantic_type(base_models.ZarrAccessGrant, description="Temporary S3 credentials for reading a Zarr store.")
class ZarrAccessGrant:
    """Temporary S3 credentials for a Zarr store."""

    status: str
    access_key: str
    secret_key: str
    session_token: str
    region: str

    bucket: str
    key: str
    path: str
    expires_in: int
    store: str | None


@kante.pydantic_type(base_models.GeneralZarrAccessGrant, description="Temporary S3 credentials for reading a Zarr store.")
class GeneralZarrAccessGrant:
    """Temporary S3 credentials for a Zarr store."""

    status: str
    access_key: str
    secret_key: str
    session_token: str
    region: str
    bucket: str
    path: str
    expires_in: int
    store: str | None


@kante.pydantic_type(base_models.GeneralParquetAccessGrant, description="Temporary S3 credentials for reading a parquet object.")
class GeneralParquetAccessGrant:
    """Temporary S3 credentials for a parquet object."""

    status: str
    access_key: str
    secret_key: str
    session_token: str
    region: str
    bucket: str
    path: str
    expires_in: int
    store: str | None


@kante.pydantic_type(base_models.ParquetAccessGrant, description="Temporary S3 credentials for reading a parquet object.")
class ParquetAccessGrant:
    """Temporary S3 credentials for a parquet object."""

    status: str
    access_key: str
    secret_key: str
    session_token: str
    region: str
    bucket: str
    key: str
    path: str
    expires_in: int
    store: str | None


@kante.pydantic_type(base_models.FabriksAccessGrant, description="Temporary S3 credentials for reading a fabriks store. Covers the whole prefix, so one grant reads the manifest, both catalogs and every level.")
class FabriksAccessGrant:
    """Temporary S3 credentials for a fabriks store."""

    status: str
    access_key: str
    secret_key: str
    session_token: str
    region: str
    bucket: str
    key: str
    path: str
    expires_in: int
    store: str | None


# Note the field list: `status`/`region`/`bucket`/`expires_in` and nothing else, because that
# is what `GeneralAccessGrant` actually carries. The zarr and parquet twins declare `path` and
# `store` here as non-null, neither of which exists on the model, so both resolve to None
# through a non-null field. Not copied.
@kante.pydantic_type(base_models.GeneralFabriksAccessGrant, description="Temporary S3 credentials for reading the organization's fabriks stores.")
class GeneralFabriksAccessGrant:
    """Temporary S3 credentials for the organization's fabriks stores."""

    status: str
    access_key: str
    secret_key: str
    session_token: str
    region: str
    bucket: str
    expires_in: int


# Modelled on `MediaUploadGrant`, deliberately not on `ZarrUploadGrant`: that one declares an
# `action: str` the pydantic model has never had, and omits `region`, which it does have.
@kante.pydantic_type(base_models.FabriksUploadGrant, description="Temporary S3 credentials for uploading a fabriks store. Scoped to the prefix and permitted to read back and delete inside it, because the tree is written incrementally and its manifest lands last.")
class FabriksUploadGrant:
    """Temporary S3 credentials for a fabriks upload."""

    region: str
    status: str
    access_key: str
    secret_key: str
    session_token: str
    bucket: str
    key: str
    path: str
    expires_in: int
    max_bytes: int
    original_file_name: str | None
    upload_file_name: str
    upload_content_type: str | None
    upload_form_field: str
    store: str


@kante.pydantic_type(base_models.MediaUploadGrant, description="A presigned PUT grant for uploading a media object.")
class MediaUploadGrant:
    """A presigned PUT grant for a media upload."""

    region: str
    status: str
    access_key: str
    secret_key: str
    session_token: str
    bucket: str
    key: str
    path: str
    expires_in: int
    max_bytes: int
    original_file_name: str | None
    upload_file_name: str
    upload_content_type: str | None
    upload_form_field: str
    store: str


@kante.pydantic_type(base_models.BigFileUploadGrant, description="Temporary S3 credentials for uploading a big file.")
class BigFileUploadGrant:
    """Temporary S3 credentials for a big file upload."""

    region: str
    status: str
    access_key: str
    secret_key: str
    session_token: str
    bucket: str
    key: str
    path: str
    expires_in: int
    max_bytes: int
    original_file_name: str | None
    upload_file_name: str
    upload_content_type: str | None
    upload_form_field: str
    store: str


@kante.pydantic_type(base_models.ZarrUploadGrant, description="Temporary S3 credentials for uploading a Zarr store.")
class ZarrUploadGrant:
    """Temporary S3 credentials for a Zarr upload."""

    status: str
    access_key: str
    secret_key: str
    session_token: str
    bucket: str
    key: str
    path: str
    action: str
    expires_in: int
    max_bytes: int
    original_file_name: str | None
    upload_file_name: str
    upload_content_type: str | None
    upload_form_field: str
    store: str


@kante.pydantic_type(base_models.ParquetUploadGrant, description="Temporary S3 credentials for uploading a parquet store.")
class ParquetUploadGrant:
    """Temporary S3 credentials for a parquet upload."""

    status: str
    access_key: str
    secret_key: str
    session_token: str
    bucket: str
    key: str
    path: str
    action: str
    expires_in: int
    max_bytes: int
    original_file_name: str | None
    upload_file_name: str
    upload_content_type: str | None
    upload_form_field: str
    store: str


@kante.django_type(
    models.BigFileStore,
    description="A BigFileStore represents a large object stored behind the S3 datalayer.",
)
class BigFileStore:
    """A large object stored behind the S3 datalayer."""

    id: strawberry.auto
    path: str
    bucket: str
    key: str
    original_file_name: str | None
    content_type: str | None

    @strawberry.field(description="Get temporary S3 read credentials for the object.")
    def access_grant(self, info: Info, host: str | None = None) -> BigFileAccessGrant:
        """Return a signed read grant for the big file."""
        del info, host
        datalayer = get_current_datalayer()
        grant = cast(models.BigFileStore, self).get_access_grant(datalayer=datalayer)
        return BigFileAccessGrant.from_pydantic(grant)

    @strawberry.field()
    def presigned_url(self, info: Info) -> str:
        """Compatibility field returning the canonical S3 object path."""
        datalayer = get_current_datalayer()
        return cast(models.BigFileStore, self).get_presigned_url(datalayer=datalayer)


@kante.django_type(models.MediaStore)
class MediaStore:
    """A media object stored behind the S3 datalayer."""

    id: strawberry.auto
    path: str
    bucket: str
    key: str
    original_file_name: str | None
    content_type: str | None

    @kante.django_field(description="Get temporary S3 read credentials for the media object.")
    def access_grant(self, info: Info, host: str | None = None) -> MediaAccessGrant:
        """Return a signed read grant for the media object."""
        del info, host
        datalayer = get_current_datalayer()
        grant = cast(models.MediaStore, self).get_access_grant(datalayer=datalayer)
        return MediaAccessGrant(**grant.model_dump())

    @kante.django_field(description="Compatibility field returning the canonical S3 object path.")
    def presigned_url(self, info: Info, host: str | None = None) -> str:
        """Compatibility field returning the canonical S3 object path."""
        datalayer = get_current_datalayer()
        return cast(models.MediaStore, self).get_presigned_url(datalayer=datalayer, host=host)


@kante.django_type(models.FabriksStore, description="A fabriks collection stored as a prefix of Parquet files behind the S3 datalayer. Its grid and encoding are read from its own manifest, never declared by a caller.")
class FabriksStore:
    """A fabriks store: one prefix holding a manifest, two catalogs and the level partitions."""

    id: strawberry.auto
    path: str
    bucket: str
    key: str
    spec_version: str | None
    grid: JSON | None
    encoding: JSON | None
    axes: list[str] | None
    counts: JSON | None
    files: JSON | None

    @kante.django_field(description="Get temporary S3 read credentials covering this store's whole prefix -- the manifest, both catalogs and every level, in one grant.")
    def access_grant(self, info: Info, host: str | None = None) -> FabriksAccessGrant:
        """Return a signed read grant for the fabriks prefix."""
        del info, host
        datalayer = get_current_datalayer()
        grant = cast(models.FabriksStore, self).get_access_grant(datalayer=datalayer)
        return FabriksAccessGrant(**grant.model_dump())


@kante.django_type(models.ZarrStore)
class ZarrStore:
    """A Zarr object stored behind the S3 datalayer."""

    id: strawberry.auto
    path: str
    bucket: str
    key: str
    shape: list[int]
    chunks: list[int]
    version: str | None
    dtype: str | None
    dimension_names: list[str | None] | None
    fill_value: JSON
    attributes: JSON | None
    storage_transformers: JSON | None
    chunk_key_encoding: JSON | None
    codecs: JSON | None

    @kante.django_field(description="Get temporary S3 read credentials for the Zarr object.")
    def access_grant(self, info: Info, host: str | None = None) -> ZarrAccessGrant:
        """Return a signed read grant for the Zarr store."""
        del info, host
        datalayer = get_current_datalayer()
        grant = cast(models.ZarrStore, self).get_access_grant(datalayer=datalayer)
        return ZarrAccessGrant(**grant.model_dump())


@kante.django_type(models.ParquetStore)
class ParquetStore:
    """A parquet object stored behind the S3 datalayer."""

    id: strawberry.auto
    path: str
    bucket: str
    key: str
    original_file_name: str | None
    content_type: str | None

    @kante.django_field(description="Get temporary S3 read credentials for the parquet object.")
    def access_grant(self, info: Info, host: str | None = None) -> ParquetAccessGrant:
        """Return a signed read grant for the Zarr store."""
        del info, host
        datalayer = get_current_datalayer()
        grant = cast(models.ParquetStore, self).get_access_grant(datalayer=datalayer)
        return ParquetAccessGrant(**grant.model_dump())

    @kante.django_field(description="Compatibility field returning the canonical S3 object path.")
    def presigned_url(self, info: Info, host: str | None = None) -> str:
        """Compatibility field returning the canonical S3 object path."""
        datalayer = get_current_datalayer()
        return cast(models.ParquetStore, self).get_presigned_url(datalayer=datalayer, host=host)
