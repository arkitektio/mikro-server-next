import strawberry
from datalayer import models
from kante.types import Info
import kante
from typing import cast

from datalayer.datalayer import get_current_datalayer


@kante.type(description="A signed SeaweedFS grant for a specific object path.")
class DatalayerAccessGrant:
    """A signed SeaweedFS read or delete grant."""

    jwt: str
    path: str
    method: str
    action: str
    body_format: str
    expires_in: int
    max_bytes: int


@kante.type(description="A signed SeaweedFS upload grant tied to a media store.")
class MediaUploadGrant:
    """A signed upload grant for media objects."""

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
    store: strawberry.ID


@kante.type(description="A signed SeaweedFS upload grant tied to a datalayer-backed store.")
class BigFileUploadGrant:
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
    store: strawberry.ID


@kante.type(description="A signed SeaweedFS upload grant tied to a datalayer-backed store.")
class ZarrUploadGrant:
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
    store: strawberry.ID


@kante.type(description="A signed SeaweedFS upload grant tied to a datalayer-backed store.")
class ParquetUploadGrant:
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
    store: strawberry.ID


@kante.django_type(
    models.BigFileStore,
    description="A BigFileStore represents a large object stored behind the SeaweedFS datalayer.",
)
class BigFileStore:
    """A large object stored behind the SeaweedFS datalayer."""

    id: strawberry.auto
    path: str
    bucket: str
    key: str
    original_file_name: str | None
    content_type: str | None

    @strawberry.field(description="Get a signed SeaweedFS read grant for the object.")
    def access_grant(self, info: Info, host: str | None = None) -> DatalayerAccessGrant:
        """Return a signed read grant for the big file."""
        datalayer = get_current_datalayer()
        grant = cast(models.BigFileStore, self).grant_read_access(datalayer=datalayer, host=host)
        return DatalayerAccessGrant(**grant.model_dump())

    @strawberry.field()
    def presigned_url(self, info: Info) -> str:
        """Compatibility field returning the signed relative SeaweedFS request path."""
        datalayer = get_current_datalayer()
        return cast(models.BigFileStore, self).get_presigned_url(datalayer=datalayer)


@kante.django_type(models.MediaStore)
class MediaStore:
    """A media object stored behind the SeaweedFS datalayer."""

    id: strawberry.auto
    path: str
    bucket: str
    key: str
    original_file_name: str | None
    content_type: str | None

    @kante.django_field(description="Get a signed SeaweedFS read grant for the media object.")
    def access_grant(self, info: Info, host: str | None = None) -> DatalayerAccessGrant:
        """Return a signed read grant for the media object."""
        datalayer = get_current_datalayer()
        grant = cast(models.MediaStore, self).grant_read_access(datalayer=datalayer, host=host)
        return DatalayerAccessGrant(**grant.model_dump())

    @kante.django_field(description="Compatibility field returning the signed SeaweedFS read URL.")
    def presigned_url(self, info: Info, host: str | None = None) -> str:
        """Compatibility field returning the signed relative SeaweedFS request path."""
        datalayer = get_current_datalayer()
        return cast(models.MediaStore, self).get_presigned_url(datalayer=datalayer, host=host)


@kante.django_type(models.ZarrStore)
class ZarrStore:
    """A Zarr object stored behind the SeaweedFS datalayer."""

    id: strawberry.auto
    path: str
    bucket: str
    key: str
    original_file_name: str | None
    content_type: str | None
    shape: list[int] | None
    chunks: list[int] | None
    version: str | None

    @kante.django_field(description="Get a signed SeaweedFS read grant for the Zarr object.")
    def access_grant(self, info: Info, host: str | None = None) -> DatalayerAccessGrant:
        """Return a signed read grant for the Zarr store."""
        datalayer = get_current_datalayer()
        grant = cast(models.ZarrStore, self).grant_read_access(datalayer=datalayer, host=host)
        return DatalayerAccessGrant(**grant.model_dump())


@kante.django_type(models.ParquetStore)
class ParquetStore:
    """A Zarr object stored behind the SeaweedFS datalayer."""

    id: strawberry.auto
    path: str
    bucket: str
    key: str
    original_file_name: str | None
    content_type: str | None

    @kante.django_field(description="Get a signed SeaweedFS read grant for the Zarr object.")
    def access_grant(self, info: Info, host: str | None = None) -> DatalayerAccessGrant:
        """Return a signed read grant for the Zarr store."""
        datalayer = get_current_datalayer()
        grant = cast(models.ParquetStore, self).grant_read_access(datalayer=datalayer, host=host)
        return DatalayerAccessGrant(**grant.model_dump())

    @kante.django_field(description="Compatibility field returning the signed SeaweedFS read URL.")
    def presigned_url(self, info: Info, host: str | None = None) -> str:
        """Compatibility field returning the signed relative SeaweedFS request path."""
        datalayer = get_current_datalayer()
        return cast(models.MediaStore, self).get_presigned_url(datalayer=datalayer, host=host)
