from kante.types import Info
import strawberry

from core import types, models, scalars
from datalayer.datalayer import get_current_datalayer
from .view import (
    PartialChannelViewInput,
    PartialDerivedViewInput,
    PartialFileViewInput,
    PartialROIViewInput,
    PartialTimepointViewInput,
    PartialRGBViewInput,
    PartialOpticsViewInput,
    PartialMaskViewInput,
    PartialAcquisitionViewInput,
    PartialAffineTransformationViewInput,
    PartialInstanceMaskViewInput,
    PartialReferenceViewInput,
    PartialLightpathViewInput,
    PartialScaleViewInput,
    _create_mask_view_from_partial,
    _create_instance_mask_view_from_partial,
    view_kwargs_from_input,
)
from django.contrib.auth import get_user_model
from core.managers import auto_create_views
from core.scoping import get_for_org
from core.mutations._generic import make_pin


@strawberry.input
class SetAsOriginInput:
    child: strawberry.ID
    origin: bool


def set_other_as_origin(
    info: Info,
    input: SetAsOriginInput,
) -> types.Image:
    image = get_for_org(models.Image, info, id=input.child)
    other = get_for_org(models.Image, info, id=input.origin)

    image.origins.add(other)
    return image


def relate_to_dataset(
    info: Info,
    id: strawberry.ID,
    other: strawberry.ID,
) -> types.Image:
    image = get_for_org(models.Image, info, id=id)
    other = get_for_org(models.Dataset, info, id=other)

    return image


@strawberry.input
class PinImageInput:
    id: strawberry.ID
    pin: bool


pin_image = make_pin(models.Image, PinImageInput, types.Image)


@strawberry.input
class UpdateImageInput:
    id: strawberry.ID
    tags: list[str] | None = None
    name: str | None = None


def update_image(
    info: Info,
    input: UpdateImageInput,
) -> types.Image:
    image = get_for_org(models.Image, info, id=input.id)

    if input.tags:
        image.tags.add(*input.tags)

    if input.name:
        image.name = input.name

    image.save()

    return image


@strawberry.input()
class DeleteImageInput:
    id: strawberry.ID


def delete_image(
    info: Info,
    input: DeleteImageInput,
) -> strawberry.ID:
    item = get_for_org(models.Image, info, id=input.id)
    assert item.creator == info.context.request.user, "You can only delete your own images"

    item.delete()
    return input.id


@strawberry.input(description="Input type for creating an image from an array-like object")
class FromArrayLikeInput:
    array: scalars.ImageLike = strawberry.field(description="The array-like object to create the image from")
    name: str = strawberry.field(description="The name of the image")
    dataset: strawberry.ID | None = strawberry.field(default=None, description="Optional dataset ID to associate the image with")
    channel_views: list[PartialChannelViewInput] | None = strawberry.field(default=None, description="Optional list of channel views")
    transformation_views: list[PartialAffineTransformationViewInput] | None = strawberry.field(default=None, description="Optional list of affine transformation views")
    acquisition_views: list[PartialAcquisitionViewInput] | None = strawberry.field(default=None, description="Optional list of acquisition views")
    mask_views: list[PartialMaskViewInput] | None = strawberry.field(default=None, description="Optional list of mask views")
    reference_views: list[PartialReferenceViewInput] | None = strawberry.field(default=None, description="Optional list of reference views")
    instance_mask_views: list[PartialInstanceMaskViewInput] | None = strawberry.field(default=None, description="Optional list of instance mask views")
    rgb_views: list[PartialRGBViewInput] | None = strawberry.field(default=None, description="Optional list of RGB views")
    timepoint_views: list[PartialTimepointViewInput] | None = strawberry.field(default=None, description="Optional list of timepoint views")
    optics_views: list[PartialOpticsViewInput] | None = strawberry.field(default=None, description="Optional list of optics views")
    scale_views: list[PartialScaleViewInput] | None = strawberry.field(default=None, description="Optional list of scale views")
    tags: list[str] | None = strawberry.field(default=None, description="Optional list of tags to associate with the image")
    roi_views: list[PartialROIViewInput] | None = strawberry.field(default=None, description="Optional list of ROI views")
    file_views: list[PartialFileViewInput] | None = strawberry.field(default=None, description="Optional list of file views")
    derived_views: list[PartialDerivedViewInput] | None = strawberry.field(default=None, description="Optional list of derived views")
    lightpath_views: list[PartialLightpathViewInput] | None = strawberry.field(default=None, description="Optional list of lightpath views")


def from_array_like(
    info: Info,
    input: FromArrayLikeInput,
) -> types.Image:
    datalayer = get_current_datalayer()

    store = get_for_org(models.ZarrStore, info, id=input.array)
    store.fill_info(datalayer)

    dataset = input.dataset or get_image_dataset(info)

    image = models.Image.objects.create(
        dataset_id=dataset,
        creator=info.context.request.user,
        name=input.name,
        store=store,
        organization=info.context.request.organization,
    )

    if input.tags:
        image.tags.add(*input.tags)

    derived_image = None

    if input.derived_views is not None:
        for derived in input.derived_views:
            derived_image = get_for_org(models.Image, info, id=derived.origin_image)

            models.DerivedView.objects.create(
                image=image,
                origin_image=derived_image,
                **view_kwargs_from_input(derived),
            )

    if input.channel_views is not None:
        for channelview in input.channel_views:
            models.ChannelView.objects.create(
                image=image,
                acquisition_mode=channelview.acquisition_mode,
                excitation_wavelength=channelview.excitation_wavelength,
                emission_wavelength=channelview.emission_wavelength,
                name=channelview.name,
                **view_kwargs_from_input(channelview),
            )

    if input.lightpath_views is not None:
        for lightpath_view in input.lightpath_views:
            models.LightpathView.objects.create(
                image=image,
                graph=strawberry.asdict(lightpath_view.graph),  # Assuming lightpath is a JSON string or similar
                **view_kwargs_from_input(lightpath_view),
            )

    if input.roi_views is not None:
        for roi_view in input.roi_views:
            models.ROIView.objects.create(
                image=image,
                roi=get_for_org(models.ROI, info, id=roi_view.roi),
                **view_kwargs_from_input(roi_view),
            )

    if input.file_views is not None:
        for fileview in input.file_views:
            models.FileView.objects.create(
                image=image,
                file=get_for_org(models.File, info, id=fileview.file),
                series_identifier=fileview.series_identifier,
                **view_kwargs_from_input(fileview),
            )

    if input.timepoint_views is not None:
        for i, timepoint_view in enumerate(input.timepoint_views):
            models.TimepointView.objects.create(
                image=image,
                era=(get_for_org(models.Era, info, id=timepoint_view.era) if timepoint_view.era else models.Era.objects.create(name=f"Unknown for {image.name} and {i}", organization=info.context.request.organization)),
                **view_kwargs_from_input(timepoint_view),
            )

    if input.reference_views is not None:
        for view in input.reference_views:
            models.ReferenceView.objects.create(
                image=image,
                **view_kwargs_from_input(view),
            )

    if input.mask_views is not None:
        for maskview in input.mask_views:
            _create_mask_view_from_partial(image, maskview)

    if input.instance_mask_views is not None:
        for instance_mask_view in input.instance_mask_views:
            _create_instance_mask_view_from_partial(image, instance_mask_view, info)

    if input.scale_views is not None:
        for scaleview in input.scale_views:
            models.ScaleView.objects.create(
                image=image,
                parent_id=scaleview.parent,
                scale_x=scaleview.scale_x or 1,
                scale_y=scaleview.scale_y or 1,
                scale_z=scaleview.scale_z or 1,
                scale_c=scaleview.scale_c or 1,
                scale_t=scaleview.scale_t or 1,
                **view_kwargs_from_input(scaleview),
            )

    if input.rgb_views is not None:
        default_context = None

        for rgb_view in input.rgb_views:
            if rgb_view.context is None and default_context is None:
                default_context = models.RGBRenderContext.objects.create(
                    name="Default",
                    image=image,
                )

            x, _ = models.RGBView.objects.update_or_create(
                image=image,
                c_max=rgb_view.c_max,
                c_min=rgb_view.c_min,
                gamma=rgb_view.gamma,
                contrast_limit_min=rgb_view.contrast_limit_min,
                contrast_limit_max=rgb_view.contrast_limit_max,
                active=rgb_view.active if rgb_view.active is not None else True,
                color_map=(rgb_view.color_map if rgb_view.color_map is not None else "gray"),
                base_color=rgb_view.base_color if rgb_view.base_color else None,
            )

            context = get_for_org(models.RGBRenderContext, info, id=rgb_view.context) if rgb_view.context else default_context
            context.views.add(x)

    else:
        if derived_image is not None:
            # If there are derived views but no RGB view, we create a default RGB view to ensure the derived image is visible in the UI
            if derived_image.store:
                default_context = models.RGBRenderContext.objects.create(
                    name="Default",
                    image=image,
                )

                if derived_image.store.c_size == store.c_size:
                    for view in derived_image.rgb_views.all():
                        x, _ = models.RGBView.objects.update_or_create(
                            image=image,
                            c_max=view.c_max,
                            c_min=view.c_min,
                            gamma=view.gamma,
                            contrast_limit_min=view.contrast_limit_min,
                            contrast_limit_max=view.contrast_limit_max,
                            active=view.active,
                            color_map=view.color_map,
                            base_color=view.base_color,
                        )

                        default_context.views.add(x)

        else:
            auto_create_views(image)

    if input.acquisition_views is not None:
        for acquisitionview in input.acquisition_views:
            models.AcquisitionView.objects.create(
                image=image,
                description=acquisitionview.description,
                acquired_at=acquisitionview.acquired_at,
                operator=(get_user_model().objects.get(id=acquisitionview.operator) if acquisitionview.operator else None),
                **view_kwargs_from_input(acquisitionview),
            )

    if input.optics_views is not None:
        for opticsview in input.optics_views:
            models.OpticsView.objects.create(
                image=image,
                instrument_id=opticsview.instrument,
                objective_id=opticsview.objective,
                camera_id=opticsview.camera,
                **view_kwargs_from_input(opticsview),
            )

    if input.transformation_views is not None:
        for i, transformationview in enumerate(input.transformation_views):
            models.AffineTransformationView.objects.create(
                image=image,
                affine_matrix=transformationview.affine_matrix,
                stage=(
                    get_for_org(models.Stage, info, id=transformationview.stage)
                    if transformationview.stage
                    else models.Stage.objects.create(
                        name=f"Unknown for {image.name} and {i}",
                        organization=info.context.request.organization,
                    )
                ),
                **view_kwargs_from_input(transformationview),
            )

    return image


def get_image_dataset(info: Info) -> models.Dataset:
    return models.Dataset.objects.get_current_default(info).id
