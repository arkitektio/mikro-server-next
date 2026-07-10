"""GraphQL input types for image views.

These classes define the public schema: their names become the GraphQL input
type names, so they must not be renamed. ``Partial*ViewInput`` variants are
nested inside ``FromArrayLikeInput`` (no image field, the image comes from the
surrounding mutation); the non-partial variants add the ``image`` ID for the
standalone ``create*View`` mutations.
"""

import kante
import strawberry
from datetime import datetime
from strawberry import ID
from pydantic import BaseModel, Field

from core import enums, scalars
from kanne_server import scalars as kanne_scalars
from kanne_server import quantities
from lightpath.inputs.types import LightpathGraphInput
from lightpath.inputs.models import LightpathGraphInputModel


class ViewInputModel(BaseModel):
    collection: str | None = Field(default=None, description="The collection this view belongs to")
    z_min: int | None = Field(default=None, description="The minimum z coordinate of the view")
    z_max: int | None = Field(default=None, description="The maximum z coordinate of the view")
    x_min: int | None = Field(default=None, description="The minimum x coordinate of the view")
    x_max: int | None = Field(default=None, description="The maximum x coordinate of the view")
    y_min: int | None = Field(default=None, description="The minimum y coordinate of the view")
    y_max: int | None = Field(default=None, description="The maximum y coordinate of the view")
    t_min: int | None = Field(default=None, description="The minimum t coordinate of the view")
    t_max: int | None = Field(default=None, description="The maximum t coordinate of the view")
    c_min: int | None = Field(default=None, description="The minimum c (channel) coordinate of the view")
    c_max: int | None = Field(default=None, description="The maximum c (channel) coordinate of the view")


@kante.pydantic_input(
    ViewInputModel,
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


class PartialChannelViewInputModel(ViewInputModel):
    emission_wavelength: quantities.Length | None = Field(
        default=None,
        description="The emission wavelength of the channel (e.g. '509 nm')",
    )
    excitation_wavelength: quantities.Length | None = Field(
        default=None,
        description="The excitation wavelength of the channel (e.g. '488 nm')",
    )
    acquisition_mode: str | None = Field(
        default=None,
        description="The acquisition mode of the channel",
    )
    name: str | None = Field(
        default=None,
        description="The name of the channel",
    )


@kante.pydantic_input(
    PartialChannelViewInputModel,
    description="Input for creating a channel view (channel metadata such as name and wavelengths) as part of creating an image; the image is taken from the surrounding input",
)
class PartialChannelViewInput(ViewInput):
    """Input for creating a view of a specific channel"""

    emission_wavelength: kanne_scalars.Length | None = strawberry.field(
        default=None,
        description="The emission wavelength of the channel (e.g. '509 nm')",
    )
    excitation_wavelength: kanne_scalars.Length | None = strawberry.field(
        default=None,
        description="The excitation wavelength of the channel (e.g. '488 nm')",
    )
    acquisition_mode: str | None = strawberry.field(
        default=None,
        description="The acquisition mode of the channel",
    )
    name: str | None = strawberry.field(
        default=None,
        description="The name of the channel",
    )


class ChannelViewInputModel(PartialChannelViewInputModel):
    image: str = Field(description="The ID of the image this view is for")


@kante.pydantic_input(
    ChannelViewInputModel,
    description="Input for creating a channel view on an existing image, referenced by ID",
)
class ChannelViewInput(PartialChannelViewInput):
    """Input for creating a complete channel view including the image"""

    image: strawberry.ID = strawberry.field(description="The ID of the image this view is for")


class PartialAffineTransformationViewInputModel(ViewInputModel):
    stage: str | None = Field(default=None, description="The ID of the stage this transformation maps the image onto")
    affine_matrix: list[list[float]] = Field(description="The 4x4 affine matrix mapping image coordinates to stage coordinates")


@kante.pydantic_input(
    PartialAffineTransformationViewInputModel,
    description="Input for creating an affine transformation view (mapping the image onto a stage) as part of creating an image; the image is taken from the surrounding input",
)
class PartialAffineTransformationViewInput(ViewInput):
    """Input for an affine transformation view nested in image creation"""

    stage: ID | None = strawberry.field(default=None, description="The ID of the stage this transformation maps the image onto")
    affine_matrix: scalars.FourByFourMatrix = strawberry.field(description="The 4x4 affine matrix mapping image coordinates to stage coordinates")


class PartialLabelViewInputModel(ViewInputModel):
    label: str = Field(description="The label of the entity class annotated by this view")


@kante.pydantic_input(
    PartialLabelViewInputModel,
    description="Input for creating a label view (annotating the region with an entity class label) as part of creating an image; the image is taken from the surrounding input",
)
class PartialLabelViewInput(ViewInput):
    """Input for a label view nested in image creation"""

    label: str = strawberry.field(description="The label of the entity class annotated by this view")


class PartialRGBViewInputModel(ViewInputModel):
    context: str | None = Field(default=None, description="The ID of the RGB render context this view belongs to")
    gamma: float | None = Field(default=None, description="The gamma correction applied to the channel")
    contrast_limit_min: float | None = Field(default=None, description="The minimum contrast limit of the channel")
    contrast_limit_max: float | None = Field(default=None, description="The maximum contrast limit of the channel")
    rescale: bool | None = Field(default=None, description="Whether to rescale the channel data to the contrast limits")
    scale: float | None = Field(default=None, description="The scale factor applied to the channel when rendering")
    active: bool | None = Field(default=None, description="Whether the view is active")
    color_map: enums.ColorMap | None = Field(default=None, description="The color map applied to the channel")
    base_color: list[float] | None = Field(default=None, description="The base color of the channel as RGBA values (if using a mapped scaler)")


@kante.pydantic_input(
    PartialRGBViewInputModel,
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


class UpdateRGBViewInputModel(PartialRGBViewInputModel):
    id: str = Field(description="The ID of the RGB view to update")


@kante.pydantic_input(
    UpdateRGBViewInputModel,
    description="Input for updating an existing RGB view, referenced by ID",
)
class UpdateRGBViewInput(PartialRGBViewInput):
    """Input for updating an existing RGB view"""

    id: ID = strawberry.field(description="The ID of the RGB view to update")


class PartialAcquisitionViewInputModel(ViewInputModel):
    description: str | None = Field(default=None, description="A cleartext description of the image acquisition")
    acquired_at: datetime | None = Field(default=None, description="The time the image was acquired")
    operator: str | None = Field(default=None, description="The ID of the user that acquired the image")


@kante.pydantic_input(
    PartialAcquisitionViewInputModel,
    description="Input for creating an acquisition view (when and by whom the image was acquired) as part of creating an image; the image is taken from the surrounding input",
)
class PartialAcquisitionViewInput(ViewInput):
    """Input for an acquisition view nested in image creation"""

    description: str | None = strawberry.field(default=None, description="A cleartext description of the image acquisition")
    acquired_at: datetime | None = strawberry.field(default=None, description="The time the image was acquired")
    operator: ID | None = strawberry.field(default=None, description="The ID of the user that acquired the image")


class PartialROIViewInputModel(ViewInputModel):
    roi: str = Field(description="The ID of the ROI of the parent image this view is a cutout of")


@kante.pydantic_input(
    PartialROIViewInputModel,
    description="Input for creating a ROI view (marking the image as a cutout of a parent image's ROI) as part of creating an image; the image is taken from the surrounding input",
)
class PartialROIViewInput(ViewInput):
    """Input for a ROI view nested in image creation"""

    roi: ID = strawberry.field(description="The ID of the ROI of the parent image this view is a cutout of")


class PartialDerivedViewInputModel(ViewInputModel):
    origin_image: str = Field(description="The ID of the image this image was derived from")


@kante.pydantic_input(
    PartialDerivedViewInputModel,
    description="Input for creating a derived view (recording the image this image was derived from) as part of creating an image; the image is taken from the surrounding input",
)
class PartialDerivedViewInput(ViewInput):
    """Input for a derived view nested in image creation"""

    origin_image: ID = strawberry.field(description="The ID of the image this image was derived from")


class PartialLightpathViewInputModel(ViewInputModel):
    graph: LightpathGraphInputModel = Field(description="The lightpath graph of the instrument")


@kante.pydantic_input(
    PartialLightpathViewInputModel,
    description="Input for creating a lightpath view (the optical path of the instrument) as part of creating an image; the image is taken from the surrounding input",
)
class PartialLightpathViewInput(ViewInput):
    """Input for a lightpath view nested in image creation"""

    graph: LightpathGraphInput = strawberry.field(description="The lightpath graph of the instrument")


class PartialFileViewInputModel(ViewInputModel):
    file: str = Field(description="The ID of the file this view represents")
    series_identifier: str | None = Field(default=None, description="The series identifier of the file")


@kante.pydantic_input(
    PartialFileViewInputModel,
    description="Input for creating a file view (linking the image region to the originating file) as part of creating an image; the image is taken from the surrounding input",
)
class PartialFileViewInput(ViewInput):
    """Input for a file view nested in image creation"""

    file: ID = strawberry.field(description="The ID of the file this view represents")
    series_identifier: str | None = strawberry.field(default=None, description="The series identifier of the file")


class PartialHistogramViewInputModel(ViewInputModel):
    histogram: list[float] = Field(description="The histogram of the image (y values)")
    bins: list[float] = Field(description="The bin indices of the histogram (x values)")
    min: float = Field(description="The minimum pixel value of the histogram")
    max: float = Field(description="The maximum pixel value of the histogram")


@kante.pydantic_input(
    PartialHistogramViewInputModel,
    description="Input for creating a histogram view (pixel value distribution of the region) as part of creating an image; the image is taken from the surrounding input",
)
class PartialHistogramViewInput(ViewInput):
    """Input for a histogram view nested in image creation"""

    histogram: list[float] = strawberry.field(description="The histogram of the image (y values)")
    bins: list[float] = strawberry.field(description="The bin indices of the histogram (x values)")
    min: float = strawberry.field(description="The minimum pixel value of the histogram")
    max: float = strawberry.field(description="The maximum pixel value of the histogram")


class PartialOpticsViewInputModel(ViewInputModel):
    instrument: str | None = Field(default=None, description="The ID of the instrument used to acquire the image")
    objective: str | None = Field(default=None, description="The ID of the objective used to acquire the image")
    camera: str | None = Field(default=None, description="The ID of the camera used to acquire the image")


@kante.pydantic_input(
    PartialOpticsViewInputModel,
    description="Input for creating an optics view (instrument, objective and camera used) as part of creating an image; the image is taken from the surrounding input",
)
class PartialOpticsViewInput(ViewInput):
    """Input for an optics view nested in image creation"""

    instrument: ID | None = strawberry.field(default=None, description="The ID of the instrument used to acquire the image")
    objective: ID | None = strawberry.field(default=None, description="The ID of the objective used to acquire the image")
    camera: ID | None = strawberry.field(default=None, description="The ID of the camera used to acquire the image")


class PartialScaleViewInputModel(ViewInputModel):
    parent: str | None = Field(default=None, description="The ID of the parent view this scale view is derived from")
    scale_x: float | None = Field(default=None, description="The scale in x direction")
    scale_y: float | None = Field(default=None, description="The scale in y direction")
    scale_z: float | None = Field(default=None, description="The scale in z direction")
    scale_t: float | None = Field(default=None, description="The scale in t direction")
    scale_c: float | None = Field(default=None, description="The scale in c direction")


@kante.pydantic_input(
    PartialScaleViewInputModel,
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


class PartialMaskViewInputModel(ViewInputModel):
    reference_view: str | None = Field(default=None, description="The ID of the view that is masked by this mask")
    labels: str | None = Field(default=None, description="The labels of the mask and their corresponding colors")


@kante.pydantic_input(
    PartialMaskViewInputModel,
    description="Input for creating a mask view (a label mask of another image) as part of creating an image; the image is taken from the surrounding input",
)
class PartialMaskViewInput(ViewInput):
    """Input for a mask view nested in image creation"""

    reference_view: ID | None = strawberry.field(default=None, description="The ID of the view that is masked by this mask")
    labels: scalars.LabelsLike | None = strawberry.field(default=None, description="The labels of the mask and their corresponding colors")


class PartialInstanceMaskViewInputModel(ViewInputModel):
    reference_view: str | None = Field(default=None, description="The ID of the view that is masked by this instance mask")
    labels: str | None = Field(default=None, description="The instance labels of the mask and their corresponding colors")


@kante.pydantic_input(
    PartialInstanceMaskViewInputModel,
    description="Input for creating an instance mask view (an instance mask of another image) as part of creating an image; the image is taken from the surrounding input",
)
class PartialInstanceMaskViewInput(ViewInput):
    """Input for an instance mask view nested in image creation"""

    reference_view: ID | None = strawberry.field(default=None, description="The ID of the view that is masked by this instance mask")
    labels: scalars.LabelsLike | None = strawberry.field(default=None, description="The instance labels of the mask and their corresponding colors")


class PartialReferenceViewInputModel(ViewInputModel):
    pass


@kante.pydantic_input(
    PartialReferenceViewInputModel,
    description="Input for creating a reference view (marking the region as a reference for other views) as part of creating an image; the image is taken from the surrounding input",
)
class PartialReferenceViewInput(ViewInput):
    """Input for a reference view nested in image creation.

    Adds no fields of its own; the slice bounds are re-declared here (rather than
    only inherited) because ``@pydantic_input`` needs at least one field annotation
    on the class to build the bridge.
    """

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


class PartialWellPositionViewInputModel(ViewInputModel):
    well: str | None = Field(default=None, description="The ID of the multi-well plate this view belongs to")
    row: int | None = Field(default=None, description="The row of the well")
    column: int | None = Field(default=None, description="The column of the well")


@kante.pydantic_input(
    PartialWellPositionViewInputModel,
    description="Input for creating a well position view (the well of a multi-well plate the region was acquired in) as part of creating an image; the image is taken from the surrounding input",
)
class PartialWellPositionViewInput(ViewInput):
    """Input for a well position view nested in image creation"""

    well: ID | None = strawberry.field(default=None, description="The ID of the multi-well plate this view belongs to")
    row: int | None = strawberry.field(default=None, description="The row of the well")
    column: int | None = strawberry.field(default=None, description="The column of the well")


class PartialContinoussScanViewInputModel(ViewInputModel):
    direction: enums.ScanDirection = Field(description="The direction of the scan")


@kante.pydantic_input(
    PartialContinoussScanViewInputModel,
    description="Input for creating a continuous scan view (the scan direction of the acquisition) as part of creating an image; the image is taken from the surrounding input",
)
class PartialContinoussScanViewInput(ViewInput):
    """Input for a continuous scan view nested in image creation"""

    direction: enums.ScanDirection = strawberry.field(description="The direction of the scan")


class PartialTimepointViewInputModel(ViewInputModel):
    era: str | None = Field(default=None, description="The ID of the era this timepoint belongs to")
    time_since_start: quantities.Duration | None = Field(default=None, description="The time since the start of the era (e.g. '100 ms')")
    index_since_start: int | None = Field(default=None, description="The index of the timepoint since the start of the era")


@kante.pydantic_input(
    PartialTimepointViewInputModel,
    description="Input for creating a timepoint view (placing the region in time relative to an era) as part of creating an image; the image is taken from the surrounding input",
)
class PartialTimepointViewInput(ViewInput):
    """Input for a timepoint view nested in image creation"""

    era: ID | None = strawberry.field(default=None, description="The ID of the era this timepoint belongs to")
    time_since_start: kanne_scalars.Duration | None = strawberry.field(default=None, description="The time since the start of the era (e.g. '100 ms')")
    index_since_start: int | None = strawberry.field(default=None, description="The index of the timepoint since the start of the era")


class AffineTransformationViewInputModel(PartialAffineTransformationViewInputModel):
    image: str = Field(description="The ID of the image this view is for")


@kante.pydantic_input(
    AffineTransformationViewInputModel,
    description="Input for creating an affine transformation view on an existing image, referenced by ID",
)
class AffineTransformationViewInput(PartialAffineTransformationViewInput):
    """Input for creating an affine transformation view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


class LabelViewInputModel(PartialLabelViewInputModel):
    image: str = Field(description="The ID of the image this view is for")


@kante.pydantic_input(
    LabelViewInputModel,
    description="Input for creating a label view on an existing image, referenced by ID",
)
class LabelViewInput(PartialLabelViewInput):
    """Input for creating a label view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


class AcquisitionViewInputModel(PartialAcquisitionViewInputModel):
    image: str = Field(description="The ID of the image this view is for")


@kante.pydantic_input(
    AcquisitionViewInputModel,
    description="Input for creating an acquisition view on an existing image, referenced by ID",
)
class AcquisitionViewInput(PartialAcquisitionViewInput):
    """Input for creating an acquisition view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


class RGBViewInputModel(PartialRGBViewInputModel):
    image: str = Field(description="The ID of the image this view is for")
    context: str = Field(description="The ID of the RGB render context this view belongs to")


@kante.pydantic_input(
    RGBViewInputModel,
    description="Input for creating an RGB render view on an existing image, referenced by ID",
)
class RGBViewInput(PartialRGBViewInput):
    """Input for creating an RGB render view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")
    context: ID = strawberry.field(description="The ID of the RGB render context this view belongs to")


class ContinousScanViewInputModel(PartialContinoussScanViewInputModel):
    image: str = Field(description="The ID of the image this view is for")


@kante.pydantic_input(
    ContinousScanViewInputModel,
    description="Input for creating a continuous scan view on an existing image, referenced by ID",
)
class ContinousScanViewInput(PartialContinoussScanViewInput):
    """Input for creating a continuous scan view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


class DerivedViewInputModel(PartialDerivedViewInputModel):
    image: str = Field(description="The ID of the image this view is for")


@kante.pydantic_input(
    DerivedViewInputModel,
    description="Input for creating a derived view on an existing image, referenced by ID",
)
class DerivedViewInput(PartialDerivedViewInput):
    """Input for creating a derived view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


class LightpathViewInputModel(PartialLightpathViewInputModel):
    image: str = Field(description="The ID of the image this view is for")


@kante.pydantic_input(
    LightpathViewInputModel,
    description="Input for creating a lightpath view on an existing image, referenced by ID",
)
class LightpathViewInput(PartialLightpathViewInput):
    """Input for creating a lightpath view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


class HistogramViewInputModel(PartialHistogramViewInputModel):
    image: str = Field(description="The ID of the image this view is for")


@kante.pydantic_input(
    HistogramViewInputModel,
    description="Input for creating a histogram view on an existing image, referenced by ID",
)
class HistogramViewInput(PartialHistogramViewInput):
    """Input for creating a histogram view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


class WellPositionViewInputModel(PartialWellPositionViewInputModel):
    image: str = Field(description="The ID of the image this view is for")


@kante.pydantic_input(
    WellPositionViewInputModel,
    description="Input for creating a well position view on an existing image, referenced by ID",
)
class WellPositionViewInput(PartialWellPositionViewInput):
    """Input for creating a well position view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


class TimepointViewInputModel(PartialTimepointViewInputModel):
    image: str = Field(description="The ID of the image this view is for")


@kante.pydantic_input(
    TimepointViewInputModel,
    description="Input for creating a timepoint view on an existing image, referenced by ID",
)
class TimepointViewInput(PartialTimepointViewInput):
    """Input for creating a timepoint view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


class OpticsViewInputModel(PartialOpticsViewInputModel):
    image: str = Field(description="The ID of the image this view is for")


@kante.pydantic_input(
    OpticsViewInputModel,
    description="Input for creating an optics view on an existing image, referenced by ID",
)
class OpticsViewInput(PartialOpticsViewInput):
    """Input for creating an optics view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


class ROIViewInputModel(PartialROIViewInputModel):
    image: str = Field(description="The ID of the image this view is for")


@kante.pydantic_input(
    ROIViewInputModel,
    description="Input for creating a ROI view on an existing image, referenced by ID",
)
class ROIViewInput(PartialROIViewInput):
    """Input for creating a ROI view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


class FileViewInputModel(PartialFileViewInputModel):
    image: str = Field(description="The ID of the image this view is for")


@kante.pydantic_input(
    FileViewInputModel,
    description="Input for creating a file view on an existing image, referenced by ID",
)
class FileViewInput(PartialFileViewInput):
    """Input for creating a file view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


class MaskViewInputModel(PartialMaskViewInputModel):
    image: str = Field(description="The ID of the image this view is for")


@kante.pydantic_input(
    MaskViewInputModel,
    description="Input for creating a mask view on an existing image, referenced by ID",
)
class MaskViewInput(PartialMaskViewInput):
    """Input for creating a mask view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


class InstanceMaskViewInputModel(PartialInstanceMaskViewInputModel):
    image: str = Field(description="The ID of the image this view is for")


@kante.pydantic_input(
    InstanceMaskViewInputModel,
    description="Input for creating an instance mask view on an existing image, referenced by ID",
)
class InstanceMaskViewInput(PartialInstanceMaskViewInput):
    """Input for creating an instance mask view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


class ReferenceViewInputModel(PartialReferenceViewInputModel):
    image: str = Field(description="The ID of the image this view is for")


@kante.pydantic_input(
    ReferenceViewInputModel,
    description="Input for creating a reference view on an existing image, referenced by ID",
)
class ReferenceViewInput(PartialReferenceViewInput):
    """Input for creating a reference view on an existing image"""

    image: ID = strawberry.field(description="The ID of the image this view is for")


def view_kwargs_from_input(input: ViewInputModel) -> dict:
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
