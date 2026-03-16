from kante.types import Info
from typing import cast
from datalayer import inputs, models, types

from ._stores import finish_store_upload, request_zarr_store_upload


def request_zarr_upload(
    info: Info, input: inputs.RequestZarrUploadInput
) -> types.ZarrUploadGrant:
    """Request a signed SeaweedFS upload grant for a Zarr store."""
    del info
    grant, store = request_zarr_store_upload(input)

    return types.ZarrUploadGrant(
        **grant.model_dump(),
        datalayer="zarr",
        key=store.key,
        upload_file_name=store.get_upload_file_name(),
        upload_form_field="file",
        store=store.pk,
    )


def finish_zarr_upload(
    info: Info, input: inputs.FinishZarrUploadInput
) -> types.ZarrStore:
    """Mark the ZarrStore as populated after a successful upload."""
    del info
    return cast(
        types.ZarrStore, finish_store_upload(input, models.ZarrStore, "ZarrStore")
    )
