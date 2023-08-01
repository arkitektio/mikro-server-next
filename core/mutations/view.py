from kante.types import Info
import strawberry
from core import types, models, scalars
from strawberry import ID
import strawberry_django


@strawberry_django.input(models.View)
class ViewInput:
    collection: ID | None = None
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


@strawberry_django.input(models.ChannelView)
class PartialChannelViewInput(ViewInput):
    channel: ID
    pass


@strawberry_django.input(models.ChannelView)
class ChannelViewInput(PartialChannelViewInput):
    image: ID
    pass


@strawberry_django.input(models.TransformationView)
class PartialTransformationViewInput(ViewInput):
    stage: ID | None = None
    matrix: scalars.FourByFourMatrix
    kind: strawberry.auto


@strawberry_django.input(models.TransformationView)
class PartialLabelViewInput(ViewInput):
    fluorophore: ID | None = None
    primary_antibody: ID | None = None
    secondary_antibody: ID | None = None


@strawberry_django.input(models.OpticsView)
class PartialOpticsViewInput(ViewInput):
    instrument: ID | None = None
    objective: ID | None = None
    camera: ID | None = None


@strawberry_django.input(models.TimepointView)
class PartialTimepointViewInput(ViewInput):
    era: ID | None = None
    ms_since_start: scalars.Milliseconds | None = None
    index_since_start: int | None = None


@strawberry_django.input(models.TransformationView)
class TransformationViewInput(PartialTransformationViewInput):
    image: ID


@strawberry_django.input(models.LabelView)
class LabelViewInput(PartialLabelViewInput):
    image: ID


@strawberry_django.input(models.LabelView)
class TimepointViewInput(PartialTimepointViewInput):
    image: ID


@strawberry_django.input(models.OpticsView)
class OpticsViewInput(PartialOpticsViewInput):
    image: ID


def view_kwargs_from_input(input: ChannelViewInput) -> dict:
    is_global = all(
        x is None
        for x in [
            input.z_min,
            input.z_max,
            input.x_min,
            input.x_max,
            input.y_min,
            input.y_max,
            input.t_min,
            input.t_max,
            input.c_min,
            input.c_max,
        ]
    )

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
        is_global=is_global,
        collection_id=input.collection,
    )


@strawberry.input()
class DeleteViewInput:
    id: strawberry.ID


def delete_view(
    info: Info,
    input: DeleteViewInput,
) -> strawberry.ID:
    item = models.View.objects.get(id=input.id)
    item.delete()
    return input.id


@strawberry.input
class PinViewInput:
    id: strawberry.ID
    pin: bool


def pin_view(
    info: Info,
    input: PinViewInput,
) -> types.View:
    raise NotImplementedError("TODO")


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
        stage=models.Stage.objects.get(id=input.stage)
        if input.stage
        else models.Stage.objects.create(name=f"Unknown for {image.name}"),
        matrix=input.matrix,
        **view_kwargs_from_input(input),
    )
    return view


def create_label_view(
    info: Info,
    input: LabelViewInput,
) -> types.LabelView:
    image = models.Image.objects.get(id=input.image)

    view = models.LabelView.objects.create(
        image=image,
        fluorophore=models.Fluorophore.objects.get(id=input.fluorophore)
        if input.fluorophore
        else None,
        **view_kwargs_from_input(input),
    )
    return view


def create_timepoint_view(
    info: Info,
    input: TimepointViewInput,
) -> types.TimepointView:
    image = models.Image.objects.get(id=input.image)

    view = models.LabelView.objects.create(
        image=image,
        era=models.Era.objects.get(id=input.fluorophore)
        if input.era
        else models.Era.objects.create(name=f"Unknown for {image.name}"),
        **view_kwargs_from_input(input),
    )
    return view


def create_optics_view(
    info: Info,
    input: OpticsViewInput,
) -> types.OpticsView:
    image = models.Image.objects.get(id=input.image)

    view = models.OpticsView.objects.create(
        image=image,
        objective_id=input.objective,
        instrument_id=input.instrument,
        camera_id=input.camera,
        **view_kwargs_from_input(input),
    )
    return view
