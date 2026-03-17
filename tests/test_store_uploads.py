from typing import cast
from unittest.mock import patch

from django.test import TestCase

from datalayer import base_models, models
from datalayer.datalayer import Datalayer


TEMP_CREDS = ("access-key", "secret-key", "session-token")


class StoreUploadTests(TestCase):
    def setUp(self) -> None:
        self.datalayer = Datalayer()

    @patch.object(Datalayer, "_issue_temporary_credentials", return_value=TEMP_CREDS)
    @patch.object(Datalayer, "_new_key", return_value="zarr-key")
    def test_generate_zarr_upload_grant_persists_store_metadata(
        self,
        _new_key: object,
        _issue_temporary_credentials: object,
    ) -> None:
        grant = self.datalayer.generate_zarr_upload_grant(
            base_models.RequestZarrUploadInput(
                shape=[64, 64],
                chunks=[16, 16],
                version="3",
            )
        )

        assert grant.store is not None
        zarr_store = cast(models.ZarrStore, models.ZarrStore.objects.get(pk=grant.store))
        self.assertEqual(grant.access_key, TEMP_CREDS[0])
        self.assertEqual(grant.session_token, TEMP_CREDS[2])
        self.assertEqual(grant.bucket, self.datalayer.get_bucket_config("zarr").bucket)
        self.assertEqual(grant.key, "zarr-key")
        self.assertEqual(grant.max_bytes, self.datalayer.get_bucket_config("zarr").default_max_bytes)
        self.assertEqual(zarr_store.key, "zarr-key")
        self.assertIsNone(zarr_store.original_file_name)
        self.assertIsNone(zarr_store.content_type)
        self.assertEqual(zarr_store.shape, [64, 64])
        self.assertEqual(zarr_store.chunks, [16, 16])
        self.assertEqual(zarr_store.version, "3")

    def test_zarr_upload_policy_allows_prefix_read_write_operations(self) -> None:
        policy = self.datalayer._build_policy(
            self.datalayer.get_bucket_config("zarr").bucket,
            "zarr",
            "zarr-key",
            "upload",
        )

        statements = cast(list[dict[str, object]], policy["Statement"])
        object_statement = statements[0]
        bucket_statement = statements[1]

        self.assertEqual(
            object_statement["Action"],
            ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload"],
        )
        self.assertEqual(
            object_statement["Resource"],
            [
                f"arn:aws:s3:::{self.datalayer.get_bucket_config('zarr').bucket}/zarr-key",
                f"arn:aws:s3:::{self.datalayer.get_bucket_config('zarr').bucket}/zarr-key/*",
            ],
        )
        self.assertEqual(bucket_statement["Action"], ["s3:ListBucket", "s3:GetBucketLocation"])
        self.assertEqual(
            bucket_statement["Condition"],
            {"StringLike": {"s3:prefix": ["zarr-key", "zarr-key/*"]}},
        )

    @patch.object(Datalayer, "_issue_temporary_credentials", return_value=TEMP_CREDS)
    @patch.object(Datalayer, "_new_key", return_value="bigfile-key")
    def test_generate_bigfile_upload_grant_persists_original_file_name(
        self,
        _new_key: object,
        _issue_temporary_credentials: object,
    ) -> None:
        grant = self.datalayer.generate_bigfile_upload_grant(
            base_models.RequestBigFileUploadInput(
                original_file_name="folder/sample.bin",
                file_size=123,
                content_type="application/octet-stream",
            )
        )

        bigfile_store = models.BigFileStore.objects.get(pk=grant.store)
        self.assertEqual(grant.max_bytes, 123)
        self.assertEqual(grant.bucket, self.datalayer.get_bucket_config("bigfile").bucket)
        self.assertEqual(grant.key, "bigfile-key")
        self.assertEqual(bigfile_store.key, "bigfile-key")
        self.assertEqual(bigfile_store.original_file_name, "folder/sample.bin")
        self.assertEqual(bigfile_store.content_type, "application/octet-stream")

    @patch.object(Datalayer, "_issue_temporary_credentials", return_value=TEMP_CREDS)
    @patch.object(Datalayer, "_new_key", return_value="media-key")
    def test_finish_media_upload_marks_store_populated(
        self,
        _new_key: object,
        _issue_temporary_credentials: object,
    ) -> None:
        grant = self.datalayer.generate_media_upload_grant(
            base_models.RequestMediaUploadInput(
                original_file_name="image.tif",
                file_size=512,
                content_type="image/tiff",
            )
        )

        store = self.datalayer.finish_media_upload(
            base_models.FinishMediaUploadInput(store_id=cast(str, grant.store))
        )

        self.assertTrue(store.populated)
        self.assertEqual(store.path, f"s3://{self.datalayer.get_bucket_config('media').bucket}/media-key")

    @patch.object(Datalayer, "_issue_temporary_credentials", return_value=TEMP_CREDS)
    def test_store_read_access_returns_temporary_credentials(
        self,
        _issue_temporary_credentials: object,
    ) -> None:
        store = models.MediaStore.objects.create(
            path="s3://mikromedia/media-key",
            key="media-key",
            bucket="media",
            original_file_name="image.tif",
            content_type="image/tiff",
        )

        grant = store.grant_read_access(self.datalayer)

        self.assertIsInstance(grant, base_models.MediaAccessGrant)
        self.assertEqual(grant.action, "read")
        self.assertEqual(grant.bucket, self.datalayer.get_bucket_config("media").bucket)
        self.assertEqual(grant.key, "media-key")
        self.assertEqual(grant.store, str(store.pk))