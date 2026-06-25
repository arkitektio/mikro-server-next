from kante.types import Info
import strawberry
from core import types, models
from core.inputs.views import PartialRGBViewInput
from core.creation import CreationContext
from core.scoping import get_for_org
from core.mutations._generic import make_delete


@strawberry.input(description="Input for creating an RGB render context for an image")
class CreateRGBContextInput:
    """Input for creating an RGB render context for an image"""

    name: str | None = strawberry.field(default=None, description="The name of the RGB context")
    thumbnail: strawberry.ID | None = strawberry.field(default=None, description="The ID of an uploaded media store to use as the thumbnail snapshot")
    image: strawberry.ID = strawberry.field(description="The ID of the image this RGB context renders")
    views: list[PartialRGBViewInput] | None = strawberry.field(default=None, description="The RGB views (channel rendering settings) to attach to the context")
    z: int | None = strawberry.field(default=None, description="The z plane the context renders")
    t: int | None = strawberry.field(default=None, description="The timepoint the context renders")
    c: int | None = strawberry.field(default=None, description="The channel the context renders")


@strawberry.input(description="Input for updating an existing RGB render context")
class UpdateRGBContextInput:
    """Input for updating an existing RGB render context"""

    id: strawberry.ID = strawberry.field(description="The ID of the RGB context to update")
    name: str | None = strawberry.field(default=None, description="The new name of the RGB context")
    thumbnail: strawberry.ID | None = strawberry.field(default=None, description="The ID of an uploaded media store to use as the thumbnail snapshot")
    views: list[PartialRGBViewInput] | None = strawberry.field(default=None, description="The RGB views (channel rendering settings) to replace the context's views with")
    z: int | None = strawberry.field(default=None, description="The z plane the context renders")
    t: int | None = strawberry.field(default=None, description="The timepoint the context renders")
    c: int | None = strawberry.field(default=None, description="The channel the context renders")


@strawberry.input(description="Input for deleting an RGB context by ID")
class DeleteRGBContextInput:
    """Input for deleting an RGB context by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the RGB context to delete")


delete_rgb_context = make_delete(models.RGBRenderContext, DeleteRGBContextInput)


def create_rgb_context(
    info: Info,
    input: CreateRGBContextInput,
) -> types.RGBContext:
    context = models.RGBRenderContext.objects.create(
        name=input.name,
        image=get_for_org(models.Image, info, id=input.image),
    )

    if input.thumbnail:
        media_store = get_for_org(models.MediaStore, info, id=input.thumbnail)

        ctx = CreationContext.from_info(info)
        models.Snapshot.objects.create(
            name="RGB SNapshort",
            store=media_store,
            image_id=input.image,
            context=context,
            **ctx.provenance_kwargs(),
        )

    for view_input in input.views:

        x, _ = models.RGBView.objects.get_or_create(
            image_id=input.image,
            c_max=view_input.c_max,
            c_min=view_input.c_min,
            gamma=view_input.gamma,
            contrast_limit_min=view_input.contrast_limit_min,
            contrast_limit_max=view_input.contrast_limit_max,
            rescale=view_input.rescale,
            active=view_input.active,
            color_map=view_input.color_map,
            base_color=view_input.base_color,
        )

        context.views.add(x)

    context.save()

    return context


def update_rgb_context(
    info: Info,
    input: UpdateRGBContextInput,
) -> types.RGBContext:
    context = get_for_org(models.RGBRenderContext, info,
        id=input.id,
    )
    if input.name:
        context.name = input.name

    if input.thumbnail:
        media_store = get_for_org(models.MediaStore, info, id=input.thumbnail)

        ctx = CreationContext.from_info(info)
        models.Snapshot.objects.create(
            name="RGB SNapshort",
            store=media_store,
            image_id=context.image.id,
            context=context,
            **ctx.provenance_kwargs(),
        )

    old_context_ids = set(context.views.values_list("id", flat=True))

    context.views.clear()

    for view_input in input.views:

        x, _ = models.RGBView.objects.get_or_create(
            image_id=context.image.id,
            c_max=view_input.c_max,
            c_min=view_input.c_min,
            gamma=view_input.gamma,
            contrast_limit_min=view_input.contrast_limit_min,
            contrast_limit_max=view_input.contrast_limit_max,
            rescale=view_input.rescale,
            active=view_input.active,
            color_map=view_input.color_map,
        )

        new_context_ids = set(context.views.values_list("id", flat=True))
        context.views.add(x)

    for view_id in old_context_ids:
        if view_id not in new_context_ids:
            get_for_org(models.RGBView, info, id=view_id).delete()

    context.save()

    return context
