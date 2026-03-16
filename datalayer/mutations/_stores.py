from collections.abc import Callable, Mapping
from typing import Any, TypeVar, cast

from datalayer import inputs, models
from datalayer.datalayer import AccessGrant, get_current_datalayer

StoreType = TypeVar("StoreType", bound=models.DatalayerStore)
FinishUploadInput = (
    inputs.FinishMediaUploadInput
    | inputs.FinishBigFileUploadInput
    | inputs.FinishZarrUploadInput
    | inputs.FinishParquetUploadInput
)


def generate_storage_key(
    source_name: str | None = None,
    generator: Callable[[], str] = models.get_default_upload_token,
) -> str:
    """Generate an opaque storage key for a store upload request."""
    return models.build_opaque_storage_key(source_name or "", generator=generator)


def create_store_upload(
    store_model: type[StoreType],
    bucket_key: str,
    storage_key: str,
    *,
    max_bytes: int | None = None,
    store_defaults: Mapping[str, Any] | None = None,
) -> tuple[AccessGrant, StoreType]:
    """Create or reuse a store row and return its signed upload grant."""
    datalayer = get_current_datalayer()
    grant = datalayer.generate_file_upload_url(
        bucket_key, storage_key, max_bytes=max_bytes
    )
    path = datalayer.build_store_path(bucket_key, storage_key)

    defaults: dict[str, Any] = {
        "key": storage_key,
        "bucket": bucket_key,
        "path": path,
    }
    if store_defaults:
        defaults.update(dict(store_defaults))

    store, _ = store_model.objects.get_or_create(
        path=path,
        defaults=defaults,
    )

    update_fields: list[str] = []
    for field_name, value in defaults.items():
        if getattr(store, field_name) != value:
            setattr(store, field_name, value)
            update_fields.append(field_name)

    if update_fields:
        store.save(update_fields=update_fields)

    return grant, store


def request_media_store_upload(
    input: inputs.RequestMediaUploadInput,
    key_generator: Callable[[], str] = models.get_default_upload_token,
) -> tuple[AccessGrant, models.MediaStore]:
    """Create or reuse a media store row and return its signed upload grant."""
    model = cast(Any, input).to_pydantic()
    storage_key = generate_storage_key(model.original_file_name, generator=key_generator)
    return create_store_upload(
        models.MediaStore,
        "media",
        storage_key,
        max_bytes=model.file_size,
        store_defaults={
            "original_file_name": model.original_file_name,
            "content_type": model.content_type,
        },
    )


def request_bigfile_store_upload(
    input: inputs.RequestBigFileUploadInput,
    key_generator: Callable[[], str] = models.get_default_upload_token,
) -> tuple[AccessGrant, models.BigFileStore]:
    """Create or reuse a big file store row and return its signed upload grant."""
    model = cast(Any, input).to_pydantic()
    storage_key = generate_storage_key(model.original_file_name, generator=key_generator)
    return create_store_upload(
        models.BigFileStore,
        "bigfile",
        storage_key,
        max_bytes=model.file_size,
        store_defaults={
            "original_file_name": model.original_file_name,
            "content_type": model.content_type,
        },
    )


def request_zarr_store_upload(
    input: inputs.RequestZarrUploadInput,
    key_generator: Callable[[], str] = models.get_default_upload_token,
) -> tuple[AccessGrant, models.ZarrStore]:
    """Create or reuse a zarr store row and return its signed upload grant."""
    model = cast(Any, input).to_pydantic()
    storage_key = generate_storage_key(generator=key_generator)
    return create_store_upload(
        models.ZarrStore,
        "zarr",
        storage_key,
        store_defaults={
            "shape": model.shape,
            "chunks": model.chunks,
            "version": model.version,
        },
    )


def request_parquet_store_upload(
    input: inputs.RequestParquetUploadInput,
    key_generator: Callable[[], str] = models.get_default_upload_token,
) -> tuple[AccessGrant, models.ParquetStore]:
    """Create or reuse a parquet store row and return its signed upload grant."""
    model = cast(Any, input).to_pydantic()
    storage_key = generate_storage_key(model.original_file_name, generator=key_generator)
    return create_store_upload(
        models.ParquetStore,
        "parquet",
        storage_key,
        store_defaults={
            "original_file_name": model.original_file_name,
            "content_type": model.content_type,
        },
    )


def finish_store_upload(
    input: FinishUploadInput, store_model: type[StoreType], store_label: str
) -> StoreType:
    """Finalize or delete a store row once the client upload has completed."""
    model = cast(Any, input).to_pydantic()
    try:
        store = store_model.objects.get(pk=model.store_id)
    except store_model.DoesNotExist as exc:
        raise ValueError(
            f"{store_label} with id {model.store_id} does not exist"
        ) from exc

    if not model.valid:
        store.delete()
        raise ValueError("Upload marked as invalid, store deleted")

    store.fill_info()
    return store
