import uuid

import jwt
import time
from contextvars import ContextVar
from typing import Optional
from urllib.parse import SplitResult, quote, urlencode, urlsplit, urlunsplit
import boto3
from django.conf import settings
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from datalayer import base_models
from datalayer import models
# Context variable for the datalayer instance
datalayer: ContextVar["Datalayer"] = ContextVar("datalayer")


class BucketConfig(BaseModel):
    bucket: str = Field(..., validation_alias=AliasChoices("PATH", "path"))
    subpath: str | None = Field(None, validation_alias=AliasChoices("SUBPATH", "subpath"))
    default_max_bytes: int = Field(
        100 * 1024 * 1024,
        validation_alias=AliasChoices("DEFAULT_MAX_BYTES", "default_max_bytes"),
    )

    model_config = ConfigDict(populate_by_name=True)


class DatalayerConfig(BaseModel):
    access_key: str = Field(..., validation_alias=AliasChoices("ACCESS_KEY", "access_key"))
    secret_key: str = Field(..., validation_alias=AliasChoices("SECRET_KEY", "secret_key"))
    bigfile: Optional[BucketConfig] = None
    media: Optional[BucketConfig] = None
    zarr: Optional[BucketConfig] = None




class Datalayer:
    """ Datalayer provides methods to generate signed upload and access grants for objects stored in SeaweedFS, as well as utilities for building URLs and managing bucket configurations. """
    def __init__(self) -> None:
        """ Initialize the Datalayer with configuration from Django settings and set up S3 clients for interacting with the underlying storage. """
        self.config = DatalayerConfig(**settings.DATALAYER)

        self._s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            region_name=settings.AWS_S3_REGION_NAME,  # region does not matter when using MinIO
        )
        
        
        self._s3v4 = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            region_name=settings.AWS_S3_REGION_NAME,  # region does not matter when using MinIO
            config=boto3.session.Config(signature_version="s3v4"),
        )
        
        self._sts =  boto3.client(
            "sts",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            region_name=settings.AWS_S3_REGION_NAME,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            aws_session_token=None,
            config=boto3.session.Config(signature_version="s3v4"),
            verify=False,
        )

    def build_relative_url(self, grant: AccessGrant) -> str:
        encoded_path = quote(grant.path, safe="/")
        return f"{encoded_path}?{urlencode({'jwt': grant.jwt})}"

    def build_external_url(self, grant: AccessGrant, host: str | None = None) -> str:
        base_url = host or settings.DATALAYER_URL
        parsed = urlsplit(base_url)
        encoded_path = quote(grant.path, safe="/")
        prefix = parsed.path.rstrip("/") if parsed.netloc else ""
        full_path = f"{prefix}{encoded_path}" if prefix else encoded_path
        return urlunsplit(
            SplitResult(
                parsed.scheme,
                parsed.netloc or parsed.path,
                full_path,
                urlencode({"jwt": grant.jwt}),
                "",
            )
        )

    def get_bucket_config(self, bucket_key: str) -> BucketConfig:
        """Return the configured bucket settings for a known upload type."""
        conf = getattr(self.config, bucket_key, None)
        if conf is None:
            raise ValueError(f"Service/Bucket '{bucket_key}' not configured in datalayer.")
        return conf


    def generate_media_upload_grant(self, input: base_models.RequestMediaUploadInput) -> base_models.MediaUploadGrant:
        
        
        media_config = self.config.media
        if not media_config:
            raise ValueError("Media bucket not configured in datalayer.")

        key = uuid.uuid4().hex

        
        
        response = self._s3v4.generate_presigned_post(
            Bucket=media_config.bucket,
            Key=key,
            Fields=None,
            Conditions=None,
            ExpiresIn=50000,
        )

        path = f"s3://{settings.MEDIA_BUCKET}/{key}"

        store = models.MediaStore.objects.create(path=path, key=key, bucket=settings.MEDIA_BUCKET, file_name=file_name, mime_type=mime_type or "application/octet-stream")

        aws = {
            "key": response["fields"]["key"],
            "x_amz_algorithm": response["fields"]["x-amz-algorithm"],
            "x_amz_credential": response["fields"]["x-amz-credential"],
            "x_amz_date": response["fields"]["x-amz-date"],
            "x_amz_signature": response["fields"]["x-amz-signature"],
            "policy": response["fields"]["policy"],
            "bucket": settings.MEDIA_BUCKET,
            "datalayer": input.datalayer,
            "store": store.id,
        }
        
        return base_models.MediaUploadGrant(
            x_amz_algorithm = aws["x_amz_algorithm"],
            x_amz_credential = aws["x_amz_credential"]
        )
            


    def generate_file_read_url(self, bucket_key: str, object_path: str, max_bytes: Optional[int] = None) -> AccessGrant:
        return self.grant_access(
            bucket_key,
            object_path,
            action="read",
            method="GET",
            allowed_methods=["GET", "HEAD"],
            body_format="none",
            max_bytes=max_bytes,
        )

    def generate_file_delete_url(self, bucket_key: str, object_path: str) -> AccessGrant:
        return self.grant_access(
            bucket_key,
            object_path,
            action="write",
            method="DELETE",
            allowed_methods=None,
            body_format="none",
        )

    def grant_access(
        self,
        bucket_key: str,
        object_path: str,
        *,
        action: str,
        method: str,
        allowed_methods: list[str] | None,
        body_format: str,
        max_bytes: Optional[int] = None,
    ) -> AccessGrant:
        """Generate a signed SeaweedFS filer URL for a specific object path."""
        full_path = self.build_object_path(bucket_key, object_path)

        conf = self.get_bucket_config(bucket_key)
        limit = max_bytes if max_bytes is not None else conf.default_max_bytes
        expires_in = 3600

        payload = {
            "action": action,
            "exp": int(time.time()) + expires_in,
        }
        print(payload)
        if allowed_methods:
            payload["allowed_methods"] = allowed_methods

        token = jwt.encode(payload, conf.jwt_key, algorithm="HS256")
        return AccessGrant(
            jwt=token,
            path=full_path,
            method=method,
            action=action,
            body_format=body_format,
            expires_in=expires_in,
            max_bytes=limit,
        )


dl = Datalayer()

def get_current_datalayer() -> Datalayer:
    return dl