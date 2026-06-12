"""GraphQL input types shared across mutations.

Input classes live here (not in ``core.mutations``) so the service layer in
``core.logic`` can reference them without importing mutation modules.
"""

import strawberry_django
from core import models
from typing import List, Optional
from strawberry import ID
import strawberry
import kante
from core import base_models

from core.inputs.views import (
    AcquisitionViewInput,
    AffineTransformationViewInput,
    ChannelViewInput,
    ContinousScanViewInput,
    DerivedViewInput,
    FileViewInput,
    HistogramViewInput,
    InstanceMaskViewInput,
    LabelViewInput,
    LightpathViewInput,
    MaskViewInput,
    OpticsViewInput,
    PartialAcquisitionViewInput,
    PartialAffineTransformationViewInput,
    PartialChannelViewInput,
    PartialContinoussScanViewInput,
    PartialDerivedViewInput,
    PartialFileViewInput,
    PartialHistogramViewInput,
    PartialInstanceMaskViewInput,
    PartialLabelViewInput,
    PartialLightpathViewInput,
    PartialMaskViewInput,
    PartialOpticsViewInput,
    PartialRGBViewInput,
    PartialROIViewInput,
    PartialReferenceViewInput,
    PartialScaleViewInput,
    PartialTimepointViewInput,
    PartialWellPositionViewInput,
    ROIViewInput,
    ReferenceViewInput,
    RGBViewInput,
    TimepointViewInput,
    UpdateRGBViewInput,
    ViewInput,
    WellPositionViewInput,
    view_kwargs_from_input,
)


@strawberry_django.input(models.Image, description="Input for creating an image, linking it to its dataset, creator and origin images")
class ImageInput:
    """Input for creating an image"""

    origins: Optional[List[ID]] = strawberry.field(description="The IDs of the images this image was derived from")
    dataset: Optional[ID] = strawberry.field(description="The ID of the dataset the image belongs to")
    creator: ID = strawberry.field(description="The ID of the user that created the image")


@strawberry_django.input(models.Dataset, description="Input for creating a dataset, a named collection of images")
class DatasetInput:
    """Input for creating a dataset"""

    name: str = strawberry.field(description="The name of the dataset")
    description: str = strawberry.field(description="A cleartext description of the dataset")


@strawberry.input(description="An input for associating a set of items with another item, e.g. putting images into a dataset")
class AssociateInput:
    """Input for associating a set of items with another item"""

    selfs: List[strawberry.ID] = strawberry.field(description="The IDs of the items to associate")
    other: strawberry.ID = strawberry.field(description="The ID of the target item")


@strawberry.input(description="An input for releasing a set of items from another item, e.g. removing images from a dataset")
class DesociateInput:
    """Input for releasing a set of items from another item"""

    selfs: List[strawberry.ID] = strawberry.field(description="The IDs of the items to release")
    other: strawberry.ID = strawberry.field(description="The ID of the target item")


@kante.pydantic_input(base_models.SliceInputModel, description="Input type for a dimension descriptor, which specifies a key and a kind for a dimension")
class SliceInput:
    """Input for a slice along a single dimension of an image"""

    dim: str = strawberry.field(description="The key of the dimension, e.g. 'x', 'y', 'z', 'c', or 't'")
    start: int | None = strawberry.field(default=None, description="The starting index of the slice, or None to start from the beginning")
    stop: int | None = strawberry.field(default=None, description="The stopping index of the slice, or None to go to the end")
    step: int | None = strawberry.field(default=None, description="The step size of the slice, or None to use the default step")
