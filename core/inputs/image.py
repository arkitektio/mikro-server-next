"""GraphQL input types for image creation."""

import kante
import strawberry
from pydantic import BaseModel, Field

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
from core.inputs.views import (
    PartialAcquisitionViewInputModel,
    PartialAffineTransformationViewInputModel,
    PartialChannelViewInputModel,
    PartialDerivedViewInputModel,
    PartialFileViewInputModel,
    PartialInstanceMaskViewInputModel,
    PartialLightpathViewInputModel,
    PartialMaskViewInputModel,
    PartialOpticsViewInputModel,
    PartialRGBViewInputModel,
    PartialROIViewInputModel,
    PartialReferenceViewInputModel,
    PartialScaleViewInputModel,
    PartialTimepointViewInputModel,
)


class FromArrayLikeInputModel(BaseModel):
    array: str = Field(description="The array-like object to create the image from")
    name: str = Field(description="The name of the image")
    dataset: str | None = Field(default=None, description="Optional dataset ID to associate the image with")
    channel_views: list[PartialChannelViewInputModel] | None = Field(default=None, description="Optional list of channel views")
    transformation_views: list[PartialAffineTransformationViewInputModel] | None = Field(default=None, description="Optional list of affine transformation views")
    acquisition_views: list[PartialAcquisitionViewInputModel] | None = Field(default=None, description="Optional list of acquisition views")
    mask_views: list[PartialMaskViewInputModel] | None = Field(default=None, description="Optional list of mask views")
    reference_views: list[PartialReferenceViewInputModel] | None = Field(default=None, description="Optional list of reference views")
    instance_mask_views: list[PartialInstanceMaskViewInputModel] | None = Field(default=None, description="Optional list of instance mask views")
    rgb_views: list[PartialRGBViewInputModel] | None = Field(default=None, description="Optional list of RGB views")
    timepoint_views: list[PartialTimepointViewInputModel] | None = Field(default=None, description="Optional list of timepoint views")
    optics_views: list[PartialOpticsViewInputModel] | None = Field(default=None, description="Optional list of optics views")
    scale_views: list[PartialScaleViewInputModel] | None = Field(default=None, description="Optional list of scale views")
    tags: list[str] | None = Field(default=None, description="Optional list of tags to associate with the image")
    roi_views: list[PartialROIViewInputModel] | None = Field(default=None, description="Optional list of ROI views")
    file_views: list[PartialFileViewInputModel] | None = Field(default=None, description="Optional list of file views")
    derived_views: list[PartialDerivedViewInputModel] | None = Field(default=None, description="Optional list of derived views")
    lightpath_views: list[PartialLightpathViewInputModel] | None = Field(default=None, description="Optional list of lightpath views")


@kante.pydantic_input(FromArrayLikeInputModel, description="Input type for creating an image from an array-like object")
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
