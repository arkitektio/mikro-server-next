from kante.types import Info
from typing import cast
from datalayer import inputs, types
from datalayer.datalayer import get_current_datalayer


def request_zarr_upload(
    info: Info, input: inputs.RequestZarrUploadInput
) -> types.ZarrUploadGrant:
    """Request temporary S3 upload credentials for a Zarr store."""
    del info
    dl = get_current_datalayer()
    input_model = getattr(input, "to_pydantic")()
    return types.ZarrUploadGrant.from_pydantic(dl.generate_zarr_upload_grant(input_model))


def finish_zarr_upload(
    info: Info, input: inputs.FinishZarrUploadInput
) -> types.ZarrStore:
    """Mark the ZarrStore as populated after a successful upload."""
    del info
    dl = get_current_datalayer()
    input_model = getattr(input, "to_pydantic")()
    return cast(types.ZarrStore, dl.finish_zarr_upload(input_model))
