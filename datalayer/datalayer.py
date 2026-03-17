import json
import uuid
from contextvars import ContextVar
from typing import TYPE_CHECKING, Optional, TypeVar

import boto3
from botocore.config import Config
from django.conf import settings
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from datalayer import base_models

if TYPE_CHECKING:
    from datalayer import models


AccessGrant = base_models.AccessGrant
StoreModel = TypeVar("StoreModel", bound="models.DatalayerStore")


# Context variable for the datalayer instance
datalayer: ContextVar["Datalayer"] = ContextVar("datalayer")


class BucketConfig(BaseModel):
    """Resolved bucket configuration for one datalayer store type."""

    bucket: str = Field(..., validation_alias=AliasChoices("PATH", "path"))
    subpath: str | None = Field(None, validation_alias=AliasChoices("SUBPATH", "subpath"))
    default_max_bytes: int = Field(
        100 * 1024 * 1024,
        validation_alias=AliasChoices("DEFAULT_MAX_BYTES", "default_max_bytes"),
    )

    model_config = ConfigDict(populate_by_name=True)


class DatalayerConfig(BaseModel):
    """Optional datalayer overrides layered on top of Django settings."""

    role_arn: str | None = Field(None, validation_alias=AliasChoices("ROLE_ARN", "role_arn"))
    external_id: str | None = Field(None, validation_alias=AliasChoices("EXTERNAL_ID", "external_id"))
    session_duration_seconds: int = Field(
        3600,
        validation_alias=AliasChoices("SESSION_DURATION_SECONDS", "session_duration_seconds"),
    )
    access_key: str = Field(..., validation_alias=AliasChoices("AWS_ACCESS_KEY_ID", "aws_access_key_idm", "access_key"))
    secret_key: str = Field(..., validation_alias=AliasChoices("AWS_SECRET_ACCESS_KEY", "aws_secret_access_key", "secret_key"))
    host: str | None = Field(None, validation_alias=AliasChoices("AWS_S3_ENDPOINT_URL", "aws_s3_endpoint_url", "host"))
    region: str | None = Field(None, validation_alias=AliasChoices("AWS_S3_REGION_NAME", "aws_s3_region_name", "region"))
    port: int | None = Field(None, validation_alias=AliasChoices("AWS_S3_PORT", "aws_s3_port", "port"))
    
    
    bigfile: Optional[BucketConfig] = None
    media: Optional[BucketConfig] = None
    zarr: Optional[BucketConfig] = None
    parquet: Optional[BucketConfig] = None

    model_config = ConfigDict(populate_by_name=True)




class Datalayer:
    """Generate temporary S3 grants and manage datalayer-backed stores."""

    def __init__(self) -> None:
        """Initialize S3 and STS clients using the configured storage backend."""
        self.config = DatalayerConfig(**getattr(settings, "DATALAYER", {}))

        client_kwargs = {
            "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
            "endpoint_url": settings.AWS_S3_ENDPOINT_URL,
            "region_name": settings.AWS_S3_REGION_NAME,
            "config": Config(signature_version="s3v4"),
        }
        session_token = getattr(settings, "AWS_SESSION_TOKEN", None)
        if session_token:
            client_kwargs["aws_session_token"] = session_token

        self._s3 = boto3.client("s3", **client_kwargs)
        self._sts = boto3.client("sts", **client_kwargs)

    def get_bucket_config(self, bucket_key: str) -> BucketConfig:
        """Return the configured bucket settings for a known upload type."""
        conf = getattr(self.config, bucket_key, None)
        if conf is not None:
            return conf

        fallback_buckets = {
            "bigfile": settings.FILE_BUCKET,
            "media": settings.MEDIA_BUCKET,
            "zarr": settings.ZARR_BUCKET,
            "parquet": settings.PARQUET_BUCKET,
        }
        try:
            return BucketConfig(bucket=fallback_buckets[bucket_key])
        except KeyError as exc:
            raise ValueError(f"Service/Bucket '{bucket_key}' not configured in datalayer.") from exc

    def build_object_key(self, bucket_key: str, object_path: str) -> str:
        """Return the concrete object key inside the configured S3 bucket."""
        conf = self.get_bucket_config(bucket_key)
        if conf.subpath:
            return f"{conf.subpath.rstrip('/')}/{object_path.lstrip('/')}"
        return object_path.lstrip("/")

    def build_store_path(self, bucket_key: str, object_path: str) -> str:
        """Return the canonical S3 URI stored in the database."""
        conf = self.get_bucket_config(bucket_key)
        return f"s3://{conf.bucket}/{self.build_object_key(bucket_key, object_path)}"

    def _new_key(self) -> str:
        return uuid.uuid4().hex

    def _session_duration(self, expires_in: int | None = None) -> int:
        return expires_in or self.config.session_duration_seconds

    def _object_resources(self, bucket_key: str, object_path: str) -> tuple[str, list[str], bool]:
        full_key = self.build_object_key(bucket_key, object_path)
        if bucket_key == "zarr":
            prefix = full_key.rstrip("/")
            return full_key, [prefix, f"{prefix}/*"], True
        return full_key, [full_key], False

    def _build_policy(self, bucket_name: str, bucket_key: str, object_path: str, action: str) -> dict[str, object]:
        _, resources, allow_list = self._object_resources(bucket_key, object_path)
        s3_resources = [f"arn:aws:s3:::{bucket_name}/{resource}" for resource in resources]
        action_map = {
            "read": ["s3:GetObject"],
            "upload": ["s3:PutObject", "s3:AbortMultipartUpload"],
            "delete": ["s3:DeleteObject"],
        }

        statements: list[dict[str, object]] = [
            {
                "Effect": "Allow",
                "Action": action_map[action],
                "Resource": s3_resources,
            }
        ]

        if allow_list:
            full_key, _, _ = self._object_resources(bucket_key, object_path)
            prefix = full_key.rstrip("/")
            statements.append(
                {
                    "Effect": "Allow",
                    "Action": ["s3:ListBucket"],
                    "Resource": [f"arn:aws:s3:::{bucket_name}"],
                    "Condition": {
                        "StringLike": {
                            "s3:prefix": [prefix, f"{prefix}/*"],
                        }
                    },
                }
            )

        return {"Version": "2012-10-17", "Statement": statements}

    def _issue_temporary_credentials(self, bucket_key: str, object_path: str, action: str, expires_in: int) -> tuple[str, str, str]:
        conf = self.get_bucket_config(bucket_key)
        duration = self._session_duration(expires_in)

        if self.config.role_arn:
            assume_role_kwargs = {
                "RoleArn": self.config.role_arn,
                "RoleSessionName": f"mikro-{action}-{uuid.uuid4().hex[:8]}",
                "DurationSeconds": duration,
                "Policy": json.dumps(self._build_policy(conf.bucket, bucket_key, object_path, action)),
            }
            if self.config.external_id:
                assume_role_kwargs["ExternalId"] = self.config.external_id
            try:
                credentials = self._sts.assume_role(**assume_role_kwargs)["Credentials"]
                return (
                    credentials["AccessKeyId"],
                    credentials["SecretAccessKey"],
                    credentials["SessionToken"],
                )
            except Exception:
                pass

        try:
            credentials = self._sts.get_session_token(DurationSeconds=duration)["Credentials"]
            return (
                credentials["AccessKeyId"],
                credentials["SecretAccessKey"],
                credentials["SessionToken"],
            )
        except Exception:
            return (
                settings.AWS_ACCESS_KEY_ID,
                settings.AWS_SECRET_ACCESS_KEY,
                getattr(settings, "AWS_SESSION_TOKEN", ""),
            )

    def _build_access_grant(
        self,
        grant_model: type[AccessGrant],
        bucket_key: str,
        object_path: str,
        *,
        action: str,
        store_id: str | None = None,
        expires_in: int | None = None,
    ) -> AccessGrant:
        conf = self.get_bucket_config(bucket_key)
        ttl = self._session_duration(expires_in)
        access_key, secret_key, session_token = self._issue_temporary_credentials(
            bucket_key,
            object_path,
            action,
            ttl,
        )
        full_key = self.build_object_key(bucket_key, object_path)
        return grant_model(
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
            bucket=conf.bucket,
            key=full_key,
            path=self.build_store_path(bucket_key, object_path),
            action=action,
            expires_in=ttl,
            datalayer=bucket_key,
            store=str(store_id) if store_id is not None else None,
        )

    def generate_media_upload_grant(self, input: base_models.RequestMediaUploadInput) -> base_models.MediaUploadGrant:
        """Create a media store and return temporary upload credentials for it."""
        from datalayer import models

        conf = self.get_bucket_config("media")
        key = self._new_key()
        store = models.MediaStore.objects.create(
            path=self.build_store_path("media", key),
            key=key,
            bucket="media",
            original_file_name=input.original_file_name,
            content_type=input.content_type,
        )

        grant = self._build_access_grant(
            base_models.AccessGrant,
            "media",
            store.key,
            action="upload",
            store_id=str(store.pk),
        )
        grant_data = grant.model_dump()
        grant_data.pop("store", None)

        return base_models.MediaUploadGrant(
            **grant_data,
            max_bytes=input.file_size or conf.default_max_bytes,
            original_file_name=store.original_file_name,
            upload_file_name=store.get_upload_file_name(),
            upload_content_type=store.content_type,
            upload_form_field="file",
            store=str(store.pk),
        )

    def generate_bigfile_upload_grant(self, input: base_models.RequestBigFileUploadInput) -> base_models.BigFileUploadGrant:
        """Create a big file store and return temporary upload credentials for it."""
        from datalayer import models

        conf = self.get_bucket_config("bigfile")
        key = self._new_key()
        store = models.BigFileStore.objects.create(
            path=self.build_store_path("bigfile", key),
            key=key,
            bucket="bigfile",
            original_file_name=input.original_file_name,
            content_type=input.content_type,
        )

        grant = self._build_access_grant(
            base_models.AccessGrant,
            "bigfile",
            store.key,
            action="upload",
            store_id=str(store.pk),
        )
        grant_data = grant.model_dump()
        grant_data.pop("store", None)

        return base_models.BigFileUploadGrant(
            **grant_data,
            max_bytes=input.file_size or conf.default_max_bytes,
            original_file_name=store.original_file_name,
            upload_file_name=store.get_upload_file_name(),
            upload_content_type=store.content_type,
            upload_form_field="file",
            store=str(store.pk),
        )

    def generate_zarr_upload_grant(self, input: base_models.RequestZarrUploadInput) -> base_models.ZarrUploadGrant:
        """Create a Zarr store and return temporary upload credentials for it."""
        from datalayer import models

        conf = self.get_bucket_config("zarr")
        key = self._new_key()
        store = models.ZarrStore.objects.create(
            path=self.build_store_path("zarr", key),
            key=key,
            bucket="zarr",
            shape=input.shape,
            chunks=input.chunks,
            version=input.version,
        )

        grant = self._build_access_grant(
            base_models.AccessGrant,
            "zarr",
            store.key,
            action="upload",
            store_id=str(store.pk),
        )
        grant_data = grant.model_dump()
        grant_data.pop("store", None)

        return base_models.ZarrUploadGrant(
            **grant_data,
            max_bytes=conf.default_max_bytes,
            original_file_name=store.original_file_name,
            upload_file_name=store.get_upload_file_name(),
            upload_content_type=store.content_type,
            upload_form_field="file",
            store=str(store.pk),
        )

    def generate_parquet_upload_grant(self, input: base_models.RequestParquetUploadInput) -> base_models.ParquetUploadGrant:
        """Create a parquet store and return temporary upload credentials for it."""
        from datalayer import models

        conf = self.get_bucket_config("parquet")
        key = self._new_key()
        store = models.ParquetStore.objects.create(
            path=self.build_store_path("parquet", key),
            key=key,
            bucket="parquet",
            original_file_name=input.original_file_name,
            content_type=input.content_type,
        )

        grant = self._build_access_grant(
            base_models.AccessGrant,
            "parquet",
            store.key,
            action="upload",
            store_id=str(store.pk),
        )
        grant_data = grant.model_dump()
        grant_data.pop("store", None)

        return base_models.ParquetUploadGrant(
            **grant_data,
            max_bytes=conf.default_max_bytes,
            original_file_name=store.original_file_name,
            upload_file_name=store.get_upload_file_name(),
            upload_content_type=store.content_type,
            upload_form_field="file",
            store=str(store.pk),
        )

    def _finish_store_upload(self, model_class: type[StoreModel], store_id: str, valid: bool) -> StoreModel:
        store = model_class.objects.get(id=store_id)
        if valid:
            store.fill_info(self)
        else:
            store.populated = False
            store.save(update_fields=["populated"])
        return store

    def finish_media_upload(self, input: base_models.FinishMediaUploadInput) -> "models.MediaStore":
        """Mark a media upload as complete."""
        from datalayer import models

        return self._finish_store_upload(models.MediaStore, input.store_id, input.valid)

    def finish_bigfile_upload(self, input: base_models.FinishBigFileUploadInput) -> "models.BigFileStore":
        """Mark a big file upload as complete."""
        from datalayer import models

        return self._finish_store_upload(models.BigFileStore, input.store_id, input.valid)

    def finish_zarr_upload(self, input: base_models.FinishZarrUploadInput) -> "models.ZarrStore":
        """Mark a Zarr upload as complete."""
        from datalayer import models

        return self._finish_store_upload(models.ZarrStore, input.store_id, input.valid)

    def finish_parquet_upload(self, input: base_models.FinishParquetUploadInput) -> "models.ParquetStore":
        """Mark a parquet upload as complete."""
        from datalayer import models

        return self._finish_store_upload(models.ParquetStore, input.store_id, input.valid)

    def generate_file_read_url(
        self,
        bucket_key: str,
        object_path: str,
        *,
        store_id: str | None = None,
        expires_in: int | None = None,
    ) -> AccessGrant:
        """Return temporary credentials for reading an object or object prefix."""
        return self._build_access_grant(
            base_models.AccessGrant,
            bucket_key,
            object_path,
            action="read",
            store_id=store_id,
            expires_in=expires_in,
        )

    def generate_file_delete_url(
        self,
        bucket_key: str,
        object_path: str,
        *,
        store_id: str | None = None,
        expires_in: int | None = None,
    ) -> AccessGrant:
        """Return temporary credentials for deleting an object or object prefix."""
        return self._build_access_grant(
            base_models.AccessGrant,
            bucket_key,
            object_path,
            action="delete",
            store_id=store_id,
            expires_in=expires_in,
        )

    def generate_bigfile_access_grant(
        self,
        object_path: str,
        *,
        store_id: str | None = None,
        expires_in: int | None = None,
    ) -> base_models.BigFileAccessGrant:
        """Return temporary credentials for reading a big file."""
        return self._build_access_grant(
            base_models.BigFileAccessGrant,
            "bigfile",
            object_path,
            action="read",
            store_id=store_id,
            expires_in=expires_in,
        )

    def generate_media_access_grant(
        self,
        object_path: str,
        *,
        store_id: str | None = None,
        expires_in: int | None = None,
    ) -> base_models.MediaAccessGrant:
        """Return temporary credentials for reading a media object."""
        return self._build_access_grant(
            base_models.MediaAccessGrant,
            "media",
            object_path,
            action="read",
            store_id=store_id,
            expires_in=expires_in,
        )

    def generate_zarr_access_grant(
        self,
        object_path: str,
        *,
        store_id: str | None = None,
        expires_in: int | None = None,
    ) -> base_models.ZarrAccessGrant:
        """Return temporary credentials for reading a Zarr prefix."""
        return self._build_access_grant(
            base_models.ZarrAccessGrant,
            "zarr",
            object_path,
            action="read",
            store_id=store_id,
            expires_in=expires_in,
        )

    def generate_parquet_access_grant(
        self,
        object_path: str,
        *,
        store_id: str | None = None,
        expires_in: int | None = None,
    ) -> base_models.ParquetAccessGrant:
        """Return temporary credentials for reading a parquet object."""
        return self._build_access_grant(
            base_models.ParquetAccessGrant,
            "parquet",
            object_path,
            action="read",
            store_id=store_id,
            expires_in=expires_in,
        )

    def put_file(self, bucket_key: str, object_path: str, payload: bytes, content_type: str | None = None) -> None:
        """Upload a single object with the service credentials."""
        conf = self.get_bucket_config(bucket_key)
        self._s3.put_object(
            Bucket=conf.bucket,
            Key=self.build_object_key(bucket_key, object_path),
            Body=payload,
            ContentType=content_type or "application/octet-stream",
        )

    def delete_object(self, bucket_key: str, object_path: str) -> None:
        """Delete a single object with the service credentials."""
        conf = self.get_bucket_config(bucket_key)
        self._s3.delete_object(
            Bucket=conf.bucket,
            Key=self.build_object_key(bucket_key, object_path),
        )


dl = Datalayer()


def get_current_datalayer() -> Datalayer:
    """Return the datalayer instance bound to the current request context."""
    return dl