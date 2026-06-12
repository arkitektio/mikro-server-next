from kante.types import Info
import strawberry

from core import types, models, scalars
from datalayer.datalayer import get_current_datalayer
import json

from django.conf import settings
from django.contrib.auth import get_user_model
from core.managers import auto_create_views
import kante
from pydantic import BaseModel, Field
from lightpath.inputs.types import LightpathGraphInput
from lightpath.inputs.models import LightpathGraphInputModel
from core.scoping import get_for_org


class DimAnchorInputModel(BaseModel):
    dim: str
    value: int


@kante.pydantic_input(DimAnchorInputModel, description="Input type for a dimension anchor, which specifies a dimension and a value to anchor to")
class DimAnchorInput:
    dim: str = strawberry.field(description="The dimension to anchor to, e.g. 'x', 'y', 'z', 'c', or 't'")
    value: int = strawberry.field(description="The value to anchor the dimension to, e.g. 0 for the first position along that dimension")


class OmeMetadataInputModel(BaseModel):
    metadata_string: str = Field(..., description="The OME metadata as a JSON string")


@kante.pydantic_input(OmeMetadataInputModel, description="Input type for OME metadata")
class OmeMetadataInput:
    metadata_string: str = strawberry.field(description="The OME metadata as a JSON string")


class ValueHistogramInputModel(BaseModel):
    histogram: list[float] = Field(..., description="The histogram of the pixel values (y values)")
    bins: list[float] = Field(..., description="The bin indices of the histogram (x values)")
    min: float | None = Field(None, description="The minimum pixel value of the histogram")
    max: float | None = Field(None, description="The maximum pixel value of the histogram")
    p1: float | None = Field(None, description="The 1st percentile pixel value of the histogram")
    p99: float | None = Field(None, description="The 99th percentile pixel value of the histogram")


@kante.pydantic_input(ValueHistogramInputModel, description="Input type for a value histogram, which specifies the histogram of pixel values along certain dimensions to provide additional context about the distribution of pixel values in an image")
class ValueHistogramInput:
    histogram: list[float] = strawberry.field(description="The histogram of the pixel values (y values)")
    bins: list[float] = strawberry.field(description="The bin indices of the histogram (x values)")
    min: float | None = strawberry.field(default=None, description="The minimum pixel value of the histogram")
    max: float | None = strawberry.field(default=None, description="The maximum pixel value of the histogram")
    p1: float | None = strawberry.field(default=None, description="The 1st percentile pixel value of the histogram")
    p99: float | None = strawberry.field(default=None, description="The 99th percentile pixel value of the histogram")


class ValueHistogramInputModel(BaseModel):
    histogram: list[float] = Field(..., description="The histogram of the pixel values (y values)")
    bins: list[float] = Field(..., description="The bin indices of the histogram (x values)")
    min: float | None = Field(None, description="The minimum pixel value of the histogram")
    max: float | None = Field(None, description="The maximum pixel value of the histogram")
    p1: float | None = Field(None, description="The 1st percentile pixel value of the histogram")
    p99: float | None = Field(None, description="The 99th percentile pixel value of the histogram")


@kante.pydantic_input(ValueHistogramInputModel, description="Input type for a value histogram, which specifies the histogram of pixel values along certain dimensions to provide additional context about the distribution of pixel values in an image")
class ValueHistogramInput:
    histogram: list[float] = strawberry.field(description="The histogram of the pixel values (y values)")
    bins: list[float] = strawberry.field(description="The bin indices of the histogram (x values)")
    min: float | None = strawberry.field(default=None, description="The minimum pixel value of the histogram")
    max: float | None = strawberry.field(default=None, description="The maximum pixel value of the histogram")
    p1: float | None = strawberry.field(default=None, description="The 1st percentile pixel value of the histogram")
    p99: float | None = strawberry.field(default=None, description="The 99th percentile pixel value of the histogram")


class LabelInputModel(BaseModel):
    label: str


@kante.pydantic_input(LabelInputModel, description="Input type for a label, which specifies a label to associate with a coordinate anchor or an image")
class LabelInput:
    label: str = strawberry.field(description="The label to associate with the coordinate anchor or image, which can provide additional context about the content of the image or the significance of the coordinate anchor")


class CoordinateAnchorInputModel(BaseModel):
    dim_anchors: list[DimAnchorInputModel]
    ome_metadata: OmeMetadataInputModel | None = None
    value_histogram: ValueHistogramInputModel | None = None
    label: LabelInputModel | None = None
    light_graph: LightpathGraphInputModel | None = None


@kante.pydantic_input(CoordinateAnchorInputModel, description="Input type for a coordinate anchor, which specifies a list of dimension anchors to anchor to")
class CoordinateAnchorInput:
    dim_anchors: list[DimAnchorInput] = strawberry.field(description="A list of dimension anchors to anchor to, e.g. [{'dim': 'z', 'value': 0}, {'dim': 't', 'value': 5}] to anchor to the first position along the z dimension and the sixth position along the t dimension")
    ome_metadata: OmeMetadataInput | None = strawberry.field(default=None, description="Optional OME metadata to associate with the choordinate anchor, which can provide additional context about the dimensions being anchored to")
    value_histogram: ValueHistogramInput | None = strawberry.field(default=None, description="Optional value histogram to associate with the coordinate anchor, which can provide additional context about the distribution of pixel values along the anchored dimensions")
    label: LabelInput | None = strawberry.field(default=None, description="Optional label to associate with the coordinate anchor, which can provide additional context about the significance of the coordinate anchor or the content of the image at that coordinate")
    light_graph: LightpathGraphInput | None = strawberry.field(default=None, description="Optional lightpath graph to associate with the coordinate anchor, which can provide additional context about the optical path that was used to acquire the image at that coordinate")


class DimensionDescriptorInputModel(BaseModel):
    key: str
    kind: str


@kante.pydantic_input(DimensionDescriptorInputModel, description="Input type for a dimension descriptor, which specifies a key and a kind for a dimension")
class DimensionDescriptorInput:
    key: str = strawberry.field(description="The key of the dimension, e.g. 'x', 'y', 'z', 'c', or 't'")
    kind: str = strawberry.field(description="The kind of the dimension, e.g. 'space', 'channel', or 'time'")


class ScaleInputModel(BaseModel):
    level: int
    array: str = Field(..., description="The array-like object to create the image from")
    scale_factors: list[float] | None = Field(..., description="The scale factors for each dimension of the image, which specify the physical size of each pixel along each dimension and can be used to provide additional context about the spatial resolution of the image")


@kante.pydantic_input(ScaleInputModel, description="Input type for a scale, which specifies an array-like object to create the image from and optional scale factors for each dimension of the image")
class ScaleInput:
    level: int = strawberry.field(description="The level of the scale, where 0 is the highest resolution scale and higher levels are lower resolution scales")
    array: scalars.ArrayLike = strawberry.field(description="The array-like object to create the image from")
    scale_method: str | None = strawberry.field(default=None, description="The method used to create the scale, e.g. 'nearest', 'bilinear', 'bicubic', etc. This can be used to provide additional context about how the scale was created and the expected quality of the scale")
    scale_factors: list[float] | None = strawberry.field(default=None, description="The scale factors for each dimension of the image, which specify the physical size of each pixel along each dimension and can be used to provide additional context about the spatial resolution of the image")


class CreateDatasetInputModel(BaseModel):
    data: str
    scales: list[ScaleInputModel]
    name: str
    dataset: strawberry.ID | None = None
    dim_descriptors: list[DimensionDescriptorInputModel]
    anchors: list[CoordinateAnchorInputModel] | None = None


@kante.pydantic_input(CreateDatasetInputModel, description="Input type for creating an image from an array-like object")
class CreateADatasetInput:
    data: scalars.ArrayLike = strawberry.field(description="The array-like object to create the image from")
    scales: list[ScaleInput] = strawberry.field(
        description="Scaled Pyramid levels to create for the image, where each level specifies an array-like object to create the image from and optional scale factors for each dimension of the image, which can be used to provide additional context about the spatial resolution of the image"
    )
    name: str = strawberry.field(description="The name of the image")
    dim_descriptors: list[DimensionDescriptorInput] = strawberry.field(description="Optional list of dimension descriptors to associate with the image, which can provide additional context about the dimensions of the image by specifying keys and kinds for each dimension")
    anchors: list[CoordinateAnchorInput] | None = strawberry.field(
        default=None, description="Optional list of choordinate anchors to associate with the image, which can specify specific positions along certain dimensions to anchor to and optional OME metadata for additional context about those dimensions"
    )


def create_adataset(
    info: Info,
    input: CreateADatasetInput,
) -> types.ADataset:
    model = input.to_pydantic()

    datalayer = get_current_datalayer()

    data_scale = model.data
    data_store = get_for_org(models.ZarrStore, info, id=data_scale)
    data_store.fill_info(datalayer)

    data_store_dims = len(data_store.shape)

    assert data_store_dims == len(model.dim_descriptors), "Dimension lenght mismatch. You provided {} dimension descriptors but the data has {} dimensions".format(len(model.dim_descriptors), data_store_dims)

    dataset = models.ADataset.objects.create(
        name=input.name,
        dims=[desc.key for desc in model.dim_descriptors],
        dim_descriptors=[model.model_dump() for model in model.dim_descriptors],
        shape=data_store.shape,
        organization=info.context.request.organization,
        creator=info.context.request.user,
    )

    x = models.DataArray.objects.create(
        level=0,
        store=data_store,
        dataset=dataset,
        shape=data_store.shape,
        chunk_shape=data_store.chunks,
    )

    for scale in model.scales:
        scale_store = get_for_org(models.ZarrStore, info, id=scale.array)
        scale_store.fill_info(datalayer)

        assert len(scale_store.shape) == data_store_dims, "Dimension lenght mismatch for scale level {}. You provided {} dimension descriptors but the data has {} dimensions".format(scale.level, len(model.dim_descriptors), len(scale_store.shape))

        models.DataArray.objects.create(
            level=scale.level,
            store=scale_store,
            dataset=dataset,
            shape=scale_store.shape,
            chunk_shape=scale_store.chunks,
            scale_factors=scale.scale_factors,
        )

        # Check that the scale factors are consistent with the shapes of the data and the scale if scale factors are provided
        if scale.scale_factors is not None:
            expected_scale_shape = tuple(int(data_dim / scale_factor) for data_dim, scale_factor in zip(data_store.shape, scale.scale_factors))

    for anchor in model.anchors or []:
        coordinate_anchor = models.CoordinateAnchor.objects.create(
            dataset=dataset,
            coordinates={anchor.dim: anchor.value for anchor in anchor.dim_anchors},
        )

        if anchor.ome_metadata:
            print("Creating OME metadata for coordinate anchor with coordinates {}".format(coordinate_anchor.coordinates))
            models.OmeMetadata.objects.create(
                anchor=coordinate_anchor,
                metadata={} if anchor.ome_metadata.metadata_string == "" else json.loads(anchor.ome_metadata.metadata_string),
            )

        if anchor.value_histogram:
            models.ValueHistogram.objects.create(
                anchor=coordinate_anchor,
                histogram=anchor.value_histogram.histogram,
                bins=anchor.value_histogram.bins,
                min=anchor.value_histogram.min,
                max=anchor.value_histogram.max,
                p1=anchor.value_histogram.p1,
                p99=anchor.value_histogram.p99,
            )

        if anchor.label:
            models.ChannelLabel.objects.create(
                anchor=coordinate_anchor,
                label=anchor.label.label,
            )

        if anchor.light_graph:
            light_graph = models.LightPath.objects.create(
                anchor=coordinate_anchor,
                graph=anchor.light_graph.model_dump(),
            )

    return dataset
