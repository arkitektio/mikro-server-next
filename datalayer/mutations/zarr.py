from kante.types import Info
from datalayer import types, models, inputs

from ._stores import finish_store_upload, request_store_upload


def request_zarr_upload(info: Info, input: inputs.RequestMediaUploadInput) -> types.StoreUploadGrant:
    """Request a signed SeaweedFS upload grant for a Zarr store."""
    model = input.to_pydantic()
    grant, store = request_store_upload(input, models.ZarrStore, "zarr")

    return types.StoreUploadGrant(
        **grant.model_dump(),
        datalayer="zarr",
        key=store.key,
        original_file_name=model.original_file_name,
        upload_file_name=store.get_upload_file_name(),
        upload_content_type=model.content_type,
        upload_form_field="file",
        store=store.pk,
    )


def finish_zarr_upload(info: Info, input: inputs.FinishMediaUploadInput) -> types.ZarrStore:
    """Mark the ZarrStore as populated after a successful upload."""
    finish_store_upload(input, models.ZarrStore, "ZarrStore")
