import jwt
import time
from contextvars import ContextVar
from typing import Optional
from urllib.parse import SplitResult, quote, urlencode, urlsplit, urlunsplit

from django.conf import settings
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

# Context variable for the datalayer instance
datalayer: ContextVar["Datalayer"] = ContextVar("datalayer")


class BucketConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    path: str = Field(..., validation_alias=AliasChoices("PATH", "path"))
    jwt_key: str = Field(..., validation_alias=AliasChoices("JWT_KEY", "jwt_key"))
    default_max_bytes: int = Field(
        100 * 1024 * 1024,
        validation_alias=AliasChoices("DEFAULT_MAX_BYTES", "default_max_bytes"),
    )


class DatalayerConfig(BaseModel):
    bigfile: Optional[BucketConfig] = None
    media: Optional[BucketConfig] = None
    zarr: Optional[BucketConfig] = None
    parquet: Optional[BucketConfig] = None


class AccessGrant(BaseModel):
    jwt: str
    path: str
    method: str
    action: str
    body_format: str
    expires_in: int
    max_bytes: int


class Datalayer:
    def __init__(self):
        self.config = DatalayerConfig(**settings.DATALAYER)

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
            raise ValueError(
                f"Service/Bucket '{bucket_key}' not configured in datalayer."
            )
        return conf

    def build_store_path(self, bucket_key: str, object_path: str) -> str:
        return f"seaweed://{bucket_key}/{object_path.lstrip('/')}"

    def build_object_path(self, bucket_key: str, object_path: str) -> str:
        conf = self.get_bucket_config(bucket_key)
        return f"/{conf.path.strip('/')}/{object_path.lstrip('/')}"

    def generate_file_upload_url(
        self, bucket_key: str, object_path: str, max_bytes: Optional[int] = None
    ) -> AccessGrant:
        return self.grant_access(
            bucket_key,
            object_path,
            action="write",
            method="POST",
            allowed_methods=["POST"],
            body_format="multipart",
            max_bytes=max_bytes,
        )

    def generate_file_read_url(
        self, bucket_key: str, object_path: str, max_bytes: Optional[int] = None
    ) -> AccessGrant:
        return self.grant_access(
            bucket_key,
            object_path,
            action="read",
            method="GET",
            allowed_methods=["GET", "HEAD"],
            body_format="none",
            max_bytes=max_bytes,
        )

    def generate_file_delete_url(
        self, bucket_key: str, object_path: str
    ) -> AccessGrant:
        return self.grant_access(
            bucket_key,
            object_path,
            action="write",
            method="DELETE",
            allowed_methods=["DELETE"],
            body_format="none",
        )

    def grant_access(
        self,
        bucket_key: str,
        object_path: str,
        *,
        action: str,
        method: str,
        allowed_methods: list[str],
        body_format: str,
        max_bytes: Optional[int] = None,
    ) -> AccessGrant:
        """Generate a signed SeaweedFS filer URL for a specific object path."""
        full_path = self.build_object_path(bucket_key, object_path)

        conf = self.get_bucket_config(bucket_key)
        limit = max_bytes if max_bytes is not None else conf.default_max_bytes
        expires_in = 3600

        payload = {
            "allowed_prefixes": [full_path],
            "allowed_methods": allowed_methods,
            "exp": int(time.time()) + expires_in,
            "limit": limit,
        }

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


def get_current_datalayer() -> Datalayer:
    try:
        return datalayer.get()
    except LookupError:
        dl = Datalayer()
        datalayer.set(dl)
        return dl
