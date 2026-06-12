"""Orchestration for creating an Image with its nested views from an array-like store.

This is the bulk counterpart to the standalone ``create*View`` mutations:
one Image row plus any number of views per kind, all created through the
shared per-kind creators in :mod:`core.logic.views`.

Deliberately not wrapped in a transaction: the ``post_save`` signal on
``Image`` broadcasts subscription events immediately, and subscribers may
query right away — making this atomic needs ``transaction.on_commit`` for
those broadcasts and is a separate change.
"""

from kante.types import Info

from core import models
from core.creation import CreationContext
from core.inputs.image import FromArrayLikeInput
from core.logic import views as view_logic
from core.scoping import get_for_org
from datalayer.datalayer import get_current_datalayer


def get_image_dataset(ctx: CreationContext) -> int:
    """The id of the user's default dataset, created on first use."""
    return models.Dataset.objects.get_current_default(ctx).id


def create_image_from_array(
    info: Info,
    input: FromArrayLikeInput,
    ctx: CreationContext,
) -> models.Image:
    """Create an Image from a filled Zarr store together with all requested views."""
    datalayer = get_current_datalayer()

    store = get_for_org(models.ZarrStore, info, id=input.array)
    store.fill_info(datalayer)

    dataset = input.dataset or get_image_dataset(ctx)

    image = models.Image.objects.create(
        dataset_id=dataset,
        creator=ctx.user,
        name=input.name,
        store=store,
        organization=ctx.organization,
        **ctx.provenance_kwargs(),
    )

    if input.tags:
        image.tags.add(*input.tags)

    derived_image = None

    if input.derived_views is not None:
        for derived in input.derived_views:
            derived_view = view_logic.create_derived_view(image, derived, info)
            derived_image = derived_view.origin_image

    if input.channel_views is not None:
        for channelview in input.channel_views:
            view_logic.create_channel_view(image, channelview)

    if input.lightpath_views is not None:
        for lightpath_view in input.lightpath_views:
            view_logic.create_lightpath_view(image, lightpath_view)

    if input.roi_views is not None:
        for roi_view in input.roi_views:
            view_logic.create_roi_view(image, roi_view, info)

    if input.file_views is not None:
        for fileview in input.file_views:
            view_logic.create_file_view(image, fileview, info)

    if input.timepoint_views is not None:
        for i, timepoint_view in enumerate(input.timepoint_views):
            view_logic.create_timepoint_view(image, timepoint_view, info, ctx, fallback_suffix=f" and {i}")

    if input.reference_views is not None:
        for view in input.reference_views:
            view_logic.create_reference_view(image, view)

    if input.mask_views is not None:
        for maskview in input.mask_views:
            view_logic.create_mask_view(image, maskview)

    if input.instance_mask_views is not None:
        for instance_mask_view in input.instance_mask_views:
            view_logic.create_instance_mask_view(image, instance_mask_view, info)

    if input.scale_views is not None:
        for scaleview in input.scale_views:
            view_logic.create_scale_view(image, scaleview)

    if input.rgb_views is not None:
        default_context = None

        for rgb_view in input.rgb_views:
            if rgb_view.context is None and default_context is None:
                default_context = models.RGBRenderContext.objects.create(
                    name="Default",
                    image=image,
                )

            x = view_logic.get_or_create_rgb_view(image, rgb_view)

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
            view_logic.auto_create_views(image)

    if input.acquisition_views is not None:
        for acquisitionview in input.acquisition_views:
            view_logic.create_acquisition_view(image, acquisitionview)

    if input.optics_views is not None:
        for opticsview in input.optics_views:
            view_logic.create_optics_view(image, opticsview)

    if input.transformation_views is not None:
        for i, transformationview in enumerate(input.transformation_views):
            view_logic.create_affine_transformation_view(image, transformationview, info, ctx, fallback_suffix=f" and {i}")

    return image
