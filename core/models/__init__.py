"""Django models for the core app, split by domain.

Every public name is re-exported here so that ``from core import models``
and ``from core.models import X`` keep working everywhere (including
migrations, which reference e.g. ``core.models.create_default_color``).
"""

# Re-exported store models: the old monolithic ``core/models.py`` imported
# these at module level, and code such as ``core/filters.py`` and the
# mutations access them as ``models.ZarrStore`` etc.
from datalayer.models import (
    ZarrStore,
    BigFileStore,
    ParquetStore,
    MediaStore,
)

from .dataset import (
    DatasetManager,
    Dataset,
    File,
    Table,
    Experiment,
    Mesh,
)
from .instrumentation import (
    Objective,
    Camera,
    Instrument,
)
from .image import (
    Image,
    Render,
    Blurhash,
    Video,
    Snapshot,
)
from .meta import (
    MetaSchema,
    UnstructuredMeta,
)
from .stage import (
    Stage,
    MultiWellPlate,
    Era,
)
from .roi import (
    ROIGroup,
    random_color,
    ROI,
)
from .view import (
    ViewCollection,
    View,
    OpticsView,
    LightpathView,
    ScaleView,
    AlphaView,
    ContinousScanView,
    WellPositionView,
    ChannelView,
    ReferenceView,
    FileView,
    HistogramView,
    TableView,
    DerivedView,
    ROIView,
    Accessor,
    LabelAccessor,
    ImageAccessor,
    RGBRenderContext,
    RenderTree,
    AcquisitionView,
    create_default_color,
    RGBView,
    TimepointView,
    LabelView,
    MaskView,
    InstanceMaskView,
    AffineTransformationView,
    CropView,
)
from .adataset import (
    ADataset,
    DataArray,
    CoordinateAnchor,
    OptikitState,
    OmeMetadata,
    ValueHistogram,
    ChannelLabel,
    LightPath,
    OmePlaneMetadata,
    Lens,
    Scene,
    Layer,
    DataRoi,
    LineageLink,
)

__all__ = [
    # datalayer stores (re-exported for backwards compatibility)
    "ZarrStore",
    "BigFileStore",
    "ParquetStore",
    "MediaStore",
    # dataset
    "DatasetManager",
    "Dataset",
    "File",
    "Table",
    "Experiment",
    "Mesh",
    # instrumentation
    "Objective",
    "Camera",
    "Instrument",
    # image
    "Image",
    "Render",
    "Blurhash",
    "Video",
    "Snapshot",
    # meta
    "MetaSchema",
    "UnstructuredMeta",
    # stage
    "Stage",
    "MultiWellPlate",
    "Era",
    # roi
    "ROIGroup",
    "random_color",
    "ROI",
    # view
    "ViewCollection",
    "View",
    "OpticsView",
    "LightpathView",
    "ScaleView",
    "AlphaView",
    "ContinousScanView",
    "WellPositionView",
    "ChannelView",
    "ReferenceView",
    "FileView",
    "HistogramView",
    "TableView",
    "DerivedView",
    "ROIView",
    "Accessor",
    "LabelAccessor",
    "ImageAccessor",
    "RGBRenderContext",
    "RenderTree",
    "AcquisitionView",
    "create_default_color",
    "RGBView",
    "TimepointView",
    "LabelView",
    "MaskView",
    "InstanceMaskView",
    "AffineTransformationView",
    "CropView",
    # adataset
    "ADataset",
    "DataArray",
    "CoordinateAnchor",
    "OptikitState",
    "OmeMetadata",
    "ValueHistogram",
    "ChannelLabel",
    "LightPath",
    "OmePlaneMetadata",
    "Lens",
    "Scene",
    "Layer",
    "DataRoi",
    "LineageLink",
]
