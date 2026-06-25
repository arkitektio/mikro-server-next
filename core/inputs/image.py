"""GraphQL input types for image creation."""

import strawberry

from core import scalars
from core.inputs.views import (
    PartialAcquisitionViewInput,
    PartialAffineTransformationViewInput,
    PartialChannelViewInput,
    PartialDerivedViewInput,
    PartialFileViewInput,
    PartialInstanceMaskViewInput,
    PartialLightpathViewInput,
    PartialMaskViewInput,
    PartialOpticsViewInput,
    PartialRGBViewInput,
    PartialROIViewInput,
    PartialReferenceViewInput,
    PartialScaleViewInput,
    PartialTimepointViewInput,
)


@strawberry.input(description="Input type for creating an image from an array-like object")
class FromArrayLikeInput:
    """Input for creating an image from an array-like object together with its partial views"""

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
