"""Standalone view mutations: resolve the org-scoped image, delegate to core.logic.views.

The input classes live in :mod:`core.inputs.views`; the per-kind creation
logic shared with the bulk ``fromArrayLike`` path lives in
:mod:`core.logic.views`.
"""

from kante.types import Info
import strawberry
import kante
from pydantic import BaseModel, Field
from core import types, models
from core.creation import CreationContext
from core.inputs.views import (
    AcquisitionViewInput,
    AffineTransformationViewInput,
    ChannelViewInput,
    ContinousScanViewInput,
    DerivedViewInput,
    FileViewInput,
    HistogramViewInput,
    InstanceMaskViewInput,
    LabelViewInput,
    LightpathViewInput,
    MaskViewInput,
    OpticsViewInput,
    ROIViewInput,
    ReferenceViewInput,
    RGBViewInput,
    TimepointViewInput,
    UpdateRGBViewInput,
    WellPositionViewInput,
)
from core.logic import views as view_logic
from core.scoping import get_for_org
from core.mutations._generic import make_delete, assert_can_delete, image_owner


class DeleteViewInputModel(BaseModel):
    id: str = Field(description="The ID of the view to delete")


@kante.pydantic_input(DeleteViewInputModel, description="Input for deleting a view by ID")
class DeleteViewInput:
    """Input for deleting a view by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the view to delete")


def delete_view(
    info: Info,
    input: DeleteViewInput,
) -> strawberry.ID:
    parsed = input.to_pydantic()
    item = get_for_org(models.View, info, id=parsed.id)
    assert_can_delete(info, item, image_owner)
    item.delete()
    return parsed.id


class PinViewInputModel(BaseModel):
    id: str = Field(description="The ID of the view to pin or unpin")
    pin: bool = Field(description="True to pin, false to unpin")


@kante.pydantic_input(PinViewInputModel, description="Input for pinning or unpinning a view for quick access")
class PinViewInput:
    """Input for pinning or unpinning a view for quick access"""

    id: strawberry.ID = strawberry.field(description="The ID of the view to pin or unpin")
    pin: bool = strawberry.field(description="True to pin, false to unpin")


def pin_view(
    info: Info,
    input: PinViewInput,
) -> types.View:
    raise NotImplementedError("TODO")


def create_channel_view(
    info: Info,
    input: ChannelViewInput,
) -> types.ChannelView:
    parsed = input.to_pydantic()
    image = get_for_org(models.Image, info, id=parsed.image)
    return view_logic.create_channel_view(image, parsed)


delete_channel_view = make_delete(models.ChannelView, DeleteViewInput, owner=image_owner)


def update_rgb_view(
    info: Info,
    input: UpdateRGBViewInput,
) -> types.RGBView:
    parsed = input.to_pydantic()
    view = get_for_org(models.RGBView, info, id=parsed.id)

    # Update fields that are not None
    if parsed.z_min is not None:
        view.z_min = parsed.z_min
    if parsed.z_max is not None:
        view.z_max = parsed.z_max
    if parsed.x_min is not None:
        view.x_min = parsed.x_min
    if parsed.x_max is not None:
        view.x_max = parsed.x_max
    if parsed.y_min is not None:
        view.y_min = parsed.y_min
    if parsed.y_max is not None:
        view.y_max = parsed.y_max
    if parsed.t_min is not None:
        view.t_min = parsed.t_min
    if parsed.t_max is not None:
        view.t_max = parsed.t_max
    if parsed.c_min is not None:
        view.c_min = parsed.c_min
    if parsed.c_max is not None:
        view.c_max = parsed.c_max
    if parsed.gamma is not None:
        view.gamma = parsed.gamma
    if parsed.contrast_limit_min is not None:
        view.contrast_limit_min = parsed.contrast_limit_min
    if parsed.contrast_limit_max is not None:
        view.contrast_limit_max = parsed.contrast_limit_max
    if parsed.active is not None:
        view.active = parsed.active
    if parsed.color_map is not None:
        view.color_map = parsed.color_map
    if parsed.base_color is not None:
        view.base_color = parsed.base_color

    view.save()
    return view


def create_rgb_view(
    info: Info,
    input: RGBViewInput,
) -> types.RGBView:
    parsed = input.to_pydantic()
    image = get_for_org(models.Image, info, id=parsed.image)
    context = get_for_org(models.RGBRenderContext, info, id=parsed.context)

    view = view_logic.get_or_create_rgb_view(image, parsed)
    context.views.add(view)
    return view


delete_rgb_view = make_delete(models.RGBView, DeleteViewInput, owner=image_owner)


def create_affine_transformation_view(
    info: Info,
    input: AffineTransformationViewInput,
) -> types.AffineTransformationView:
    parsed = input.to_pydantic()
    image = get_for_org(models.Image, info, id=parsed.image)
    ctx = CreationContext.from_info(info)
    return view_logic.create_affine_transformation_view(image, parsed, info, ctx)


delete_affine_transformation_view = make_delete(models.AffineTransformationView, DeleteViewInput, owner=image_owner)


def create_label_view(
    info: Info,
    input: LabelViewInput,
) -> types.LabelView:
    parsed = input.to_pydantic()
    image = get_for_org(models.Image, info, id=parsed.image)
    return view_logic.create_label_view(image, parsed)


delete_label_view = make_delete(models.LabelView, DeleteViewInput, owner=image_owner)


def create_derived_view(
    info: Info,
    input: DerivedViewInput,
) -> types.DerivedView:
    parsed = input.to_pydantic()
    image = get_for_org(models.Image, info, id=parsed.image)
    return view_logic.create_derived_view(image, parsed, info)


def create_roi_view(
    info: Info,
    input: ROIViewInput,
) -> types.ROIView:
    parsed = input.to_pydantic()
    image = get_for_org(models.Image, info, id=parsed.image)
    return view_logic.create_roi_view(image, parsed, info)


def create_file_view(
    info: Info,
    input: FileViewInput,
) -> types.FileView:
    parsed = input.to_pydantic()
    image = get_for_org(models.Image, info, id=parsed.image)
    return view_logic.create_file_view(image, parsed, info)


def create_acquisition_view(
    info: Info,
    input: AcquisitionViewInput,
) -> types.AcquisitionView:
    parsed = input.to_pydantic()
    image = get_for_org(models.Image, info, id=parsed.image)
    return view_logic.create_acquisition_view(image, parsed)


def create_histogram_view(
    info: Info,
    input: HistogramViewInput,
) -> types.HistogramView:
    parsed = input.to_pydantic()
    image = get_for_org(models.Image, info, id=parsed.image)
    return view_logic.create_histogram_view(image, parsed)


delete_histogram_view = make_delete(models.HistogramView, DeleteViewInput, owner=image_owner)


def create_continous_scan_view(
    info: Info,
    input: ContinousScanViewInput,
) -> types.ContinousScanView:
    parsed = input.to_pydantic()
    image = get_for_org(models.Image, info, id=parsed.image)
    return view_logic.create_continous_scan_view(image, parsed)


def create_lightpath_view(
    info: Info,
    input: LightpathViewInput,
) -> types.LightpathView:
    parsed = input.to_pydantic()
    image = get_for_org(models.Image, info, id=parsed.image)
    return view_logic.create_lightpath_view(image, parsed)


def create_well_position_view(
    info: Info,
    input: WellPositionViewInput,
) -> types.WellPositionView:
    parsed = input.to_pydantic()
    image = get_for_org(models.Image, info, id=parsed.image)
    return view_logic.create_well_position_view(image, parsed, info)


def create_timepoint_view(
    info: Info,
    input: TimepointViewInput,
) -> types.TimepointView:
    parsed = input.to_pydantic()
    image = get_for_org(models.Image, info, id=parsed.image)
    ctx = CreationContext.from_info(info)
    return view_logic.create_timepoint_view(image, parsed, info, ctx)


delete_timepoint_view = make_delete(models.TimepointView, DeleteViewInput, owner=image_owner)


def create_optics_view(
    info: Info,
    input: OpticsViewInput,
) -> types.OpticsView:
    parsed = input.to_pydantic()
    image = get_for_org(models.Image, info, id=parsed.image)
    return view_logic.create_optics_view(image, parsed)


delete_optics_view = make_delete(models.OpticsView, DeleteViewInput, owner=image_owner)


def create_mask_view(
    info: Info,
    input: MaskViewInput,
) -> types.MaskView:
    parsed = input.to_pydantic()
    image = get_for_org(models.Image, info, id=parsed.image)
    return view_logic.create_mask_view(image, parsed)


def create_instance_mask_view(
    info: Info,
    input: InstanceMaskViewInput,
) -> types.InstanceMaskView:
    parsed = input.to_pydantic()
    image = get_for_org(models.Image, info, id=parsed.image)
    return view_logic.create_instance_mask_view(image, parsed, info)


def create_reference_view(
    info: Info,
    input: ReferenceViewInput,
) -> types.ReferenceView:
    parsed = input.to_pydantic()
    image = get_for_org(models.Image, info, id=parsed.image)
    return view_logic.create_reference_view(image, parsed)
