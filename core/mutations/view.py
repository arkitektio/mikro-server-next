from kante.types import Info
import strawberry
from core import types, models, scalars, enums
from strawberry import ID
import strawberry_django
from datetime import datetime
from django.contrib.auth import get_user_model
from lightpath.inputs.types import LightpathGraphInput
from core.scoping import get_for_org
from core.mutations._generic import make_delete
from koherent.utils import get_or_create_task


@strawberry_django.input(
    models.View,
    description="""                       
A input type to generate a view of a slice of an image.                      
""",
)
class ViewInput:
    """A general view of a region of an image"""

    collection: strawberry.ID | None = strawberry.field(default=None, description="The collection this view belongs to")
    z_min: int | None = strawberry.field(default=None, description="The minimum z coordinate of the view")
    z_max: int | None = strawberry.field(default=None, description="The maximum z coordinate of the view")
    x_min: int | None = strawberry.field(default=None, description="The minimum x coordinate of the view")
    x_max: int | None = strawberry.field(default=None, description="The maximum x coordinate of the view")
    y_min: int | None = strawberry.field(default=None, description="The minimum y coordinate of the view")
    y_max: int | None = strawberry.field(default=None, description="The maximum y coordinate of the view")
    t_min: int | None = strawberry.field(default=None, description="The minimum t coordinate of the view")
    t_max: int | None = strawberry.field(default=None, description="The maximum t coordinate of the view")
    c_min: int | None = strawberry.field(default=None, description="The minimum c (channel) coordinate of the view")
    c_max: int | None = strawberry.field(default=None, description="The maximum c (channel) coordinate of the view")


@strawberry_django.input(models.ChannelView)
class PartialChannelViewInput(ViewInput):
    """Input for creating a view of a specific channel"""

    emission_wavelength: float | None = strawberry.field(
        default=None,
        description="The emission wavelength of the channel in nanometers",
    )
    excitation_wavelength: float | None = strawberry.field(
        default=None,
        description="The excitation wavelength of the channel in nanometers",
    )
    acquisition_mode: str | None = strawberry.field(
        default=None,
        description="The acquisition mode of the channel",
    )
    name: str | None = strawberry.field(
        default=None,
        description="The name of the channel",
    )


@strawberry_django.input(models.ChannelView)
class ChannelViewInput(PartialChannelViewInput):
    """Input for creating a complete channel view including the image"""

    image: strawberry.ID = strawberry.field(description="The ID of the image this view is for")


@strawberry_django.input(models.AffineTransformationView)
class PartialAffineTransformationViewInput(ViewInput):
    stage: ID | None = None
    affine_matrix: scalars.FourByFourMatrix


@strawberry_django.input(models.LabelView)
class PartialLabelViewInput(ViewInput):
    label: str


@strawberry_django.input(models.RGBView)
class PartialRGBViewInput(ViewInput):
    context: ID | None = None
    gamma: float | None = None
    contrast_limit_min: float | None = None
    contrast_limit_max: float | None = None
    rescale: bool | None = None
    scale: float | None = None
    active: bool | None = None
    color_map: enums.ColorMap | None = None
    base_color: list[float] | None = None


@strawberry_django.input(models.RGBView)
class UpdateRGBViewInput(PartialRGBViewInput):
    id: ID = strawberry.field(description="The ID of the RGB view to update")


@strawberry_django.input(models.AcquisitionView)
class PartialAcquisitionViewInput(ViewInput):
    description: str | None = None
    acquired_at: datetime | None = None
    operator: ID | None = None


@strawberry_django.input(models.ROIView)
class PartialROIViewInput(ViewInput):
    roi: ID


@strawberry_django.input(models.DerivedView)
class PartialDerivedViewInput(ViewInput):
    origin_image: ID


@strawberry_django.input(models.LightpathView)
class PartialLightpathViewInput(ViewInput):
    graph: LightpathGraphInput  # JSON string representing the lightpath


@strawberry_django.input(models.FileView)
class PartialFileViewInput(ViewInput):
    file: ID
    series_identifier: str | None = None


@strawberry_django.input(models.HistogramView)
class PartialHistogramViewInput(ViewInput):
    histogram: list[float]
    bins: list[float]
    min: float
    max: float


@strawberry_django.input(models.OpticsView)
class PartialOpticsViewInput(ViewInput):
    instrument: ID | None = None
    objective: ID | None = None
    camera: ID | None = None


@strawberry_django.input(models.ScaleView)
class PartialScaleViewInput(ViewInput):
    parent: ID | None = None
    scale_x: float | None = None
    scale_y: float | None = None
    scale_z: float | None = None
    scale_t: float | None = None
    scale_c: float | None = None


@strawberry_django.input(models.MaskView)
class PartialMaskViewInput(ViewInput):
    reference_view: ID | None = None
    labels: scalars.LabelsLike | None = None


@strawberry_django.input(models.InstanceMaskView)
class PartialInstanceMaskViewInput(ViewInput):
    reference_view: ID | None = None
    labels: scalars.LabelsLike | None = None


@strawberry_django.input(models.ReferenceView)
class PartialReferenceViewInput(ViewInput):
    pass


@strawberry_django.input(models.WellPositionView)
class PartialWellPositionViewInput(ViewInput):
    well: ID | None = None
    row: int | None = None
    column: int | None = None


@strawberry_django.input(models.ContinousScanView)
class PartialContinoussScanViewInput(ViewInput):
    direction: enums.ScanDirection


@strawberry_django.input(models.TimepointView)
class PartialTimepointViewInput(ViewInput):
    era: ID | None = None
    ms_since_start: scalars.Milliseconds | None = None
    index_since_start: int | None = None


@strawberry_django.input(models.AffineTransformationView)
class AffineTransformationViewInput(PartialAffineTransformationViewInput):
    image: ID


@strawberry_django.input(models.LabelView)
class LabelViewInput(PartialLabelViewInput):
    image: ID


@strawberry_django.input(models.AcquisitionView)
class AcquisitionViewInput(PartialAcquisitionViewInput):
    image: ID


@strawberry_django.input(models.RGBView)
class RGBViewInput(PartialRGBViewInput):
    image: ID
    context: ID


@strawberry_django.input(models.ContinousScanView)
class ContinousScanViewInput(PartialContinoussScanViewInput):
    image: ID


@strawberry_django.input(models.DerivedView)
class DerivedViewInput(PartialDerivedViewInput):
    image: ID


@strawberry_django.input(models.LightpathView)
class LightpathViewInput(PartialLightpathViewInput):
    image: ID


@strawberry_django.input(models.HistogramView)
class HistogramViewInput(PartialHistogramViewInput):
    image: ID


@strawberry_django.input(models.WellPositionView)
class WellPositionViewInput(PartialWellPositionViewInput):
    image: ID


@strawberry_django.input(models.LabelView)
class TimepointViewInput(PartialTimepointViewInput):
    image: ID


@strawberry_django.input(models.OpticsView)
class OpticsViewInput(PartialOpticsViewInput):
    image: ID


@strawberry_django.input(models.ROIView)
class ROIViewInput(PartialROIViewInput):
    image: ID


@strawberry_django.input(models.FileView)
class FileViewInput(PartialFileViewInput):
    image: ID


@strawberry_django.input(models.MaskView)
class MaskViewInput(PartialMaskViewInput):
    image: ID


@strawberry_django.input(models.InstanceMaskView)
class InstanceMaskViewInput(PartialInstanceMaskViewInput):
    image: ID


@strawberry_django.input(models.ReferenceView)
class ReferenceViewInput(PartialReferenceViewInput):
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
    item = get_for_org(models.View, info, id=input.id)
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
    image = get_for_org(models.Image, info, id=input.image)

    view = models.View.objects.create(
        image=image,
        **view_kwargs_from_input(input),
    )
    return view


def create_channel_view(
    info: Info,
    input: ChannelViewInput,
) -> types.ChannelView:
    image = get_for_org(models.Image, info, id=input.image)

    view = models.ChannelView.objects.create(
        image=image,
        channel=get_for_org(models.Channel, info, id=input.channel),
        **view_kwargs_from_input(input),
    )
    return view


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

    view = models.RGBView.objects.create(
        image=image,
        context=(get_for_org(models.RGBRenderContext, info, id=input.context) if input.context else models.RGBRenderContext.objects.create(name=f"Unknown for {image.name}", image=image)),
        r_scale=input.r_scale,
        g_scale=input.g_scale,
        b_scale=input.b_scale,
        **view_kwargs_from_input(input),
    )
    return view


delete_rgb_view = make_delete(models.RGBView, DeleteViewInput)


def create_affine_transformation_view(
    info: Info,
    input: AffineTransformationViewInput,
) -> types.AffineTransformationView:
    image = get_for_org(models.Image, info, id=input.image)

    task = get_or_create_task()
    view = models.AffineTransformationView.objects.create(
        image=image,
        stage=(get_for_org(models.Stage, info, id=input.stage) if input.stage else models.Stage.objects.create(name=f"Unknown for {image.name}", organization=info.context.request.organization, created_through=task, created_through_by_id=task.assigner_id if task else None)),
        affine_matrix=input.affine_matrix,
        **view_kwargs_from_input(input),
    )
    return view


delete_affine_transformation_view = make_delete(models.AffineTransformationView, DeleteViewInput)


def create_label_view(
    info: Info,
    input: LabelViewInput,
) -> types.LabelView:
    image = get_for_org(models.Image, info, id=input.image)

    view = models.LabelView.objects.create(
        image=image,
        label=input.label,
        **view_kwargs_from_input(input),
    )
    return view


def create_derived_view(
    info: Info,
    input: DerivedViewInput,
) -> types.DerivedView:
    image = get_for_org(models.Image, info, id=input.image)

    view = models.DerivedView.objects.create(
        image=image,
        origin_image=input.origin_image,
        **view_kwargs_from_input(input),
    )
    return view


def create_roi_view(
    info: Info,
    input: ROIViewInput,
) -> types.ROIView:
    image = get_for_org(models.Image, info, id=input.image)

    view = models.ROIView.objects.create(
        image=image,
        roi=get_for_org(models.ROI, info, id=input.roi),
        **view_kwargs_from_input(input),
    )
    return view


def create_file_view(
    info: Info,
    input: FileViewInput,
) -> types.FileView:
    image = get_for_org(models.Image, info, id=input.image)

    view = models.FileView.objects.create(
        image=image,
        file=get_for_org(models.File, info, id=input.file),
        series_identifier=input.series_identifier,
        **view_kwargs_from_input(input),
    )
    return view


def create_acquisition_view(
    info: Info,
    input: AcquisitionViewInput,
) -> types.AcquisitionView:
    image = get_for_org(models.Image, info, id=input.image)

    view = models.AcquisitionView.objects.create(
        image=image,
        description=input.description,
        acquired_at=input.acquired_at,
        operator=(get_user_model().objects.get(id=input.operator) if input.operator else None),
        **view_kwargs_from_input(input),
    )
    return view


def create_histogram_view(
    info: Info,
    input: HistogramViewInput,
) -> types.HistogramView:
    image = get_for_org(models.Image, info, id=input.image)

    view = models.HistogramView.objects.create(
        image=image,
        histogram=input.histogram,
        bins=input.bins,
        min=input.min,
        max=input.max,
        **view_kwargs_from_input(input),
    )
    return view


delete_histogram_view = make_delete(models.HistogramView, DeleteViewInput)


def create_continous_scan_view(
    info: Info,
    input: ContinousScanViewInput,
) -> types.ContinousScanView:
    image = get_for_org(models.Image, info, id=input.image)

    view = models.ContinousScanView.objects.create(
        image=image,
        direction=input.direction,
        **view_kwargs_from_input(input),
    )
    return view


def create_lightpath_view(
    info: Info,
    input: LightpathViewInput,
) -> types.LightpathView:
    image = get_for_org(models.Image, info, id=input.image)

    view = models.LightpathView.objects.create(
        image=image,
        graph=strawberry.asdict(input.graph),
        **view_kwargs_from_input(input),
    )
    return view


def create_well_position_view(
    info: Info,
    input: WellPositionViewInput,
) -> types.WellPositionView:
    image = get_for_org(models.Image, info, id=input.image)

    well = get_for_org(models.MultiWellPlate, info, id=input.well) if input.well else None

    view = models.WellPositionView.objects.create(
        image=image,
        well=well,
        row=input.row,
        column=input.column,
        **view_kwargs_from_input(input),
    )
    return view


delete_label_view = make_delete(models.LabelView, DeleteViewInput)


def create_timepoint_view(
    info: Info,
    input: TimepointViewInput,
) -> types.TimepointView:
    image = get_for_org(models.Image, info, id=input.image)

    task = get_or_create_task()
    view = models.TimepointView.objects.create(
        image=image,
        era=(get_for_org(models.Era, info, id=input.fluorophore) if input.era else models.Era.objects.create(name=f"Unknown for {image.name}", organization=info.context.request.organization, created_through=task, created_through_by_id=task.assigner_id if task else None)),
        **view_kwargs_from_input(input),
    )
    return view


delete_timepoint_view = make_delete(models.TimepointView, DeleteViewInput)


def create_optics_view(
    info: Info,
    input: OpticsViewInput,
) -> types.OpticsView:
    image = get_for_org(models.Image, info, id=input.image)

    view = models.OpticsView.objects.create(
        image=image,
        objective_id=input.objective,
        instrument_id=input.instrument,
        camera_id=input.camera,
        **view_kwargs_from_input(input),
    )
    return view


delete_optics_view = make_delete(models.OpticsView, DeleteViewInput)


def _create_mask_view_from_partial(image, input: PartialMaskViewInput) -> types.MaskView:
    view = models.MaskView.objects.create(
        image=image,
        reference_view_id=input.reference_view,
        **view_kwargs_from_input(input),
    )

    return view


def _create_instance_mask_view_from_partial(image, input: PartialInstanceMaskViewInput, info: Info) -> types.InstanceMaskView:
    labels = None
    if input.labels is not None:
        labels_store = get_for_org(models.ParquetStore, info, id=input.labels)
        labels_store.fill_info()
        labels = labels_store

    view = models.InstanceMaskView.objects.create(
        image=image,
        reference_view_id=input.reference_view,
        labels=labels,
        **view_kwargs_from_input(input),
    )

    return view


def create_mask_view(
    info: Info,
    input: MaskViewInput,
) -> types.MaskView:
    image = get_for_org(models.Image, info, id=input.image)
    return _create_mask_view_from_partial(image, input)


def create_instance_mask_view(
    info: Info,
    input: InstanceMaskViewInput,
) -> types.InstanceMaskView:
    image = get_for_org(models.Image, info, id=input.image)
    return _create_instance_mask_view_from_partial(image, input, info)


def create_reference_view(
    info: Info,
    input: ReferenceViewInput,
) -> types.ReferenceView:
    image = get_for_org(models.Image, info, id=input.image)

    view = models.ReferenceView.objects.create(
        image=image,
        **view_kwargs_from_input(input),
    )
    return view
