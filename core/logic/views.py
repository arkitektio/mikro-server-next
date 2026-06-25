"""Creation of image views, one explicit function per view kind.

This is the single implementation behind both the bulk path
(``fromArrayLike`` with nested ``Partial*ViewInput`` lists) and the
standalone ``create*View`` mutations, which previously duplicated each
other and had drifted apart. Each creator takes the already org-scoped
``image`` plus the input; creators that resolve further IDs take ``info``
for org scoping, and creators that auto-create fallback objects
(``Stage``, ``Era``) take a :class:`~core.creation.CreationContext` to
stamp provenance on them.
"""

import logging

import strawberry
from django.contrib.auth import get_user_model
from kante.types import Info

from core import enums, models
from core.creation import CreationContext
from core.inputs.views import (
    PartialAcquisitionViewInput,
    PartialAffineTransformationViewInput,
    PartialChannelViewInput,
    PartialContinoussScanViewInput,
    PartialDerivedViewInput,
    PartialFileViewInput,
    PartialHistogramViewInput,
    PartialInstanceMaskViewInput,
    PartialLabelViewInput,
    PartialLightpathViewInput,
    PartialMaskViewInput,
    PartialOpticsViewInput,
    PartialRGBViewInput,
    PartialROIViewInput,
    PartialReferenceViewInput,
    PartialScaleViewInput,
    PartialTimepointViewInput,
    PartialWellPositionViewInput,
    view_kwargs_from_input,
)
from core.scoping import get_for_org

logger = logging.getLogger(__name__)


def create_channel_view(image: models.Image, input: PartialChannelViewInput) -> models.ChannelView:
    """Create a channel view on ``image``."""
    return models.ChannelView.objects.create(
        image=image,
        acquisition_mode=input.acquisition_mode,
        excitation_wavelength=input.excitation_wavelength,
        emission_wavelength=input.emission_wavelength,
        name=input.name,
        **view_kwargs_from_input(input),
    )


def create_label_view(image: models.Image, input: PartialLabelViewInput) -> models.LabelView:
    """Create a label view on ``image``."""
    return models.LabelView.objects.create(
        image=image,
        label=input.label,
        **view_kwargs_from_input(input),
    )


def create_lightpath_view(image: models.Image, input: PartialLightpathViewInput) -> models.LightpathView:
    """Create a lightpath view on ``image``, serializing the graph input to JSON."""
    return models.LightpathView.objects.create(
        image=image,
        graph=strawberry.asdict(input.graph),
        **view_kwargs_from_input(input),
    )


def create_derived_view(image: models.Image, input: PartialDerivedViewInput, info: Info) -> models.DerivedView:
    """Create a derived view linking ``image`` to its org-scoped origin image."""
    origin_image = get_for_org(models.Image, info, id=input.origin_image)
    return models.DerivedView.objects.create(
        image=image,
        origin_image=origin_image,
        **view_kwargs_from_input(input),
    )


def create_roi_view(image: models.Image, input: PartialROIViewInput, info: Info) -> models.ROIView:
    """Create a ROI view on ``image`` referencing an org-scoped ROI."""
    return models.ROIView.objects.create(
        image=image,
        roi=get_for_org(models.ROI, info, id=input.roi),
        **view_kwargs_from_input(input),
    )


def create_file_view(image: models.Image, input: PartialFileViewInput, info: Info) -> models.FileView:
    """Create a file view on ``image`` referencing an org-scoped file."""
    return models.FileView.objects.create(
        image=image,
        file=get_for_org(models.File, info, id=input.file),
        series_identifier=input.series_identifier,
        **view_kwargs_from_input(input),
    )


def create_timepoint_view(
    image: models.Image,
    input: PartialTimepointViewInput,
    info: Info,
    ctx: CreationContext,
    fallback_suffix: str = "",
) -> models.TimepointView:
    """Create a timepoint view on ``image``, auto-creating a provenance-stamped Era if none is given."""
    era = (
        get_for_org(models.Era, info, id=input.era)
        if input.era
        else models.Era.objects.create(
            name=f"Unknown for {image.name}{fallback_suffix}",
            organization=ctx.organization,
            **ctx.provenance_kwargs(),
        )
    )
    return models.TimepointView.objects.create(
        image=image,
        era=era,
        ms_since_start=input.ms_since_start,
        index_since_start=input.index_since_start,
        **view_kwargs_from_input(input),
    )


def create_affine_transformation_view(
    image: models.Image,
    input: PartialAffineTransformationViewInput,
    info: Info,
    ctx: CreationContext,
    fallback_suffix: str = "",
) -> models.AffineTransformationView:
    """Create an affine transformation view on ``image``, auto-creating a provenance-stamped Stage if none is given."""
    stage = (
        get_for_org(models.Stage, info, id=input.stage)
        if input.stage
        else models.Stage.objects.create(
            name=f"Unknown for {image.name}{fallback_suffix}",
            organization=ctx.organization,
            **ctx.provenance_kwargs(),
        )
    )
    return models.AffineTransformationView.objects.create(
        image=image,
        stage=stage,
        affine_matrix=input.affine_matrix,
        **view_kwargs_from_input(input),
    )


def create_reference_view(image: models.Image, input: PartialReferenceViewInput) -> models.ReferenceView:
    """Create a reference view on ``image``."""
    return models.ReferenceView.objects.create(
        image=image,
        **view_kwargs_from_input(input),
    )


def create_mask_view(image: models.Image, input: PartialMaskViewInput) -> models.MaskView:
    """Create a mask view on ``image``."""
    return models.MaskView.objects.create(
        image=image,
        reference_view_id=input.reference_view,
        **view_kwargs_from_input(input),
    )


def create_instance_mask_view(image: models.Image, input: PartialInstanceMaskViewInput, info: Info) -> models.InstanceMaskView:
    """Create an instance mask view on ``image``, resolving the optional org-scoped labels store."""
    labels = None
    if input.labels is not None:
        labels_store = get_for_org(models.ParquetStore, info, id=input.labels)
        labels_store.fill_info()
        labels = labels_store

    return models.InstanceMaskView.objects.create(
        image=image,
        reference_view_id=input.reference_view,
        labels=labels,
        **view_kwargs_from_input(input),
    )


def create_scale_view(image: models.Image, input: PartialScaleViewInput) -> models.ScaleView:
    """Create a scale view on ``image``; unset scale factors default to 1."""
    return models.ScaleView.objects.create(
        image=image,
        parent_id=input.parent,
        scale_x=input.scale_x or 1,
        scale_y=input.scale_y or 1,
        scale_z=input.scale_z or 1,
        scale_c=input.scale_c or 1,
        scale_t=input.scale_t or 1,
        **view_kwargs_from_input(input),
    )


def create_acquisition_view(image: models.Image, input: PartialAcquisitionViewInput) -> models.AcquisitionView:
    """Create an acquisition view on ``image``."""
    return models.AcquisitionView.objects.create(
        image=image,
        description=input.description,
        acquired_at=input.acquired_at,
        operator=(get_user_model().objects.get(id=input.operator) if input.operator else None),
        **view_kwargs_from_input(input),
    )


def create_optics_view(image: models.Image, input: PartialOpticsViewInput) -> models.OpticsView:
    """Create an optics view on ``image``."""
    return models.OpticsView.objects.create(
        image=image,
        instrument_id=input.instrument,
        objective_id=input.objective,
        camera_id=input.camera,
        **view_kwargs_from_input(input),
    )


def create_histogram_view(image: models.Image, input: PartialHistogramViewInput) -> models.HistogramView:
    """Create a histogram view on ``image``."""
    return models.HistogramView.objects.create(
        image=image,
        histogram=input.histogram,
        bins=input.bins,
        min=input.min,
        max=input.max,
        **view_kwargs_from_input(input),
    )


def create_continous_scan_view(image: models.Image, input: PartialContinoussScanViewInput) -> models.ContinousScanView:
    """Create a continuous scan view on ``image``."""
    return models.ContinousScanView.objects.create(
        image=image,
        direction=input.direction,
        **view_kwargs_from_input(input),
    )


def create_well_position_view(image: models.Image, input: PartialWellPositionViewInput, info: Info) -> models.WellPositionView:
    """Create a well position view on ``image``, resolving the optional org-scoped well plate."""
    well = get_for_org(models.MultiWellPlate, info, id=input.well) if input.well else None
    return models.WellPositionView.objects.create(
        image=image,
        well=well,
        row=input.row,
        column=input.column,
        **view_kwargs_from_input(input),
    )


def get_or_create_rgb_view(image: models.Image, input: PartialRGBViewInput) -> models.RGBView:
    """Get or create an RGB view on ``image`` with the given render settings.

    RGB views are deduplicated on their render settings; linking the view to a
    render context (the ``contexts`` many-to-many) is the caller's job because
    the bulk path shares one default context across the whole input list.
    """
    view, _ = models.RGBView.objects.update_or_create(
        image=image,
        c_max=input.c_max,
        c_min=input.c_min,
        gamma=input.gamma,
        contrast_limit_min=input.contrast_limit_min,
        contrast_limit_max=input.contrast_limit_max,
        active=input.active if input.active is not None else True,
        color_map=(input.color_map if input.color_map is not None else "gray"),
        base_color=input.base_color if input.base_color else None,
    )
    return view


def auto_create_views(image: models.Image) -> None:
    """Create a default RGB render context with per-channel views for a fresh image."""
    if image.rgb_views.count() != 0:
        logger.info("Views already created")
        return

    if image.store.c_size == 3:
        rgb_context = models.RGBRenderContext.objects.create(image=image, name="RGB", description="Default RGB Context")

        red_view = models.RGBView.objects.create(image=image, color_map=enums.ColorMapChoices.RED, c_min=0, c_max=1)
        green_view = models.RGBView.objects.create(image=image, color_map=enums.ColorMapChoices.GREEN, c_min=1, c_max=2)
        blue_view = models.RGBView.objects.create(image=image, color_map=enums.ColorMapChoices.BLUE, c_min=2, c_max=3)

        rgb_context.views.add(red_view, green_view, blue_view)

    else:
        rgb_context = models.RGBRenderContext.objects.create(image=image, name="Default", description="Default")

        for i in range(image.store.c_size):
            x = models.RGBView.objects.create(
                image=image,
                color_map=enums.ColorMapChoices.VIRIDIS,
                c_min=i,
                c_max=i + 1,
                active=i == 0,
            )
            rgb_context.views.add(x)
