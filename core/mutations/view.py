"""Standalone view mutations: resolve the org-scoped image, delegate to core.logic.views.

The input classes live in :mod:`core.inputs.views`; the per-kind creation
logic shared with the bulk ``fromArrayLike`` path lives in
:mod:`core.logic.views`.
"""

from kante.types import Info
import strawberry
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
from core.mutations._generic import make_delete


@strawberry.input(description="Input for deleting a view by ID")
class DeleteViewInput:
    """Input for deleting a view by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the view to delete")


def delete_view(
    info: Info,
    input: DeleteViewInput,
) -> strawberry.ID:
    item = get_for_org(models.View, info, id=input.id)
    item.delete()
    return input.id


@strawberry.input(description="Input for pinning or unpinning a view for quick access")
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
    image = get_for_org(models.Image, info, id=input.image)
    return view_logic.create_channel_view(image, input)


delete_channel_view = make_delete(models.ChannelView, DeleteViewInput)


def update_rgb_view(
    info: Info,
    input: UpdateRGBViewInput,
) -> types.RGBView:
    view = get_for_org(models.RGBView, info, id=input.id)

    # Update fields that are not None
    if input.z_min is not None:
        view.z_min = input.z_min
    if input.z_max is not None:
        view.z_max = input.z_max
    if input.x_min is not None:
        view.x_min = input.x_min
    if input.x_max is not None:
        view.x_max = input.x_max
    if input.y_min is not None:
        view.y_min = input.y_min
    if input.y_max is not None:
        view.y_max = input.y_max
    if input.t_min is not None:
        view.t_min = input.t_min
    if input.t_max is not None:
        view.t_max = input.t_max
    if input.c_min is not None:
        view.c_min = input.c_min
    if input.c_max is not None:
        view.c_max = input.c_max
    if input.gamma is not None:
        view.gamma = input.gamma
    if input.contrast_limit_min is not None:
        view.contrast_limit_min = input.contrast_limit_min
    if input.contrast_limit_max is not None:
        view.contrast_limit_max = input.contrast_limit_max
    if input.active is not None:
        view.active = input.active
    if input.color_map is not None:
        view.color_map = input.color_map
    if input.base_color is not None:
        view.base_color = input.base_color

    view.save()
    return view


def create_rgb_view(
    info: Info,
    input: RGBViewInput,
) -> types.RGBView:
    image = get_for_org(models.Image, info, id=input.image)
    context = get_for_org(models.RGBRenderContext, info, id=input.context)

    view = view_logic.get_or_create_rgb_view(image, input)
    context.views.add(view)
    return view


delete_rgb_view = make_delete(models.RGBView, DeleteViewInput)


def create_affine_transformation_view(
    info: Info,
    input: AffineTransformationViewInput,
) -> types.AffineTransformationView:
    image = get_for_org(models.Image, info, id=input.image)
    ctx = CreationContext.from_info(info)
    return view_logic.create_affine_transformation_view(image, input, info, ctx)


delete_affine_transformation_view = make_delete(models.AffineTransformationView, DeleteViewInput)


def create_label_view(
    info: Info,
    input: LabelViewInput,
) -> types.LabelView:
    image = get_for_org(models.Image, info, id=input.image)
    return view_logic.create_label_view(image, input)


delete_label_view = make_delete(models.LabelView, DeleteViewInput)


def create_derived_view(
    info: Info,
    input: DerivedViewInput,
) -> types.DerivedView:
    image = get_for_org(models.Image, info, id=input.image)
    return view_logic.create_derived_view(image, input, info)


def create_roi_view(
    info: Info,
    input: ROIViewInput,
) -> types.ROIView:
    image = get_for_org(models.Image, info, id=input.image)
    return view_logic.create_roi_view(image, input, info)


def create_file_view(
    info: Info,
    input: FileViewInput,
) -> types.FileView:
    image = get_for_org(models.Image, info, id=input.image)
    return view_logic.create_file_view(image, input, info)


def create_acquisition_view(
    info: Info,
    input: AcquisitionViewInput,
) -> types.AcquisitionView:
    image = get_for_org(models.Image, info, id=input.image)
    return view_logic.create_acquisition_view(image, input)


def create_histogram_view(
    info: Info,
    input: HistogramViewInput,
) -> types.HistogramView:
    image = get_for_org(models.Image, info, id=input.image)
    return view_logic.create_histogram_view(image, input)


delete_histogram_view = make_delete(models.HistogramView, DeleteViewInput)


def create_continous_scan_view(
    info: Info,
    input: ContinousScanViewInput,
) -> types.ContinousScanView:
    image = get_for_org(models.Image, info, id=input.image)
    return view_logic.create_continous_scan_view(image, input)


def create_lightpath_view(
    info: Info,
    input: LightpathViewInput,
) -> types.LightpathView:
    image = get_for_org(models.Image, info, id=input.image)
    return view_logic.create_lightpath_view(image, input)


def create_well_position_view(
    info: Info,
    input: WellPositionViewInput,
) -> types.WellPositionView:
    image = get_for_org(models.Image, info, id=input.image)
    return view_logic.create_well_position_view(image, input, info)


def create_timepoint_view(
    info: Info,
    input: TimepointViewInput,
) -> types.TimepointView:
    image = get_for_org(models.Image, info, id=input.image)
    ctx = CreationContext.from_info(info)
    return view_logic.create_timepoint_view(image, input, info, ctx)


delete_timepoint_view = make_delete(models.TimepointView, DeleteViewInput)


def create_optics_view(
    info: Info,
    input: OpticsViewInput,
) -> types.OpticsView:
    image = get_for_org(models.Image, info, id=input.image)
    return view_logic.create_optics_view(image, input)


delete_optics_view = make_delete(models.OpticsView, DeleteViewInput)


def create_mask_view(
    info: Info,
    input: MaskViewInput,
) -> types.MaskView:
    image = get_for_org(models.Image, info, id=input.image)
    return view_logic.create_mask_view(image, input)


def create_instance_mask_view(
    info: Info,
    input: InstanceMaskViewInput,
) -> types.InstanceMaskView:
    image = get_for_org(models.Image, info, id=input.image)
    return view_logic.create_instance_mask_view(image, input, info)


def create_reference_view(
    info: Info,
    input: ReferenceViewInput,
) -> types.ReferenceView:
    image = get_for_org(models.Image, info, id=input.image)
    return view_logic.create_reference_view(image, input)
