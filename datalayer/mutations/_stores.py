from collections.abc import Callable
from typing import TypeVar

from datalayer import inputs, models
from datalayer.datalayer import AccessGrant, get_current_datalayer

StoreType = TypeVar("StoreType", bound=models.DatalayerStore)


def generate_storage_key(original_file_name: str, generator: Callable[[], str] = models.get_default_upload_token) -> str:
    """Generate an opaque storage key for a client-provided file name."""
    return models.build_opaque_storage_key(original_file_name, generator=generator)


def request_store_upload(
    input: inputs.RequestMediaUploadInput,
    store_model: type[StoreType],
    bucket_key: str,
    key_generator: Callable[[], str] = models.get_default_upload_token,
) -> tuple[AccessGrant, StoreType]:
    """Create or reuse a store row and return its signed upload grant."""
    datalayer = get_current_datalayer()
    model = input.to_pydantic()
    storage_key = generate_storage_key(model.original_file_name, generator=key_generator)
    grant = datalayer.generate_file_upload_url(bucket_key, storage_key, max_bytes=model.file_size)
    path = datalayer.build_store_path(bucket_key, storage_key)

    store, _ = store_model.objects.get_or_create(
        path=path,
        defaults={
            "key": storage_key,
            "bucket": bucket_key,
            "original_file_name": model.original_file_name,
            "content_type": model.content_type,
        },
    )

    if store.key != storage_key or store.bucket != bucket_key or store.path != path or store.original_file_name != model.original_file_name or store.content_type != model.content_type:
        store.key = storage_key
        store.bucket = bucket_key
        store.path = path
        store.original_file_name = model.original_file_name
        store.content_type = model.content_type
        store.save(update_fields=["key", "bucket", "path", "original_file_name", "content_type"])

    return grant, store


def finish_store_upload(input: inputs.FinishMediaUploadInput, store_model: type[StoreType], store_label: str) -> None:
    """Finalize or delete a store row once the client upload has completed."""
    model = input.to_pydantic()
    try:
        store = store_model.objects.get(pk=model.store_id)
    except store_model.DoesNotExist as exc:
        raise ValueError(f"{store_label} with id {model.store_id} does not exist") from exc

    if not model.valid:
        store.delete()
        raise ValueError("Upload marked as invalid, store deleted")

    store.fill_info()
