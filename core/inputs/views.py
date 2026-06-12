"""GraphQL input types for image views.

These classes define the public schema: their names become the GraphQL input
type names, so they must not be renamed. ``Partial*ViewInput`` variants are
nested inside ``FromArrayLikeInput`` (no image field, the image comes from the
surrounding mutation); the non-partial variants add the ``image`` ID for the
standalone ``create*View`` mutations.
"""

import strawberry
import strawberry_django
from datetime import datetime
from strawberry import ID

from core import enums, models, scalars
from lightpath.inputs.types import LightpathGraphInput


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


@strawberry_django.input(
    models.ChannelView,
    description="Input for creating a channel view (channel metadata such as name and wavelengths) as part of creating an image; the image is taken from the surrounding input",
)
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


@strawberry_django.input(
    models.ChannelView,
    description="Input for creating a channel view on an existing image, referenced by ID",
)
class ChannelViewInput(PartialChannelViewInput):
    """Input for creating a complete channel view including the image"""

    image: strawberry.ID = strawberry.field(description="The ID of the image this view is for")


@strawberry_django.input(
    models.AffineTransformationView,
    description="Input for creating an affine transformation view (mapping the image onto a stage) as part of creating an image; the image is taken from the surrounding input",
)
class PartialAffineTransformationViewInput(ViewInput):
    """Input for an affine transformation view nested in image creation"""

    stage: ID | None = strawberry.field(default=None, description="The ID of the stage this transformation maps the image onto")
    affine_matrix: scalars.FourByFourMatrix = strawberry.field(description="The 4x4 affine matrix mapping image coordinates to stage coordinates")


@strawberry_django.input(
    models.LabelView,
    description="Input for creating a label view (annotating the region with an entity class label) as part of creating an image; the image is taken from the surrounding input",
)
class PartialLabelViewInput(ViewInput):
    """Input for a label view nested in image creation"""

    label: str = strawberry.field(description="The label of the entity class annotated by this view")


@strawberry_django.input(
    models.RGBView,
    description="Input for creating an RGB render view (how a channel is rendered in an RGB context) as part of creating an image; the image is taken from the surrounding input",
)
class PartialRGBViewInput(ViewInput):
    """Input for an RGB render view nested in image creation"""

    context: ID | None = strawberry.field(default=None, description="The ID of the RGB render context this view belongs to")
    gamma: float | None = strawberry.field(default=None, description="The gamma correction applied to the channel")
    contrast_limit_min: float | None = strawberry.field(default=None, description="The minimum contrast limit of the channel")
    contrast_limit_max: float | None = strawberry.field(default=None, description="The maximum contrast limit of the channel")
    rescale: bool | None = strawberry.field(default=None, description="Whether to rescale the channel data to the contrast limits")
    scale: float | None = strawberry.field(default=None, description="The scale factor applied to the channel when rendering")
    active: bool | None = strawberry.field(default=None, description="Whether the view is active")
    color_map: enums.ColorMap | None = strawberry.field(default=None, description="The color map applied to the channel")
    base_color: list[float] | None = strawberry.field(default=None, description="The base color of the channel as RGBA values (if using a mapped scaler)")


@strawberry_django.input(
    models.RGBView,
    description="Input for updating an existing RGB view, referenced by ID",
)
class UpdateRGBViewInput(PartialRGBViewInput):
    """Input for updating an existing RGB view"""

    id: ID = strawberry.field(description="The ID of the RGB view to update")


@strawberry_django.input(
    models.AcquisitionView,
    description="Input for creating an acquisition view (when and by whom the image was acquired) as part of creating an image; the image is taken from the surrounding input",
)
class PartialAcquisitionViewInput(ViewInput):
    """Input for an acquisition view nested in image creation"""

    description: str | None = strawberry.field(default=None, description="A cleartext description of the image acquisition")
    acquired_at: datetime | None = strawberry.field(default=None, description="The time the image was acquired")
    operator: ID | None = strawberry.field(default=None, description="The ID of the user that acquired the image")


@strawberry_django.input(
    models.ROIView,
    description="Input for creating a ROI view (marking the image as a cutout of a parent image's ROI) as part of creating an image; the image is taken from the surrounding input",
)
class PartialROIViewInput(ViewInput):
    """Input for a ROI view nested in image creation"""

    roi: ID = strawberry.field(description="The ID of the ROI of the parent image this view is a cutout of")


@strawberry_django.input(
    models.DerivedView,
    description="Input for creating a derived view (recording the image this image was derived from) as part of creating an image; the image is taken from the surrounding input",
)
class PartialDerivedViewInput(ViewInput):
    """Input for a derived view nested in image creation"""

    origin_image: ID = strawberry.field(description="The ID of the image this image was derived from")


@strawberry_django.input(
    models.LightpathView,
    description="Input for creating a lightpath view (the optical path of the instrument) as part of creating an image; the image is taken from the surrounding input",
)
class PartialLightpathViewInput(ViewInput):
    """Input for a lightpath view nested in image creation"""

    graph: LightpathGraphInput = strawberry.field(description="The lightpath graph of the instrument")


@strawberry_django.input(
    models.FileView,
    description="Input for creating a file view (linking the image region to the originating file) as part of creating an image; the image is taken from the surrounding input",
)
class PartialFileViewInput(ViewInput):
    """Input for a file view nested in image creation"""

    file: ID = strawberry.field(description="The ID of the file this view represents")
    series_identifier: str | None = strawberry.field(default=None, description="The series identifier of the file")


@strawberry_django.input(
    models.HistogramView,
    description="Input for creating a histogram view (pixel value distribution of the region) as part of creating an image; the image is taken from the surrounding input",
)
class PartialHistogramViewInput(ViewInput):
    """Input for a histogram view nested in image creation"""

    histogram: list[float] = strawberry.field(description="The histogram of the image (y values)")
    bins: list[float] = strawberry.field(description="The bin indices of the histogram (x values)")
    min: float = strawberry.field(description="The minimum pixel value of the histogram")
    max: float = strawberry.field(description="The maximum pixel value of the histogram")


@strawberry_django.input(
    models.OpticsView,
    description="Input for creating an optics view (instrument, objective and camera used) as part of creating an image; the image is taken from the surrounding input",
)
class PartialOpticsViewInput(ViewInput):
    """Input for an optics view nested in image creation"""

    instrument: ID | None = strawberry.field(default=None, description="The ID of the instrument used to acquire the image")
    objective: ID | None = strawberry.field(default=None, description="The ID of the objective used to acquire the image")
    camera: ID | None = strawberry.field(default=None, description="The ID of the camera used to acquire the image")


@strawberry_django.input(
    models.ScaleView,
    description="Input for creating a scale view (the scale factors relative to a parent view) as part of creating an image; the image is taken from the surrounding input",
)
class PartialScaleViewInput(ViewInput):
    """Input for a scale view nested in image creation"""

    parent: ID | None = strawberry.field(default=None, description="The ID of the parent view this scale view is derived from")
    scale_x: float | None = strawberry.field(default=None, description="The scale in x direction")
    scale_y: float | None = strawberry.field(default=None, description="The scale in y direction")
    scale_z: float | None = strawberry.field(default=None, description="The scale in z direction")
    scale_t: float | None = strawberry.field(default=None, description="The scale in t direction")
    scale_c: float | None = strawberry.field(default=None, description="The scale in c direction")


@strawberry_django.input(
    models.MaskView,
    description="Input for creating a mask view (a label mask of another image) as part of creating an image; the image is taken from the surrounding input",
)
class PartialMaskViewInput(ViewInput):
    """Input for a mask view nested in image creation"""

    reference_view: ID | None = strawberry.field(default=None, description="The ID of the view that is masked by this mask")
    labels: scalars.LabelsLike | None = strawberry.field(default=None, description="The labels of the mask and their corresponding colors")


@strawberry_django.input(
    models.InstanceMaskView,
    description="Input for creating an instance mask view (an instance mask of another image) as part of creating an image; the image is taken from the surrounding input",
)
class PartialInstanceMaskViewInput(ViewInput):
    """Input for an instance mask view nested in image creation"""

    reference_view: ID | None = strawberry.field(default=None, description="The ID of the view that is masked by this instance mask")
    labels: scalars.LabelsLike | None = strawberry.field(default=None, description="The instance labels of the mask and their corresponding colors")


@strawberry_django.input(
    models.ReferenceView,
    description="Input for creating a reference view (marking the region as a reference for other views) as part of creating an image; the image is taken from the surrounding input",
)
class PartialReferenceViewInput(ViewInput):
    """Input for a reference view nested in image creation"""

    pass


@strawberry_django.input(
    models.WellPositionView,
    description="Input for creating a well position view (the well of a multi-well plate the region was acquired in) as part of creating an image; the image is taken from the surrounding input",
)
class PartialWellPositionViewInput(ViewInput):
    """Input for a well position view nested in image creation"""

    well: ID | None = strawberry.field(default=None, description="The ID of the multi-well plate this view belongs to")
    row: int | None = strawberry.field(default=None, description="The row of the well")
    column: int | None = strawberry.field(default=None, description="The column of the well")


@strawberry_django.input(
    models.ContinousScanView,
    description="Input for creating a continuous scan view (the scan direction of the acquisition) as part of creating an image; the image is taken from the surrounding input",
)
class PartialContinoussScanViewInput(ViewInput):
    """Input for a continuous scan view nested in image creation"""

    direction: enums.ScanDirection = strawberry.field(description="The direction of the scan")


@strawberry_django.input(
    models.TimepointView,
    description="Input for creating a timepoint view (placing the region in time relative to an era) as part of creating an image; the image is taken from the surrounding input",
)
class PartialTimepointViewInput(ViewInput):
    """Input for a timepoint view nested in image creation"""

    era: ID | None = strawberry.field(default=None, description="The ID of the era this timepoint belongs to")
    ms_since_start: scalars.Milliseconds | None = strawberry.field(default=None, description="The time in ms since the start of the era")
    index_since_start: int | None = strawberry.field(default=None, description="The index of the timepoint since the start of the era")


@strawberry_django.input(
    models.AffineTransformationView,
    description="Input for creating an affine transformation view on an existing image, referenced by ID",
)
class AffineTransformationViewInput(PartialAffineTransformationViewInput):
    """Input for creating an affine transformation view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


@strawberry_django.input(
    models.LabelView,
    description="Input for creating a label view on an existing image, referenced by ID",
)
class LabelViewInput(PartialLabelViewInput):
    """Input for creating a label view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


@strawberry_django.input(
    models.AcquisitionView,
    description="Input for creating an acquisition view on an existing image, referenced by ID",
)
class AcquisitionViewInput(PartialAcquisitionViewInput):
    """Input for creating an acquisition view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


@strawberry_django.input(
    models.RGBView,
    description="Input for creating an RGB render view on an existing image, referenced by ID",
)
class RGBViewInput(PartialRGBViewInput):
    """Input for creating an RGB render view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")
    context: ID = strawberry.field(description="The ID of the RGB render context this view belongs to")


@strawberry_django.input(
    models.ContinousScanView,
    description="Input for creating a continuous scan view on an existing image, referenced by ID",
)
class ContinousScanViewInput(PartialContinoussScanViewInput):
    """Input for creating a continuous scan view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


@strawberry_django.input(
    models.DerivedView,
    description="Input for creating a derived view on an existing image, referenced by ID",
)
class DerivedViewInput(PartialDerivedViewInput):
    """Input for creating a derived view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


@strawberry_django.input(
    models.LightpathView,
    description="Input for creating a lightpath view on an existing image, referenced by ID",
)
class LightpathViewInput(PartialLightpathViewInput):
    """Input for creating a lightpath view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


@strawberry_django.input(
    models.HistogramView,
    description="Input for creating a histogram view on an existing image, referenced by ID",
)
class HistogramViewInput(PartialHistogramViewInput):
    """Input for creating a histogram view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


@strawberry_django.input(
    models.WellPositionView,
    description="Input for creating a well position view on an existing image, referenced by ID",
)
class WellPositionViewInput(PartialWellPositionViewInput):
    """Input for creating a well position view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


@strawberry_django.input(
    models.LabelView,
    description="Input for creating a timepoint view on an existing image, referenced by ID",
)
class TimepointViewInput(PartialTimepointViewInput):
    """Input for creating a timepoint view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


@strawberry_django.input(
    models.OpticsView,
    description="Input for creating an optics view on an existing image, referenced by ID",
)
class OpticsViewInput(PartialOpticsViewInput):
    """Input for creating an optics view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


@strawberry_django.input(
    models.ROIView,
    description="Input for creating a ROI view on an existing image, referenced by ID",
)
class ROIViewInput(PartialROIViewInput):
    """Input for creating a ROI view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


@strawberry_django.input(
    models.FileView,
    description="Input for creating a file view on an existing image, referenced by ID",
)
class FileViewInput(PartialFileViewInput):
    """Input for creating a file view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


@strawberry_django.input(
    models.MaskView,
    description="Input for creating a mask view on an existing image, referenced by ID",
)
class MaskViewInput(PartialMaskViewInput):
    """Input for creating a mask view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


@strawberry_django.input(
    models.InstanceMaskView,
    description="Input for creating an instance mask view on an existing image, referenced by ID",
)
class InstanceMaskViewInput(PartialInstanceMaskViewInput):
    """Input for creating an instance mask view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


@strawberry_django.input(
    models.ReferenceView,
    description="Input for creating a reference view on an existing image, referenced by ID",
)
class ReferenceViewInput(PartialReferenceViewInput):
    """Input for creating a reference view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


def view_kwargs_from_input(input: ViewInput) -> dict:
    """The slice-bounds kwargs shared by every view model, with ``is_global`` derived."""
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
