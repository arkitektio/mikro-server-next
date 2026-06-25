import strawberry
import strawberry_django
from strawberry import auto
from typing import Any, Dict, List, Optional, Annotated, Union, cast
from core import models, scalars, filters, enums
from kante.types import Info
import datetime
from itertools import chain
from enum import Enum
from core.type_gen import create_stats_type
from core.duck import get_current_duck
from core.logic import tables as table_logic
from lightpath.objects.types import LightpathGraph
from lightpath.objects.models import LightpathGraphModel
import kante
from datalayer.types import ZarrStore, ParquetStore, BigFileStore

from core import order
import logging

from core.types._shared import build_prescoped_queryset
from core.types.auth import Organization, ProvenanceEntry, Task, User
from core.types.renders import IMAGE_RENDER_RELATIONS, Render, RenderKind, Snapshot, Video
from core.types.instrumentation import Camera, Instrument, Objective
from core.types.acquisition import Era, MultiWellPlate, Stage

logger = logging.getLogger(__name__)


@kante.django_type(
    models.ViewCollection,
    filters=filters.ViewCollectionFilter,
    ordering=order.ViewCollectionOrder,
    pagination=True,
    description="A collection of views. View collections provide overarching views on your data that are not bound to a specific image, e.g. all middle-z views of all images with a certain tag. They are a pure metadata construct and do not map to an ordering of binary data.",
)
class ViewCollection:
    """A colletion of views.

        View collections are use to provide overarching views on your data,
        that are not bound to a specific image. For example, you can create
        a view collection that includes all middle z views of all images with
        a certain tag.

        View collections are a pure metadata construct and will not map to
        oredering of binary data.

    I
    """

    id: auto
    name: auto
    views: List["View"]
    provenance_entries: List["ProvenanceEntry"] = kante.django_field(description="Provenance entries for this view collection")
    affine_transformation_views: List["AffineTransformationView"]
    label_views: List["LabelView"]
    channel_views: List["ChannelView"]


@strawberry.enum
class ViewKind(str, Enum):
    """The kind of view.

    Views can be of different kinds. For example, a view can be a label view
    that will map a labeleling agent (e.g. an antibody) to a specific image channel.

    Depending on the kind of view, different fields will be available.

    """

    CHANNEL = "channel_views"
    LABEL = "label_views"
    AFFINE_TRANSFORMATION = "affine_transformation_views"
    TIMEPOINT = "timepoint_views"
    OPTICS = "optics_views"
    HISTOGRAM = "histogram_views"
    MASK_VIEW = "mask_views"
    INSTANCE_MASK_VIEW = "instance_mask_views"
    REFERENCE = "reference_views"
    LIGHTPATH = "lightpath_views"
    RGB = "rgb_views"
    WELL_POSITION = "wellposition_views"
    CONTINOUS_SCAN = "continousscan_views"
    ACQUISITION = "acquisition_views"
    SCALE = "scale_views"
    ROI = "roi_views"
    FILE = "file_views"
    DERIVED = "derived_views"


# The single source of truth for the view relations on Image: the enum values
# are the Django related names, so deriving the default list from the enum
# keeps the `types:` argument able to select every kind a resolver returns.
IMAGE_VIEW_RELATIONS: list[str] = [kind.value for kind in ViewKind]


@strawberry.enum
class AccessorKind(str, Enum):
    """The kind of accessors.

    Accessors can be of different kinds. For example, an accessor can be a label accessor
    that will map a labeleling agent (e.g. an antibody) to a specific image channel.

    """

    LABEL = "label_accessors"
    IMAGE = "image_accessors"


@kante.django_type(models.Experiment, filters=filters.ExperimentFilter, ordering=order.ExperimentOrder, pagination=True, description="An experiment. Experiments are used to group datasets and images that belong to the same scientific investigation, carrying a name and a description.")
class Experiment:
    id: auto
    name: str
    description: str | None
    provenance_entries: List["ProvenanceEntry"] = kante.django_field(description="Provenance entries for this experiment")
    created_at: datetime.datetime
    creator: User | None


@kante.type(description="A cell of a table")
class TableCell:
    id: strawberry.ID
    table: "Table"
    row_id: int
    column_id: int
    value: scalars.Any

    @kante.django_field(description="The column this cell belongs to")
    def column(self, info: Info) -> "TableColumn":
        # self.table holds the Django model; the duck SQL lives in core.logic.tables.
        return TableColumn(_duckdb_column=table_logic.columns(self.table)[self.column_id], _table_id=str(self.table.id))

    @kante.django_field(description="The name of the column this cell belongs to")
    def name(self, info: Info) -> str:
        return table_logic.columns(self.table)[self.column_id][0]


@kante.type(description="A row of a table")
class TableRow:
    id: strawberry.ID
    table: "Table"
    row_id: int

    @kante.django_field(description="The column descriptors of the table")
    def columns(self, info: Info) -> List["TableColumn"]:
        return [TableColumn(_duckdb_column=c, _table_id=str(self.table.id)) for c in table_logic.columns(self.table)]

    @kante.django_field(description="The values of this row, one per column")
    def values(self, info: Info) -> List[scalars.Any]:
        return parseRow(table_logic.row_values(self.table, self.row_id))

    @kante.django_field(description="The display name of this row")
    def name(self, info: Info) -> str:
        return f"Row {self.row_id}"


@kante.type(description="A column descriptor")
class TableColumn:
    _duckdb_column: strawberry.Private[list[str]]
    _table_id: strawberry.Private[str]

    @kante.field()
    def name(self) -> str:
        return self._duckdb_column[0]

    @kante.field()
    def type(self) -> enums.DuckDBDataType:
        return self._duckdb_column[1]

    @kante.field()
    def nullable(self) -> bool:
        return self._duckdb_column[2] == "YES"

    @kante.field()
    def key(self) -> str | None:
        return self._duckdb_column[3]

    @kante.field()
    def default(self) -> str | None:
        return str(self._duckdb_column[4])

    @kante.django_field()
    def accessors(
        self,
        info: Info,
        filters: filters.AccessorFilter | None = strawberry.UNSET,
        types: List[AccessorKind] | None = strawberry.UNSET,
    ) -> List["Accessor"]:
        if types is strawberry.UNSET:
            view_relations = [
                "label_accessors",
                "image_accessors",
            ]
        else:
            view_relations = [kind.value for kind in types]

        results = []

        base = models.Table.objects.get(id=self._table_id)

        for relation in view_relations:
            qs = getattr(base, relation).filter(keys__contains=[self._duckdb_column[0]]).all()

            # apply filters if defined
            if filters is not strawberry.UNSET:
                qs = strawberry_django.filters.apply(filters, qs, info)

            results.append(qs)

        return list(chain(*results))


def parseRow(row) -> scalars.MetricMap:
    parsed_row = []
    for idx, value in enumerate(row):
        if isinstance(value, bytes):
            try:
                value = value.decode("utf-8")
            except Exception:
                value = str(value)
        elif isinstance(value, memoryview):
            try:
                value = value.tobytes().decode("utf-8")
            except Exception:
                value = str(value)
        elif isinstance(value, list):
            try:
                value = [float(x) for x in value]
            except Exception:
                value = [str(x) for x in value]
        elif isinstance(value, dict):
            try:
                value = {str(k): float(v) for k, v in value.items()}
            except Exception:
                value = {str(k): str(v) for k, v in value.items()}

        elif isinstance(value, float):
            if value == float("inf") or value == float("-inf") or value != value:
                value = str(value)
        elif isinstance(value, datetime.date):
            value = value.isoformat()

        else:
            value = str(value)

        parsed_row.append(value)

    return parsed_row


@kante.django_type(models.Table, filters=filters.TableFilter, ordering=order.TableOrder, pagination=True, federated=True, description="A table of tabular data, stored as a Parquet file. Tables are typically derived from images (e.g. measurements or localisations) and can be queried column- and row-wise through the API.")
class Table:
    id: auto
    name: auto
    origins: List["Image"] = kante.django_field()
    store: ParquetStore
    created_through: Optional[Task] = kante.django_field(description="The task this table was created through, if any")
    created_through_by: Optional[User] = kante.django_field(description="The assigner of the creating task, if any")

    @kante.django_field(description="The column descriptors of the table's parquet data")
    def columns(self, info: Info) -> List[TableColumn]:
        return [TableColumn(_duckdb_column=c, _table_id=str(self.id)) for c in table_logic.columns(cast(models.Table, self))]

    @kante.django_field(description="All rows of the table's parquet data")
    def rows(self, info: Info) -> List[scalars.MetricMap]:
        x = get_current_duck()

        sql = f"""
            SELECT * FROM read_parquet('{table_logic.parquet_source(cast(models.Table, self))}');
            """

        result = x.connection.sql(sql)

        return [parseRow(x) for x in result.fetchall()]

    @kante.django_field()
    def accessors(
        self,
        info: Info,
        filters: filters.AccessorFilter | None = strawberry.UNSET,
        types: List[AccessorKind] | None = strawberry.UNSET,
    ) -> List["Accessor"]:
        if types is strawberry.UNSET:
            view_relations = [
                "label_accessors",
                "image_accessors",
            ]
        else:
            view_relations = [kind.value for kind in types]

        results = []

        for relation in view_relations:
            qs = getattr(self, relation).all()

            # apply filters if defined
            if filters is not strawberry.UNSET:
                qs = strawberry_django.filters.apply(filters, qs, info)

            results.append(qs)

        return list(chain(*results))


@kante.type(description="A channel descriptor")
class ChannelInfo:
    _image: strawberry.Private[models.Image]
    _channel: strawberry.Private[int]

    @kante.django_field()
    def label(self, with_color_name: bool = False) -> str:
        name = f"Channel {self._channel}"

        if with_color_name:
            for i in self._image.rgb_views.filter(c_max__gt=self._channel, c_min__lte=self._channel).all():
                name += f" ({i.colormap_name})"

        return name

    @kante.django_field()
    def index(self) -> int:
        return self._channel


@kante.type(description="A channel descriptor")
class FrameInfo:
    _image: strawberry.Private[models.Image]
    _frame: strawberry.Private[int]

    @kante.field()
    def label(self) -> str:
        return f"Frame {self._frame}"


@kante.type(description="A channel descriptor")
class PlaneInfo:
    _image: strawberry.Private[models.Image]
    _plane: strawberry.Private[int]

    @kante.field()
    def label(self) -> str:
        return f"Plane {self._plane}"


@kante.django_type(models.File, filters=filters.FileFilter, pagination=True, federated=True, ordering=order.FileOrder, description="A file in its original format (e.g. a microscopy vendor file), stored in a BigFileStore. Files are the raw sources that images are converted from, and file views link back to the images that originated from them.")
class File:
    id: auto
    name: auto
    origins: List["Image"] = kante.django_field()
    store: BigFileStore
    views: List["FileView"] = kante.django_field()
    provenance_entries: List["ProvenanceEntry"] = kante.django_field(description="Provenance entries for this file")
    creator: User = kante.django_field(description="The user who created this file")
    created_through: Optional[Task] = kante.django_field(description="The task this file was created through, if any")
    created_through_by: Optional[User] = kante.django_field(description="The assigner of the creating task, if any")
    organization: Organization = kante.django_field(description="The organization this file belongs to")
    size: float | None = kante.django_field(description="The size of the file in bytes")
    content_type: str | None = kante.django_field(description="The content type of the file")

    @classmethod
    def get_queryset(cls, queryset, info, **kwargs):
        return build_prescoped_queryset(info, queryset)


@kante.django_type(models.Image, filters=filters.ImageFilter, ordering=order.ImageOrder, pagination=True, federated=True, description="An image. Images are the central data type in mikro: a single 5D bioimage whose binary data is stored in a ZarrStore. Images can be annotated with views (coordinate-ordered subsets of the image) and are the primary container that rois, metrics, renders and generated tables are bound to.")
class Image:
    """An image.


    Images are the central data type in mikro. They represent a single 5D bioimage, which
    binary data is stored in a ZarrStore. Images can be annotated with views, which are
    subsets of the image, ordered by its coordinates. Views can be of different kinds, for
    example, a label view will map a labeling agent (e.g. an antibody) to a specific image
    channel. Depending on the kind of view, different fields will be available.

    Images also represent the primary data container for other models of the mikro data model.
    For example rois, metrics, renders, and generated tables are all bound to a specific image,
    and will share the lifecycle of the image.

    """

    id: auto
    name: auto = kante.django_field(description="The name of the image")
    store: ZarrStore = kante.django_field(description="The store where the image data is stored.")
    snapshots: List["Snapshot"] = kante.django_field(description="Associated snapshots")
    videos: List["Video"] = kante.django_field(description="Associated videos")
    dataset: Optional["Dataset"] = kante.django_field(description="The dataset this image belongs to")
    provenance_entries: List["ProvenanceEntry"] = kante.django_field(description="Provenance entries for this image")
    affine_transformation_views: List["AffineTransformationView"] = kante.django_field(description="The affine transformation views describing position and scale")
    label_views: List["LabelView"] = kante.django_field(description="Label views mapping channels to labels")
    channel_views: List["ChannelView"] = kante.django_field(description="Channel views relating to acquisition channels")
    timepoint_views: List["TimepointView"] = kante.django_field(description="Timepoint views describing temporal relationships")
    optics_views: List["OpticsView"] = kante.django_field(description="Optics views describing acquisition settings")
    mask_views: List["MaskView"] = kante.django_field(description="Structure views relating other Arkitekt types to a subsection of the image")
    instance_mask_views: List["InstanceMaskView"] = kante.django_field(description="Instance mask views relating other Arkitekt types to a subsection of the image")
    scale_views: List["ScaleView"] = kante.django_field(description="Scale views describing physical dimensions")
    histogram_views: List["HistogramView"] = kante.django_field(description="Histogram views describing pixel value distribution")
    reference_views: List["ReferenceView"] = kante.django_field(description="Reference views describing relationships to other views")
    created_at: datetime.datetime = kante.django_field(description="When this image was created")
    creator: User | None = kante.django_field(description="Who created this image")
    created_through: Optional[Task] = kante.django_field(description="The task this image was created through, if any")
    created_through_by: Optional[User] = kante.django_field(description="The assigner of the creating task, if any")
    rgb_contexts: List["RGBContext"] = kante.django_field(description="RGB rendering contexts")
    derived_scale_views: List["ScaleView"] = kante.django_field(description="Scale views derived from this image")
    derived_views: List["DerivedView"] = kante.django_field(description="Views derived from this image")
    derived_instance_mask_views: List["InstanceMaskView"] = kante.django_field(description="Instance mask views")
    roi_views: List["ROIView"] = kante.django_field(description="Region of interest views")
    file_views: List["FileView"] = kante.django_field(description="File views relating to source files")
    derived_from_views: List["DerivedView"] = kante.django_field(description="Views this image was derived from")
    lightpath_views: List["LightpathView"] = kante.django_field(description="Lightpath views describing the lightpath used to acquire this image")

    @kante.django_field(description="The channels of this image")
    def channels(self, info: Info) -> List["ChannelInfo"]:
        return [ChannelInfo(_image=self, _channel=i) for i in range(0, self.store.shape[0])]

    @kante.django_field(description="The channels of this image")
    def frames(self, info: Info) -> List["FrameInfo"]:
        return [FrameInfo(_image=self, _frame=i) for i in range(0, self.store.shape[1])]

    @kante.django_field(description="The channels of this image")
    def planes(self, info: Info) -> List["PlaneInfo"]:
        return [PlaneInfo(_image=self, _plane=i) for i in range(0, self.store.shape[2])]

    @kante.django_field(description="The latest snapshot of this image")
    def latest_snapshot(self, info: Info) -> Optional["Snapshot"]:
        return cast(models.Image, self).snapshots.order_by("-created_at").first()

    @kante.django_field(description="Is this image pinned by the current user")
    def pinned(self, info: Info) -> bool:
        return cast(models.Image, self).pinned_by.filter(id=info.context.request.user.id).exists()

    @kante.django_field(description="The tags of this image")
    def tags(self, info: Info) -> list[str]:
        return cast(models.Image, self).tags.slugs()

    @kante.django_field(description="All views of this image")
    def views(
        self,
        info: Info,
        filters: Annotated[
            filters.ViewFilter | None,
            strawberry.argument(description="A filter to selected the subset of views"),
        ] = strawberry.UNSET,
        types: List[ViewKind] | None = strawberry.UNSET,
    ) -> List["View"]:
        if types is strawberry.UNSET:
            view_relations = IMAGE_VIEW_RELATIONS
        else:
            view_relations = [kind.value for kind in types]

        results = []

        for relation in view_relations:
            qs = getattr(self, relation).all()

            # apply filters if defined
            if filters is not strawberry.UNSET:
                qs = strawberry_django.filters.apply(filters, qs, info)

            results.append(qs)

        return list(chain(*results))

    @kante.django_field()
    def renders(
        self,
        info: Info,
        filters: filters.ViewFilter | None = strawberry.UNSET,
        types: List[RenderKind] | None = strawberry.UNSET,
    ) -> List["Render"]:
        if types is strawberry.UNSET:
            view_relations = IMAGE_RENDER_RELATIONS
        else:
            view_relations = [kind.value for kind in types]

        results = []

        for relation in view_relations:
            qs = getattr(self, relation).all()

            # apply filters if defined
            if filters is not strawberry.UNSET:
                qs = strawberry_django.filters.apply(filters, qs, info)

            results.append(qs)

        return list(chain(*results))

    @kante.django_field()
    def rois(
        self,
        info: Info,
        filters: filters.ROIFilter | None = strawberry.UNSET,
    ) -> List["ROI"]:
        qs = self.rois.all()

        # apply filters if defined
        if filters is not strawberry.UNSET:
            qs = strawberry_django.filters.apply(filters, qs, info)

        return qs

    @classmethod
    def resolve_reference(cls, info: Info, id: strawberry.ID) -> "Image":
        """Resolve an image by its ID."""
        logger.debug(f"Resolving image with ID: {info}")
        try:
            return models.Image.objects.aget(id=id)
        except models.Image.DoesNotExist:
            raise ValueError(f"Image with ID {id} does not exist.")

    @classmethod
    def get_queryset(cls, queryset, info, **kwargs):
        return build_prescoped_queryset(info, queryset)


ImageStats, ImageStatsResolver = create_stats_type(models.Image, allowed_fields={"pk": "id"}, allowed_datetime_fields={"created_at": "created_at"}, filters=filters.ImageFilter)


@kante.django_type(models.Dataset, filters=filters.DatasetFilter, ordering=order.DatasetOrder, pagination=True, description="A dataset is a collection of images and files. It mimics the concept of a folder in a file system and is the top-level container for organising data in mikro.")
class Dataset:
    id: auto
    images: List["Image"]
    files: List["File"]
    parent: Optional["Dataset"]
    children: List["Dataset"]
    description: str | None
    name: str
    provenance_entries: List["ProvenanceEntry"] = kante.django_field(description="Provenance entries for this dataset")
    is_default: bool
    created_at: datetime.datetime
    creator: User | None
    created_through: Optional[Task] = kante.django_field(description="The task this dataset was created through, if any")
    created_through_by: Optional[User] = kante.django_field(description="The assigner of the creating task, if any")

    @kante.django_field()
    def pinned(self, info: Info) -> bool:
        return cast(models.Dataset, self).pinned_by.filter(id=info.context.request.user.id).exists()

    @kante.django_field()
    def tags(self, info: Info) -> list[str]:
        return cast(models.Image, self).tags.slugs()


OtherItem = Annotated[Union[Dataset, Image], strawberry.union("OtherItem")]


def min_max_to_accessor(min, max):
    if min is None:
        min = ""
    if max is None:
        max = ""
    return f"{min}:{max}"


@kante.django_interface(models.View, description="A view is a subset of an image, delimited by its coordinates (c, t, z, x, y) within the 5D array. Views attach metadata (channels, labels, transformations, timepoints, ...) to that subregion of the image.")
class View:
    """A view is a subset of an image."""

    image: "Image"
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
    is_global: bool

    @kante.django_field(description="The accessor")
    def accessor(self) -> List[str]:
        z_accessor = min_max_to_accessor(self.z_min, self.z_max)
        t_accessor = min_max_to_accessor(self.t_min, self.t_max)
        c_accessor = min_max_to_accessor(self.c_min, self.c_max)
        x_accessor = min_max_to_accessor(self.x_min, self.x_max)
        y_accessor = min_max_to_accessor(self.y_min, self.y_max)

        return [c_accessor, t_accessor, z_accessor, x_accessor, y_accessor]

    @kante.django_field(description="All views of this image")
    def congruent_views(
        self,
        info: Info,
        filters: Annotated[
            filters.ViewFilter | None,
            strawberry.argument(description="A filter to selected the subset of views"),
        ] = strawberry.UNSET,
        types: List[ViewKind] | None = strawberry.UNSET,
    ) -> List["View"]:
        image = self.image

        if types is strawberry.UNSET:
            view_relations = IMAGE_VIEW_RELATIONS
        else:
            view_relations = [kind.value for kind in types]

        results = []

        for relation in view_relations:
            logger.debug("Searching congruent views for %s", relation)
            qs = getattr(image, relation).filter(c_min=self.c_min, c_max=self.c_max, t_min=self.t_min, t_max=self.t_max, z_min=self.z_min, z_max=self.z_max, x_min=self.x_min, x_max=self.x_max, y_min=self.y_min, y_max=self.y_max).all()

            # apply filters if defined
            if filters is not strawberry.UNSET:
                qs = strawberry_django.filters.apply(filters, qs, info)

            results.append(qs)

        return list(chain(*results))


@kante.django_interface(models.Accessor, description="An accessor declares how the values of specific columns (keys) of a table should be interpreted, e.g. as pixel labels of a mask or as ids of images.")
class Accessor:
    id: strawberry.ID
    table: Table
    keys: list[str]
    min_index: int | None
    max_index: int | None


@kante.django_type(models.LabelAccessor, description="A label accessor declares that the values of its table columns are pixel values of an associated mask view, allowing clients to join table rows to mask labels.")
class LabelAccessor(Accessor):
    id: auto
    mask_view: "MaskView"


@kante.django_type(models.ImageAccessor, description="An image accessor declares that the values of its table columns are ids of associated images, allowing clients to resolve table rows to images.")
class ImageAccessor(Accessor):
    id: auto
    pass


@kante.django_type(models.ChannelView, description="A channel view describes an acquisition channel of an image, carrying its name and optical properties such as emission and excitation wavelengths.")
class ChannelView(View):
    id: auto
    name: str | None = kante.django_field(description="The name of the channel ")
    emission_wavelength: float | None = kante.django_field(description="The emission wavelength of the channel in nanometers")
    excitation_wavelength: float | None = kante.django_field(description="The excitation wavelength of the channel in nanometers")
    acquisition_mode: str | None = kante.django_field(description="The acquisition mode of the channel")


@kante.django_type(models.RGBRenderContext, filters=filters.RGBContextFilter, ordering=order.RGBContextOrder, pagination=True, description="An RGB context is a collection of RGB views that together describe how an image should be rendered in RGB, e.g. grouping the views that represent each channel with its color map and contrast settings.")
class RGBContext:
    id: auto
    name: str
    image: Image
    snapshots: List[Snapshot]
    blending: enums.Blending
    z: int
    t: int
    c: int

    @kante.django_field()
    def pinned(self, info: Info) -> bool:
        return cast(models.RGBRenderContext, self).pinned_by.filter(id=info.context.request.user.id).exists()

    @kante.django_field()
    def views(self, info: Info) -> List["RGBView"]:
        return self.views.order_by("c_min").all()


@kante.django_type(
    models.RenderTree,
    filters=filters.RenderTreeFilter,
    ordering=order.RenderTreeOrder,
    pagination=True,
    description="A render tree is a tree structure that describes the rendering of multiple images together, by linking several RGB contexts into one composite visualization.",
)
class RenderTree:
    id: auto
    name: str
    linked_contexts: list[RGBContext]


@kante.django_type(models.RGBView, filters=filters.RGBViewFilter, pagination=True, description="An RGB view describes how a subset of an image (typically a channel) is rendered in RGB within an RGB context, carrying color map, gamma and contrast limit settings.")
class RGBView(View):
    id: auto
    contexts: List[RGBContext]
    color_map: enums.ColorMap
    gamma: float | None
    contrast_limit_min: float | None
    contrast_limit_max: float | None
    active: bool
    base_color: list[int] | None

    @kante.django_field()
    def full_colour(self, info: Info, format: enums.ColorFormat | None = enums.ColorFormat.RGB) -> str:
        if format is None:
            format = enums.ColorFormat.RGB

        if format == enums.ColorFormat.RGB:
            if self.color_map == enums.ColorMap.RED:
                return "rgb(255,0,0)"
            if self.color_map == enums.ColorMap.GREEN:
                return "rgb(0,255,0)"
            if self.color_map == enums.ColorMap.BLUE:
                return "rgb(0,0,255)"

        return ""

    @kante.django_field()
    def name(self, info: Info, long: bool = False) -> str:
        if long:
            return f"{self.color_map} {self.gamma} {self.contrast_limit_min} {self.contrast_limit_max} {self.rescale}"
        return f"{self.color_map} ({self.c_min}:{self.c_max})"


@kante.django_type(models.LabelView, description="A label view gives a label to a specific image channel, e.g. mapping an antibody to the channel it stains, so the labeling agent can be easily identified. Labels can also be used for other purposes, such as marking a channel as poor quality.")
class LabelView(View):
    """A label view.

    Label views are used to give a label to a specific image channel. For example, you can
    create a label view that maps an antibody to a specific image channel. This will allow
    you to easily identify the labeling agent in the image. However, label views can be used
    for other purposes as well. For example, you can use a label to mark a specific channel
    to be of poor quality. (e.g. "bad channel").

    """

    id: auto

    image: Image

    @kante.django_field()
    def label(self, info: Info) -> str:
        return self.label or "No Label"


@kante.django_type(models.ROIView, description="A ROI view establishes a relationship between an image region and a region of interest, e.g. recording that this image was cropped from the area described by the ROI on another image.")
class ROIView(View):
    """A label view.

    Label views are used to give a label to a specific image channel. For example, you can
    create a label view that maps an antibody to a specific image channel. This will allow
    you to easily identify the labeling agent in the image. However, label views can be used
    for other purposes as well. For example, you can use a label to mark a specific channel
    to be of poor quality. (e.g. "bad channel").

    """

    id: auto

    image: Image
    roi: "ROI"


@kante.django_type(
    models.FileView,
    pagination=True,
    filters=filters.FileViewFilter,
    ordering=order.FileViewOrder,
    description="A file view establishes a relationship between an image and a file: it records that this view of the image was originally part of the file (optionally a specific series within it) and links back to the source file.",
)
class FileView(View):
    """A file view.

    File view establish a relationship between an image and a file. It is used to establish
    the this view of the image was originally part of a file, and to provide a link to the
    file that was used to create the image.

    Related Concepts:
        - TableViews: Table views establish a relationship between a table and an image. (i.e. when a table is generated from an image)

    """

    id: auto
    series_identifier: str | None = None
    image: Image
    file: "File"


@kante.django_type(models.HistogramView, description="A histogram view describes the distribution of pixel values in a subset of an image, providing bins, min/max bounds and the histogram counts. Useful for clients that want to display or auto-scale contrast.")
class HistogramView(View):
    """A file view.

    File view establish a relationship between an image and a file. It is used to establish
    the this view of the image was originally part of a file, and to provide a link to the
    file that was used to create the image.

    Related Concepts:
        - TableViews: Table views establish a relationship between a table and an image. (i.e. when a table is generated from an image)

    """

    id: auto
    image: Image
    bins: list[float]
    min: float
    max: float
    histogram: list[float]


@kante.django_type(models.DerivedView, description="A derived view establishes a processing relationship between two images, guaranteeing that the derived image shares the same coordinate system as its origin image so the two can be trivially overlayed and compared (e.g. a segmentation over its source image). Cropped or projected images are not derived views, as they do not share the coordinate system.")
class DerivedView(View):
    """A  derived view.

    Derived views establish a processing relationship between two images. Within this relationship
    it is guarenteed that the derived view is derived from the origin image and shares the same
    coordinate system. This means that images can be trivially overlayed and compared.

    Attention:
    Importantly cropped or projected images are not derived views, as they do not share the same coordinate system.
    This means that cropped images cannot be trivially overlayed and compared, for this you would need to create a
    ROIView (mapping the cropped area or projected area to the original image).


    Biological Example:
        I.e. if you have a derived view that is a segmentation of an image, you can overlay the segmentation
        on the original image and compare the two. This is useful to validate the segmentation.

    Related Concepts:
        - RoiViews: RoiViews allow to establish a relationship between a region of interest and an image. (i.e when cropping an image)


    """

    id: auto
    image: Image
    origin_image: Image
    operation: str | None = None


@kante.django_type(models.TableView, description="A table view establishes that an image was generated from a table, e.g. an image reconstructed from a table of SMLM localisations, providing a backlink from the image to its source table.")
class TableView(View):
    """A  table view.

    A table view established that an image was generated from a table.


    Biological Example:
        -   You have a table that describes the localisations in Single Molecule Localization Microscopy (SMLM) data.
            You can establish a backlink from the image to the table to show that the image was generated from this table





    """

    id: auto
    image: Image
    table: Table
    operation: str | None = None


@kante.django_type(models.ScaleView, description="A view linking an image to a downscaled version of another image. Scale views form the levels of a multiscale pyramid: the parent is the full-resolution image and the scale factors give the downsampling per dimension.")
class ScaleView(View):
    """A view linking an image to a downscaled version of another image.

    Scale views form the levels of a multiscale pyramid: the parent is the
    full-resolution image and the scale factors give the downsampling per
    dimension.
    """

    id: auto
    parent: "Image"
    scale_x: float
    scale_y: float
    scale_z: float
    scale_t: float
    scale_c: float


@kante.django_type(models.AcquisitionView, description="A view recording when and by whom an image region was acquired at the microscope. Use it to trace an image back to its acquisition session and operator.")
class AcquisitionView(View):
    """A view recording when and by whom an image region was acquired at the microscope.

    Use it to trace an image back to its acquisition session and operator.
    """

    id: auto
    description: str | None
    acquired_at: datetime.datetime | None
    operator: User | None


@kante.django_type(models.OpticsView, filters=filters.OpticsViewFilter, pagination=True, description="A view describing the optics used to acquire an image region: the instrument, objective and camera. Use it to inspect or compare acquisition hardware settings.")
class OpticsView(View):
    """An optics view.

    Optics views describe the optics that were used to acquire the image. This includes
    the camera, the objective, and the instrument that were used to acquire the image.
    Often optics views are used to describe the acquisition settings of the image.

    """

    id: auto
    instrument: Instrument | None
    camera: Camera | None
    objective: Objective | None


@kante.django_type(models.LightpathView, filters=filters.OpticsViewFilter, pagination=True, description="A view attaching the optical path (light sources, filters, detectors and their connections) that light travelled through when this image region was acquired.")
class LightpathView(View):
    """A view attaching the optical path that light travelled through when this image region was acquired.

    The graph describes light sources, filters, detectors and their connections.
    """

    id: auto

    @kante.django_field(description="The lightpath graph describing the lightpath used to acquire this image")
    def graph(self, info: Info) -> LightpathGraph:
        t = LightpathGraphModel(**self.graph)
        return t


@kante.django_type(models.WellPositionView, filters=filters.WellPositionViewFilter, pagination=True, description="A view mapping an image region to a well (row/column) of a multi well plate, so plate-based acquisitions can be traced back to their well.")
class WellPositionView(View):
    """A well position view.

    Well position views are used to map the well position of a multi well plate to the
    image. This is useful if you are using a multi well plate to acquire images and you
    want to map the well position to the image data. This can be useful to track the
    position of the image data in the multi well plate.

    """

    id: auto
    well: MultiWellPlate | None
    row: int | None
    column: int | None


@kante.django_type(models.ContinousScanView, filters=filters.ContinousScanViewFilter, pagination=True, description="A view marking an image region as acquired by a continuous scan, recording the direction the scan traversed the axes in.")
class ContinousScanView(View):
    """A view marking an image region as acquired by a continuous scan, recording the scan direction."""

    id: auto
    direction: enums.ScanDirection


@kante.django_type(models.ReferenceView, filters=filters.ReferenceViewFilter, pagination=True, description="A view marking an image region as the reference that other views (e.g. mask views) point back to, for example the raw channel a segmentation mask was computed from.")
class ReferenceView(View):
    """A reference view.

    Reference views are used to map a view to a reference image. This is useful if you
    want to compare the view to a reference image. For example, you can use a reference
    view to compare a label view to a reference image of the same channel.

    """

    id: auto
    image: Image

    def referenced_by_views(self, info: Info) -> List[View]:
        """Get all views that reference this view."""
        return cast(models.ReferenceView, self).referenced_by_views.all()


@kante.django_type(models.MaskView, filters=filters.MaskViewFilter, pagination=True, description="A view marking an image region as a semantic segmentation mask, where pixel values are class labels. It points to the reference view it was computed from and can carry a label table.")
class MaskView(View):
    """A view marking an image region as a semantic segmentation mask (pixel values are class labels).

    It points to the reference view it was computed from and can carry a label table.
    """

    id: auto
    image: Image
    reference_view: ReferenceView
    labels: ParquetStore | None


@kante.django_type(models.InstanceMaskView, filters=filters.InstanceMaskViewFilter, pagination=True, description="A view marking an image region as an instance segmentation mask, where each pixel value identifies an individual object instance. It points to the reference view it was computed from and can carry a per-instance label table.")
class InstanceMaskView(View):
    """A view marking an image region as an instance segmentation mask (each pixel value identifies one object instance).

    It points to the reference view it was computed from and can carry a per-instance label table.
    """

    id: auto
    image: Image
    reference_view: ReferenceView
    labels: ParquetStore | None
    operation: str | None = None


@kante.django_type(models.TimepointView, filters=filters.TimepointViewFilter, pagination=True, description="A view anchoring an image region in real time: it places the region within an era (a named time epoch on the microscope) at a millisecond offset or frame index since its start.")
class TimepointView(View):
    """A view anchoring an image region in real time.

    It places the region within an era (a named time epoch on the microscope)
    at a millisecond offset or frame index since its start.
    """

    id: auto
    era: Era
    ms_since_start: scalars.Milliseconds | None
    index_since_start: int | None


@kante.django_type(
    models.AffineTransformationView,
    filters=filters.AffineTransformationViewFilter,
    pagination=True,
    description="A view placing an image region in physical space: a 4x4 affine matrix maps pixel coordinates onto a stage, encoding position and pixel size.",
)
class AffineTransformationView(View):
    """A view placing an image region in physical space.

    The 4x4 affine matrix maps pixel coordinates onto a stage, encoding
    position and pixel size.
    """

    id: auto
    stage: Stage
    affine_matrix: scalars.FourByFourMatrix

    @kante.django_field()
    def pixel_size(self, info: Info) -> scalars.ThreeDVector:
        if self.affine_matrix:
            return [self.affine_matrix[0][0], self.affine_matrix[1][1], self.affine_matrix[2][2]]
        raise NotImplementedError("Only affine transformations are supported")

    @kante.django_field()
    def pixel_size_x(self, info: Info) -> scalars.Micrometers:
        if self.affine_matrix:
            return self.affine_matrix[0][0]
        raise NotImplementedError("Only affine transformations are supported")

    @kante.django_field()
    def isotropic(self, info: Info) -> bool:
        """Check if the pixel size is isotropic."""
        if self.affine_matrix:
            return self.affine_matrix[0][0] == self.affine_matrix[1][1] == self.affine_matrix[2][2]
        raise NotImplementedError("Only affine transformations are supported")

    @kante.django_field()
    def pixel_size_z(self, info: Info) -> scalars.Micrometers:
        if self.affine_matrix:
            return self.affine_matrix[2][2]
        raise NotImplementedError("Only affine transformations are supported")

    @kante.django_field()
    def pixel_size_y(self, info: Info) -> scalars.Micrometers:
        if self.affine_matrix:
            return self.affine_matrix[1][1]
        raise NotImplementedError("Only affine transformations are supported")

    @kante.django_field()
    def position(self, info: Info) -> scalars.ThreeDVector:
        if self.affine_matrix:
            return [self.affine_matrix[0][3], self.affine_matrix[1][3], self.affine_matrix[2][3]]
        raise NotImplementedError("Only affine transformations are supported")


@kante.django_type(models.ROI, filters=filters.ROIFilter, ordering=order.ROIOrder, pagination=True, description="A region of interest drawn on an image, defined by a list of 5D vectors (c, t, z, y, x) and a kind (rectangle, path, point, ...). Use ROIs to mark and share structures of interest.")
class ROI:
    """A region of interest drawn on an image.

    Defined by a list of 5D vectors (c, t, z, y, x) and a kind (rectangle,
    path, point, ...). Use ROIs to mark and share structures of interest.
    """

    id: auto
    image: "Image"
    kind: enums.RoiKind
    vectors: list[scalars.FiveDVector]
    created_at: datetime.datetime
    creator: User | None
    created_through: Optional[Task] = kante.django_field(description="The task this ROI was created through, if any")
    created_through_by: Optional[User] = kante.django_field(description="The assigner of the creating task, if any")
    provenance_entries: List["ProvenanceEntry"] = kante.django_field(description="Provenance entries for this ROI")

    @kante.django_field()
    def pinned(self, info: Info) -> bool:
        return self.pinned_by.filter(id=info.context.request.user.id).exists()

    @kante.django_field()
    def name(self, info: Info) -> str:
        return self.kind


@strawberry.type(description="Display information for one pixel value of a mask: the label it represents and the color it is rendered with.")
class MaskedPixelInfo:
    """Display information for one pixel value of a mask: its label and render color."""

    label: str
    color: str


@strawberry.type(description="One labelled instance of an instance mask: the row of the mask's label table describing a single segmented object.")
class InstanceMaskViewLabel:
    """One labelled instance of an instance mask (a row of the mask's label table)."""

    _id: strawberry.Private[str]
    _mask: strawberry.Private[str]
    _store: strawberry.Private[ParquetStore]
    _values: strawberry.Private[Dict[str, Any]]

    @kante.django_field()
    def mask(self, info: Info) -> InstanceMaskView:
        return models.InstanceMaskView.objects.get(id=self._mask)

    @kante.django_field()
    def values(self, info: Info) -> scalars.Any:
        return self._values

    @kante.field()
    def id(self) -> str:
        return self._id
