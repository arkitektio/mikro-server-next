import logging
from pathlib import PurePosixPath
from collections.abc import Callable
from typing import TYPE_CHECKING
from urllib import error, request
from uuid import uuid4

from django.db import models
from polymorphic.models import PolymorphicModel
from datalayer.datalayer import AccessGrant, Datalayer
from datalayer.fields import StorePathField

if TYPE_CHECKING:
    from types_boto3_s3.type_defs import FileobjTypeDef


logger = logging.getLogger(__name__)


def get_default_upload_token() -> str:
    """Return the default opaque token used for storage keys."""
    return uuid4().hex


def build_opaque_storage_key(original_file_name: str, generator: Callable[[], str] = get_default_upload_token) -> str:
    """Build a fully opaque storage key without embedding filename metadata."""
    del original_file_name
    return generator()


def build_multipart_upload_payload(filename: str, payload: bytes, content_type: str) -> tuple[bytes, str]:
    """Build a multipart payload accepted by the SeaweedFS filer POST handler."""
    boundary = f"----kraph-{uuid4().hex}"
    parts = [
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        payload,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class DatalayerStore(PolymorphicModel):
    """An object stored behind the SeaweedFS datalayer."""

    path = StorePathField(null=True, blank=True, help_text="The object-store URI of the file", unique=True)
    key = models.CharField(max_length=1000, help_text="The object key/path within the datalayer bucket.")
    bucket = models.CharField(max_length=1000, help_text="The datalayer bucket/service this store belongs to.")
    original_file_name = models.CharField(max_length=1000, null=True, blank=True, help_text="The original client-provided file name.")
    content_type = models.CharField(max_length=255, null=True, blank=True, help_text="The client-provided content type for the uploaded file.")
    populated = models.BooleanField(default=False, help_text="Whether the store has been populated with a valid path and is ready for use.")

    def build_store_path(self, datalayer: Datalayer | None = None) -> str:
        """Return the canonical object-store URI for this store."""
        layer = datalayer or Datalayer()
        return layer.build_store_path(self.bucket, self.key)

    def grant_read_access(self, datalayer: Datalayer, host: str | None = None) -> AccessGrant:
        """Return a signed read grant for this store."""
        del host
        return datalayer.generate_file_read_url(self.bucket, self.key)

    def grant_delete_access(self, datalayer: Datalayer) -> AccessGrant:
        """Return a signed delete grant for this store."""
        return datalayer.generate_file_delete_url(self.bucket, self.key)

    def fill_info(self) -> None:
        """Finalize the store after a successful upload."""
        raise NotImplementedError("Subclasses must implement fill_info()")

    def delete(self, *args, **kwargs) -> tuple[int, dict[str, int]]:
        """Delete the remote object when the store row is removed."""
        datalayer = Datalayer()
        grant = self.grant_delete_access(datalayer)
        delete_url = datalayer.build_external_url(grant)

        try:
            with request.urlopen(request.Request(delete_url, method=grant.method), timeout=5):
                pass
        except error.HTTPError as exc:
            if exc.code != 404:
                raise
        except error.URLError:
            logger.warning("Unable to delete SeaweedFS object %s during store deletion", self.path or self.key)

        return super().delete(*args, **kwargs)

    def get_upload_file_name(self) -> str:
        """Return the client-visible filename to use in multipart uploads."""
        if self.original_file_name:
            return PurePosixPath(self.original_file_name).name

        return self.key.rsplit("/", 1)[-1]


class BigFileStore(DatalayerStore):
    """A large file stored behind the SeaweedFS datalayer."""

    def fill_info(self) -> None:
        """Mark the object as populated and normalize its stored URI."""
        self.path = self.build_store_path()
        self.populated = True
        self.save(update_fields=["path", "populated"])

    def get_presigned_url(
        self,
        datalayer: Datalayer,
        host: str | None = None,
    ) -> str:
        """Return a signed relative SeaweedFS request path for the object."""
        grant = self.grant_read_access(datalayer, host=host)
        return datalayer.build_relative_url(grant)


class MediaStore(DatalayerStore):
    """Media objects stored behind the SeaweedFS datalayer."""

    def get_access_grant(self, datalayer: Datalayer) -> AccessGrant:
        """Return a signed SeaweedFS read URL for the object."""
        return self.grant_read_access(datalayer)

    def get_presigned_url(self, datalayer: Datalayer, host: str | None = None) -> str:
        """Return a signed relative SeaweedFS request path for the object."""
        grant = self.grant_read_access(datalayer, host=host)
        return datalayer.build_relative_url(grant)

    def fill_info(self) -> None:
        """Mark the object as populated and normalize its stored URI."""
        self.path = self.build_store_path()
        self.populated = True
        self.save(update_fields=["path", "populated"])

    def put_file(self, datalayer: Datalayer, file: "FileobjTypeDef") -> None:
        """Upload a file to SeaweedFS using a signed filer URL."""
        grant = datalayer.generate_file_upload_url(self.bucket, self.key)
        payload, content_type = build_multipart_upload_payload(
            self.get_upload_file_name(),
            file.read(),
            getattr(file, "content_type", "application/octet-stream"),
        )
        headers = {"Content-Type": content_type}
        upload_url = datalayer.build_external_url(grant)

        with request.urlopen(request.Request(upload_url, data=payload, headers=headers, method=grant.method), timeout=30):
            pass

        self.fill_info()


class ZarrStore(DatalayerStore):
    """Zarr objects stored behind the SeaweedFS datalayer."""

    shape = models.JSONField(null=True, blank=True, help_text="The shape of the Zarr array stored at this location.")
    chunks = models.JSONField(null=True, blank=True, help_text="The chunk size of the Zarr array stored at this location.")
    version = models.CharField(max_length=10, null=True, blank=True, help_text="The Zarr format version of the array stored at this location.")

    def get_access_grant(self, datalayer: Datalayer) -> AccessGrant:
        """Return a signed SeaweedFS read URL for the object."""
        return self.grant_read_access(datalayer)

    def fill_info(self) -> None:
        """Mark the Zarr store as populated after a successful upload."""
        self.path = self.build_store_path()
        self.populated = True
        self.save(update_fields=["path", "populated"])


class ParquetStore(DatalayerStore):
    """Parquet objects stored behind the SeaweedFS datalayer."""

    def get_access_grant(self, datalayer: Datalayer) -> AccessGrant:
        """Return a signed SeaweedFS read URL for the object."""
        return self.grant_read_access(datalayer)

    def fill_info(self) -> None:
        """Mark the Parquet store as populated after a successful upload."""
        self.path = self.build_store_path()
        self.populated = True
        self.save(update_fields=["path", "populated"])
