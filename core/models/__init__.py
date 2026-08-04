"""Django models for the core app, split by domain.

Every public name is re-exported here so that ``from core import models``
and ``from core.models import X`` keep working everywhere (including
migrations, which reference e.g. ``core.models.create_default_color``).
"""

# Re-exported store models: the old monolithic ``core/models.py`` imported
# these at module level, and code such as ``core/filters.py`` and the
# mutations access them as ``models.ZarrStore`` etc.
#
# Dependency rule between the apps: core may depend on datalayer models (they
# are FK targets of Image/File/Table and re-exported here for convenience),
# but datalayer must never import core — it is the storage backend, agnostic
# of the domain on top of it (guarded by tests/test_architecture.py). All
# runtime storage I/O goes through ``datalayer.datalayer.get_current_datalayer()``,
# never through boto3/zarr directly.
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
    FileLink,
    Table,
    Experiment,
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
from .coords import (
    CoordinateSystem,
    Axis,
    Transformation,
    MeshCollection,
)
from .table_dataset import (
    TableDataset,
    TableColumn,
)
from .annotation import (
    AnnotationCollection,
    Annotation,
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
    PhasorHistogram,
    PhasorCalibration,
    Lens,
    Scene,
    SceneSnapshot,
    Animation,
    AnimationWaypoint,
    Layer,
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
    "FileLink",
    "Table",
    "Experiment",
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
    # coords (the RFC-5 coordinate system graph)
    "CoordinateSystem",
    "Axis",
    "Transformation",
    "MeshCollection",
    # table dataset
    "TableDataset",
    "TableColumn",
    # annotations
    "AnnotationCollection",
    "Annotation",
    # adataset
    "ADataset",
    "DataArray",
    "CoordinateAnchor",
    "OptikitState",
    "OmeMetadata",
    "ValueHistogram",
    "ChannelLabel",
    "LightPath",
    "PhasorHistogram",
    "PhasorCalibration",
    "Lens",
    "Scene",
    "SceneSnapshot",
    "Animation",
    "AnimationWaypoint",
    "Layer",
]
