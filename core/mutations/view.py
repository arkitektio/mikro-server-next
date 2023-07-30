from kante.types import Info
import strawberry
from core import types, models, scalars
from strawberry import ID


@strawberry.input
class ViewInput:
    image: ID
    z_min: int | None = None
    z_max: int | None = None
    x_min: int | None = None
    x_max: int | None = None
    y_min: int | None = None
    y_max: int | None = None
    t_min: int | None = None
    t_max: int | None = None
    c_min: int | None = None
    c_max: int | None = None


@strawberry.input
class ChannelViewInput(ViewInput):
    channel: ID


@strawberry.input
class TransformationViewInput(ViewInput):
    stage: ID
    matrix: scalars.Matrix


def view_kwargs_from_input(input: ChannelViewInput) -> dict:
    return dict(
        z_min=input.z_min,
        z_max=input.z_max,
        x_min=input.x_min,
        x_max=input.x_max,
        y_min=input.y_min,
        y_max=input.y_max,
        t_min=input.t_min,
        t_max=input.t_max,
        c_min=input.c_min,
        c_max=input.c_max,
    )


def create_new_view(
    info: Info,
    input: ViewInput,
) -> types.View:
    image = models.Image.objects.get(id=input.image)

    view = models.View.objects.create(
        image=image,
        **view_kwargs_from_input(input),
    )
    return view


def create_channel_view(
    info: Info,
    input: ChannelViewInput,
) -> types.ChannelView:
    image = models.Image.objects.get(id=input.image)

    view = models.ChannelView.objects.create(
        image=image,
        channel=models.Channel.objects.get(id=input.channel),
        **view_kwargs_from_input(input),
    )
    return view


def create_transformation_view(
    info: Info,
    input: TransformationViewInput,
) -> types.TransformationView:
    image = models.Image.objects.get(id=input.image)

    view = models.TransformationView.objects.create(
        image=image,
        channel=models.Stage.objects.get(id=input.stage),
        matrix=input.matrix,
        **view_kwargs_from_input(input),
    )
    return view
