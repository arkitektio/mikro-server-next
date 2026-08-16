import logging
from pathlib import PurePosixPath
from collections.abc import Callable
from typing import TYPE_CHECKING, ClassVar
from uuid import uuid4

from django.db import models
from polymorphic.models import PolymorphicModel
from datalayer import base_models
from datalayer.datalayer import AccessGrant, Datalayer

if TYPE_CHECKING:
    from types_boto3_s3.type_defs import FileobjTypeDef


logger = logging.getLogger(__name__)


def get_default_upload_token() -> str:
    """Return the default opaque token used sfor storage keys."""
    return uuid4().hex


def build_opaque_storage_key(original_file_name: str, generator: Callable[[], str] = get_default_upload_token) -> str:
    """Build a fully opaque storage key without sembsedding filename metadata."""
    del original_file_name
    return generator()


class DatalayerStore(PolymorphicModel):
    """An object stored behind the S3-backed datalayer."""

    objects: models.Manager["DatalayerStore"]  # type: ignore[assignment]

    #: The logical datalayer bucket this kind of store lives in -- the key
    #: ``Datalayer.get_bucket_config`` takes, and the value written to the ``bucket`` column.
    #: A ClassVar because it is a property of the *type*, not of a row: the column records what
    #: a store was written with, this records where its kind belongs. Declared so
    #: :func:`Datalayer.prefix_bucket_keys` can derive which buckets hold prefixes from the
    #: classes themselves rather than from a literal that has to be remembered.
    bucket_key: ClassVar[str] = ""

    #: Whether ``key`` names a *prefix* -- a directory of objects -- rather than one object.
    #: A ClassVar, so it is not queryable and does not need to be: ``DatalayerStore.objects``
    #: is polymorphic, so a query returns already-downcast instances and this is read off each.
    #: Read by ``purge_bytes`` to choose object vs prefix deletion, and -- through
    #: ``bucket_key`` above -- by the grant builder to decide whether a grant must cover a whole
    #: tree. **Both halves matter**: a prefix store whose grants are object-scoped cannot list
    #: or write its own children, and one whose deletion is object-scoped leaks every byte it
    #: ever wrote, because ``DeleteObject`` on a prefix succeeds having removed nothing.
    is_prefix: ClassVar[bool] = False

    organization = models.ForeignKey(
        "authentikate.Organization",
        on_delete=models.CASCADE,
        help_text="The organization this store belongs to.",
    )
    path = models.CharField(max_length=1000, null=True, blank=True, help_text="The object-store URI of the file", unique=True)
    key = models.CharField(max_length=1000, help_text="The object key/path within the datalayer bucket.")
    bucket = models.CharField(max_length=1000, help_text="The datalayer bucket/service this store belongs to.")
    original_file_name = models.CharField(max_length=1000, null=True, blank=True, help_text="The original client-provided file name.")
    content_type = models.CharField(max_length=255, null=True, blank=True, help_text="The client-provided content type for the uploaded file.")
    populated = models.BooleanField(default=False, help_text="Whether the store has been populated with a valid path and is ready for use.")
    orphaned_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "When the last data row referencing this store was deleted, or null while it is still in use. A *candidate* for garbage collection, not an authority: "
            "`purge_orphaned_stores` re-checks for referrers before deleting anything, and clears this again if the store was re-attached in the meantime"
        ),
    )

    def build_store_path(self, datalayer: Datalayer | None = None) -> str:
        """Return the canonical object-store URI for this store."""
        layer = datalayer or Datalayer()
        return layer.build_store_path(self.bucket, self.key)

    def grant_read_access(self, datalayer: Datalayer, host: str | None = None) -> AccessGrant:
        """Return temporary credentials for reading this store."""
        del host
        return datalayer.generate_file_read_url(self.bucket, self.key, store_id=str(self.pk))

    def grant_delete_access(self, datalayer: Datalayer) -> AccessGrant:
        """Return temporary credentials for deleting this store."""
        return datalayer.generate_file_delete_url(self.bucket, self.key, store_id=str(self.pk))

    def fill_info(self, datalayer: Datalayer | None = None) -> None:
        """Finalize the store after a successful upload."""
        raise NotImplementedError("Subclasses must implement fill_info()")

    def purge_bytes(self, datalayer: Datalayer | None = None) -> int:
        """Delete this store's objects from S3, and return how many went.

        Prefix-aware: a zarr is a directory of chunks and needs list-then-batch-delete, where
        every other store is a single key. Idempotent, so a retry after a partial failure is
        safe -- deleting an absent key is a no-op.
        """
        layer = datalayer or Datalayer()
        if self.is_prefix:
            return layer.delete_prefix(self.bucket, self.key)
        layer.delete_object(self.bucket, self.key)
        return 1

    def delete(self, *args, **kwargs) -> tuple[int, dict[str, int]]:
        """Delete the remote objects, then the row.

        **This purges immediately and ignores the grace period.** It is the "I mean it, now"
        path; the ordinary route is to let a data-row deletion flag the store and let
        `purge_orphaned_stores` collect it, which is what every delete mutation does. Nothing
        in `core.mutations` calls this.

        Bytes first, then the row, deliberately: bytes gone with the row still present is
        recoverable by re-running the sweep, while the row gone with bytes left is a leak
        nothing points at any more. A failure therefore propagates rather than being logged
        and swallowed -- the old behaviour dropped the row anyway and left the bytes orphaned
        with no record of them.
        """
        self.purge_bytes()
        return super().delete(*args, **kwargs)

    def get_upload_file_name(self) -> str:
        """Return the client-visible filename to use in multipart uploads."""
        if self.original_file_name:
            return PurePosixPath(self.original_file_name).name

        return self.key.rsplit("/", 1)[-1]


class BigFileStore(DatalayerStore):
    """A large file stored behind the S3-backed datalayer."""

    objects: models.Manager["BigFileStore"]  # type: ignore[assignment]

    bucket_key: ClassVar[str] = "bigfile"

    def grant_read_access(self, datalayer: Datalayer, host: str | None = None) -> base_models.BigFileAccessGrant:
        """Return temporary credentials for reading this big file."""
        del host
        return datalayer.generate_bigfile_access_grant(self)

    def get_access_grant(self, datalayer: Datalayer) -> base_models.BigFileAccessGrant:
        """Return temporary credentials for reading the object."""
        return self.grant_read_access(datalayer)

    def fill_info(self, datalayer: Datalayer | None = None) -> None:
        """Mark the object as populated and normalize its stored URI."""
        self.path = self.build_store_path(datalayer)
        self.populated = True
        self.save(update_fields=["path", "populated"])

    def get_presigned_url(
        self,
        datalayer: Datalayer,
        host: str | None = None,
    ) -> str:
        """Return the canonical S3 path for the object."""
        del host
        return self.build_store_path(datalayer)

    def calculate_size(self, datalayer: Datalayer) -> int:
        """Calculate the size of the big file by querying the datalayer."""
        return datalayer.get_object_size(self.bucket, self.key)


class MediaStore(DatalayerStore):
    """Media objects stored behind the S3-backed datalayer."""

    objects: models.Manager["MediaStore"]  # type: ignore[assignment]

    bucket_key: ClassVar[str] = "media"

    def grant_read_access(self, datalayer: Datalayer, host: str | None = None) -> base_models.MediaAccessGrant:
        """Return temporary credentials for reading this media object."""
        del host
        return datalayer.generate_media_access_grant(self)

    def get_access_grant(self, datalayer: Datalayer) -> base_models.MediaAccessGrant:
        """Return temporary credentials for reading the object."""
        return self.grant_read_access(datalayer)

    def get_presigned_url(self, datalayer: Datalayer, host: str | None = None) -> str:
        """Return the canonical S3 path for the object."""
        del host
        return self.build_store_path(datalayer)

    def fill_info(self, datalayer: Datalayer | None = None) -> None:
        """Mark the object as populated and normalize its stored URI."""
        self.path = self.build_store_path(datalayer)
        self.populated = True
        self.save(update_fields=["path", "populated"])

    def put_file(self, datalayer: Datalayer, file: "FileobjTypeDef") -> None:
        """Upload a file with the service credentials and finalize the store."""
        datalayer.put_file(
            self.bucket,
            self.key,
            file.read(),
            getattr(file, "content_type", "application/octet-stream"),
        )
        self.fill_info(datalayer)


class ZarrStore(DatalayerStore):
    """Zarr objects stored behind the S3-backed datalayer."""

    objects: models.Manager["ZarrStore"]  # type: ignore[assignment]

    bucket_key: ClassVar[str] = "zarr"

    # A zarr is a *directory* -- `zarr.json` plus a tree of chunk objects -- so its `key` is a
    # prefix and there is no single object at it. `DeleteObject` against a prefix succeeds with
    # a 204 having deleted nothing, which is why removing one needs list + batched delete.
    is_prefix: ClassVar[bool] = True

    shape = models.JSONField(null=True, blank=True, help_text="The shape of the Zarr array stored at this location.")
    chunks = models.JSONField(null=True, blank=True, help_text="The chunk size of the Zarr array stored at this location.")
    version = models.CharField(max_length=10, null=True, blank=True, help_text="The Zarr format version of the array stored at this location.")
    dtype = models.CharField(max_length=255, null=True, blank=True, help_text="The dtype of the Zarr array stored at this location.")
    dimension_names = models.JSONField(null=True, blank=True, help_text="The dimension names declared by the Zarr array.")
    fill_value = models.JSONField(null=True, blank=True, help_text="The fill value declared by the Zarr array.")
    attributes = models.JSONField(null=True, blank=True, help_text="The user attributes stored in zarr.json.")
    storage_transformers = models.JSONField(null=True, blank=True, help_text="The storage transformers declared by the Zarr array.")
    chunk_key_encoding = models.JSONField(null=True, blank=True, help_text="The chunk key encoding configuration for the Zarr array.")
    codecs = models.JSONField(null=True, blank=True, help_text="The codec pipeline declared for the Zarr array.")

    def grant_read_access(self, datalayer: Datalayer, host: str | None = None) -> base_models.ZarrAccessGrant:
        """Return temporary credentials for reading this Zarr prefix."""
        del host
        return datalayer.generate_zarr_access_grant(self)

    def get_access_grant(self, datalayer: Datalayer) -> base_models.ZarrAccessGrant:
        """Return temporary credentials for reading the object prefix."""
        return self.grant_read_access(datalayer)

    def fill_info(self, datalayer: Datalayer | None = None) -> None:
        """Populate Zarr metadata and mark the store as ready.

        Raises:
            FileNotFoundError: If the Zarr metadata file cannot be retrieved.
            ValueError: If the Zarr metadata is invalid or unsupported.
        """
        layer = datalayer or Datalayer()
        self.path = self.build_store_path(layer)
        metadata = layer.get_zarr_metadata(self)
        self.shape = metadata.shape
        self.chunks = metadata.chunks
        self.dtype = metadata.dtype
        self.dimension_names = metadata.dimension_names
        self.fill_value = metadata.fill_value
        self.attributes = metadata.attributes
        self.storage_transformers = metadata.storage_transformers
        self.chunk_key_encoding = metadata.chunk_key_encoding
        self.codecs = metadata.codecs
        self.version = metadata.version
        self.populated = True
        self.save(
            update_fields=[
                "path",
                "shape",
                "chunks",
                "dtype",
                "dimension_names",
                "fill_value",
                "attributes",
                "storage_transformers",
                "chunk_key_encoding",
                "codecs",
                "version",
                "populated",
            ]
        )

    @property
    def c_size(self) -> int:
        """Return the regular chunk shape for callers using the legacy field name."""
        return self.shape[0]

    @property
    def t_size(self) -> int:
        """Return the regular chunk shape for callers using the legacy field name."""
        return self.shape[1]

    @property
    def z_size(self) -> int:
        """Return the regular chunk shape for callers using the legacy field name."""
        return self.shape[2]

    @property
    def y_size(self) -> int:
        """Return the regular chunk shape for callers using the legacy field name."""
        return self.shape[3]

    @property
    def x_size(self) -> int:
        """Return the regular chunk shape for callers using the legacy field name."""
        return self.shape[4]


class ParquetStore(DatalayerStore):
    """Parquet objects stored behind the S3-backed datalayer."""

    objects: models.Manager["ParquetStore"]  # type: ignore[assignment]

    bucket_key: ClassVar[str] = "parquet"

    def grant_read_access(self, datalayer: Datalayer, host: str | None = None) -> base_models.ParquetAccessGrant:
        """Return temporary credentials for reading this parquet object."""
        del host
        return datalayer.generate_parquet_access_grant(self)

    def get_access_grant(self, datalayer: Datalayer) -> base_models.ParquetAccessGrant:
        """Return temporary credentials for reading the object."""
        return self.grant_read_access(datalayer)

    def fill_info(self, datalayer: Datalayer | None = None) -> None:
        """Mark the Parquet store as populated after a successful upload."""
        self.path = self.build_store_path(datalayer)
        self.populated = True
        self.save(update_fields=["path", "populated"])


class FabriksStore(DatalayerStore):
    """A fabriks collection -- one octree of surfaces -- stored as a prefix of Parquet files.

    **One artifact, one store.** The writer names files inside its own tree, so the layout the
    format specifies is the layout on disk::

        <prefix>/fabriks.json
        <prefix>/catalog/cells.parquet
        <prefix>/catalog/objects.parquet
        <prefix>/level0/part-00000.parquet

    One grant covers the whole collection, and a reader can glob a level without being handed a
    list of store ids.

    ``level0`` rather than the Hive-style ``level=0`` this once was. Every name in the tree is
    spelled to be *signable*: a path component ends up inside a signed URL, and SigV4 canonicalises
    a request by percent-encoding the path against RFC 3986's unreserved set before signing. ``=``
    is a sub-delimiter, so one signer sends ``%3D`` and another leaves it bare -- two strings to
    sign for one object, and a ``SignatureDoesNotMatch`` that reads like a credentials problem. The
    server hands out a prefix-wide grant and lets the client sign, so this is the client's failure
    to hit; the layout is written down here because this is where the server states it.

    **It is self-describing, and that is the point.** ``fabriks.json`` states the grid and the
    encoding next to the bytes they describe, and :meth:`fill_info` reads them here rather than
    trusting a caller to retype them -- the same move ``ZarrStore`` makes with ``zarr.json``,
    for the same reason: a fact derived from the artifact cannot be declared wrong.

    The manifest is also the **completion marker**. A prefix has no atomic "upload finished"
    flag, so a half-written tree would otherwise register as a store and fail much later, on a
    reader. Writing the manifest last and refusing a store without one converts that into a
    refusal at registration.
    """

    objects: models.Manager["FabriksStore"]  # type: ignore[assignment]

    bucket_key: ClassVar[str] = "fabriks"

    # A fabriks store is a *directory*: a manifest, two catalogs and a tree of level partitions.
    # Same consequence as a zarr -- `DeleteObject` on the prefix would delete nothing and report
    # success, so removal needs list + batched delete.
    is_prefix: ClassVar[bool] = True

    spec_version = models.CharField(max_length=64, null=True, blank=True, help_text="The mesh format version declared by the store's manifest.")
    grid = models.JSONField(null=True, blank=True, help_text="The octree grid declared by the manifest: cellSize (in voxels, ordered x/y/z), levels and sortKey.")
    encoding = models.JSONField(null=True, blank=True, help_text="The geometry encoding declared by the manifest: how positions, normals and indices are packed and compressed.")
    axes = models.JSONField(null=True, blank=True, help_text="The axis order the writer states it wrote, used to refuse a collection whose declared axes disagree with its geometry.")
    counts = models.JSONField(null=True, blank=True, help_text="Object and per-level cell counts declared by the manifest. Convenience for budgeting; never authoritative.")
    files = models.JSONField(null=True, blank=True, help_text="The file layout the manifest claims. A claim, not authority -- the prefix listing is what a check reads.")

    def grant_read_access(self, datalayer: Datalayer, host: str | None = None) -> base_models.FabriksAccessGrant:
        """Return temporary credentials for reading this fabriks prefix."""
        del host
        return datalayer.generate_fabriks_access_grant(self)

    def get_access_grant(self, datalayer: Datalayer) -> base_models.FabriksAccessGrant:
        """Return temporary credentials for reading the object prefix."""
        return self.grant_read_access(datalayer)

    def fill_info(self, datalayer: Datalayer | None = None) -> None:
        """Read the manifest, learn what it says, and mark the store populated.

        Raises:
            FileNotFoundError: If the manifest is missing -- which is also how an interrupted
                upload presents, and why it is refused rather than tolerated.
            ValueError: If the manifest is malformed or declares an unsupported version.
        """
        layer = datalayer or Datalayer()
        self.path = self.build_store_path(layer)
        metadata = layer.get_fabriks_metadata(self)
        self.spec_version = metadata.spec_version
        self.grid = metadata.grid
        self.encoding = metadata.encoding
        self.axes = metadata.axes
        self.counts = metadata.counts
        self.files = metadata.files
        self.populated = True
        self.save(update_fields=["path", "spec_version", "grid", "encoding", "axes", "counts", "files", "populated"])
