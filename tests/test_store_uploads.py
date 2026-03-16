from unittest.mock import patch
from typing import cast

from django.test import TestCase

from datalayer import base_models, inputs, models
from datalayer.datalayer import AccessGrant
from datalayer.mutations import _stores


class StubDatalayer:
    def generate_file_upload_url(
        self, bucket_key: str, object_path: str, max_bytes: int | None = None
    ) -> AccessGrant:
        return AccessGrant(
            jwt="jwt",
            path=f"/{bucket_key}/{object_path}",
            method="POST",
            action="upload",
            body_format="multipart",
            expires_in=300,
            max_bytes=max_bytes or 0,
        )

    def build_store_path(self, bucket_key: str, object_path: str) -> str:
        return f"seaweed://{bucket_key}/{object_path}"


class RequestAdapter:
    def __init__(self, model: object) -> None:
        self._model = model

    def to_pydantic(self) -> object:
        return self._model


class StoreUploadTests(TestCase):
    @patch("datalayer.mutations._stores.get_current_datalayer", return_value=StubDatalayer())
    def test_request_zarr_store_upload_does_not_require_original_file_name(
        self, _get_current_datalayer: object
    ) -> None:
        grant, store = _stores.request_zarr_store_upload(
            cast(
                inputs.RequestZarrUploadInput,
                RequestAdapter(
                    base_models.RequestZarrUploadInput(
                        shape=[64, 64], chunks=[16, 16], version="3"
                    )
                ),
            ),
            key_generator=lambda: "zarr-key",
        )

        zarr_store = models.ZarrStore.objects.get(pk=store.pk)
        self.assertEqual(grant.max_bytes, 0)
        self.assertEqual(zarr_store.key, "zarr-key")
        self.assertIsNone(zarr_store.original_file_name)
        self.assertIsNone(zarr_store.content_type)
        self.assertEqual(zarr_store.shape, [64, 64])
        self.assertEqual(zarr_store.chunks, [16, 16])
        self.assertEqual(zarr_store.version, "3")

    @patch("datalayer.mutations._stores.get_current_datalayer", return_value=StubDatalayer())
    def test_request_bigfile_store_upload_persists_original_file_name(
        self, _get_current_datalayer: object
    ) -> None:
        grant, store = _stores.request_bigfile_store_upload(
            cast(
                inputs.RequestBigFileUploadInput,
                RequestAdapter(
                    base_models.RequestBigFileUploadInput(
                        original_file_name="folder/sample.bin",
                        file_size=123,
                        content_type="application/octet-stream",
                    )
                ),
            ),
            key_generator=lambda: "bigfile-key",
        )

        bigfile_store = models.BigFileStore.objects.get(pk=store.pk)
        self.assertEqual(grant.max_bytes, 123)
        self.assertEqual(bigfile_store.key, "bigfile-key")
        self.assertEqual(bigfile_store.original_file_name, "folder/sample.bin")
        self.assertEqual(bigfile_store.content_type, "application/octet-stream")