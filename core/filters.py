import datetime
import strawberry
from core import models, enums
from koherent.models import Task as KoherentTask
from strawberry import auto
from typing import Optional
from strawberry_django.filters import FilterLookup
from kante.types import Info
from django.db.models import Q, QuerySet
import kante


@strawberry.input
class ChannelInfoFilter:
    search: Optional[str] = None
    ids: Optional[list[strawberry.ID]] = None


@strawberry.input
class DatasetChildrenFilter:
    show_children: bool | None = None
    search: str | None = None


@strawberry.input
class RowFilter:
    clause: str | None = None


@strawberry.input
class TableRowFilter:
    search: str | None = None
    ids: list[strawberry.ID] | None = None


@strawberry.input
class TableCellFilter:
    search: str | None = None
    ids: list[strawberry.ID] | None = None


# Mixins: reusable filter fields shared across filter types. All methods are
# prefix-aware so they compose correctly when the filter is nested inside
# another filter (the prefix carries the relation path).


@strawberry.input
class IdsFilterMixin:
    @kante.filter_field(description="Filter by list of IDs")
    def ids(self, info: Info, value: list[strawberry.ID], prefix: str) -> Q:
        return Q(**{f"{prefix}id__in": value})


@strawberry.input
class SearchFilterMixin:
    @kante.filter_field(description="Search by name (full-text search)")
    def search(self, info: Info, value: str, prefix: str) -> Q:
        return Q(**{f"{prefix}name__search": value})


@strawberry.input
class NameSearchFilterMixin:
    @kante.filter_field(description="Search by name (case-insensitive substring)")
    def search(self, info: Info, value: str, prefix: str) -> Q:
        return Q(**{f"{prefix}name__icontains": value})


@strawberry.input
class CreatedAtFilterMixin:
    @kante.filter_field(description="Filter for items created before this datetime")
    def created_before(self, info: Info, value: datetime.datetime, prefix: str) -> Q:
        return Q(**{f"{prefix}created_at__lt": value})

    @kante.filter_field(description="Filter for items created after this datetime")
    def created_after(self, info: Info, value: datetime.datetime, prefix: str) -> Q:
        return Q(**{f"{prefix}created_at__gt": value})


@strawberry.input
class OwnedFilterMixin(CreatedAtFilterMixin):
    @kante.filter_field(description="Filter by the creator's subject ID")
    def owner(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}creator__sub": value})


@strawberry.input
class PinnedFilterMixin:
    @kante.filter_field(description="Filter by whether the current user has pinned the item")
    def pinned(self, info: Info, value: bool, prefix: str) -> Q:
        if value:
            return Q(**{f"{prefix}pinned_by": info.context.request.user})
        return ~Q(**{f"{prefix}pinned_by": info.context.request.user})


@strawberry.input
class TagsFilterMixin:
    @kante.filter_field(description="Filter by tag names")
    def tags(self, info: Info, queryset: QuerySet, value: list[str], prefix: str) -> tuple[QuerySet, Q]:
        # Multiple matching tags would duplicate rows on the join.
        return queryset.distinct(), Q(**{f"{prefix}tags__name__in": value})


@strawberry.input
class ScopeFilterMixin:
    @kante.filter_field(description="Filter by visibility scope")
    def scope(self, info: Info, value: enums.ScopeKind, prefix: str) -> Q:
        if value == enums.ScopeKind.ORG:
            return Q(**{f"{prefix}organization": info.context.request.organization})
        if value == enums.ScopeKind.ME:
            return Q(**{f"{prefix}creator": info.context.request.user})
        raise NotImplementedError(f"Scope filtering for {value} is not implemented")


@strawberry.input
class CreatedThroughFilterMixin:
    @kante.filter_field(description="Filter by the rekuest task id the item was created through")
    def created_through_task(self, info: Info, value: str, prefix: str) -> Q:
        return Q(**{f"{prefix}created_through__task_id": value})

    @kante.filter_field(description="Filter by the sub of the user that assigned the creating task")
    def assigned_by(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        # Hits the denormalized FK on the model itself; the join through the
        # (very large) task table would scale with the user's task count.
        return Q(**{f"{prefix}created_through_by__sub": value})


@strawberry.input
class ImageViewFilterMixin:
    """Shared filters for all View subtypes (everything hanging off an image)."""

    is_global: Optional[bool]

    @kante.filter_field(description="Filter by the image this view belongs to")
    def image(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}image_id": value})

    @kante.filter_field(description="Filter by a list of images this view belongs to")
    def images(self, info: Info, value: list[strawberry.ID], prefix: str) -> Q:
        return Q(**{f"{prefix}image_id__in": value})

    @kante.filter_field(description="Search by the name of the image this view belongs to")
    def search(self, info: Info, value: str, prefix: str) -> Q:
        return Q(**{f"{prefix}image__name__icontains": value})


# Store filters


@kante.filter_type(models.ZarrStore)
class ZarrStoreFilter:
    shape: Optional[FilterLookup[int]]


# Hardware / acquisition context filters


@kante.filter_type(models.Instrument)
class InstrumentFilter(IdsFilterMixin, NameSearchFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]
    manufacturer: Optional[FilterLookup[str]]
    model: Optional[FilterLookup[str]]
    serial_number: Optional[FilterLookup[str]]


@kante.filter_type(models.Objective)
class ObjectiveFilter(IdsFilterMixin, NameSearchFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]
    serial_number: Optional[FilterLookup[str]]
    magnification: Optional[FilterLookup[float]]
    na: Optional[FilterLookup[float]]
    immersion: Optional[FilterLookup[str]]


@kante.filter_type(models.Camera)
class CameraFilter(IdsFilterMixin, NameSearchFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]
    serial_number: Optional[FilterLookup[str]]
    model: Optional[FilterLookup[str]]
    manufacturer: Optional[FilterLookup[str]]
    bit_depth: Optional[FilterLookup[int]]


@kante.filter_type(models.Stage)
class StageFilter(IdsFilterMixin, NameSearchFilterMixin, OwnedFilterMixin, PinnedFilterMixin, CreatedThroughFilterMixin):
    id: auto
    kind: auto
    name: Optional[FilterLookup[str]]

    @kante.filter_field(description="Filter by the instrument this stage belongs to")
    def instrument(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}instrument_id": value})


@kante.filter_type(models.Era)
class EraFilter(IdsFilterMixin, NameSearchFilterMixin, OwnedFilterMixin, PinnedFilterMixin, CreatedThroughFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]
    begin: auto
    end: auto

    @kante.filter_field(description="Filter by the instrument this era belongs to")
    def instrument(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}instrument_id": value})


@kante.filter_type(models.MultiWellPlate)
class MultiWellPlateFilter(IdsFilterMixin, NameSearchFilterMixin, PinnedFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]
    description: Optional[FilterLookup[str]]
    rows: Optional[FilterLookup[int]]
    columns: Optional[FilterLookup[int]]


# Dataset filter (needed by ImageFilter/FileFilter as a nested filter)


@kante.filter_type(models.Dataset)
class DatasetFilter(IdsFilterMixin, SearchFilterMixin, OwnedFilterMixin, ScopeFilterMixin, PinnedFilterMixin, TagsFilterMixin, CreatedThroughFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]
    description: Optional[FilterLookup[str]]
    is_default: Optional[bool]

    @kante.filter_field(description="Filter for datasets with (true) or without (false) a parent")
    def parentless(self, info: Info, value: bool, prefix: str) -> Q:
        if value:
            return Q(**{f"{prefix}parent": None})
        return ~Q(**{f"{prefix}parent": None})


# View filters


@kante.filter_type(models.ViewCollection)
class ViewCollectionFilter(IdsFilterMixin, NameSearchFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]


@kante.filter_type(models.View)
class ViewFilter(IdsFilterMixin):
    is_global: Optional[bool]


@kante.filter_type(models.AffineTransformationView)
class AffineTransformationViewFilter(IdsFilterMixin, ImageViewFilterMixin):
    id: auto
    stage: Optional[StageFilter]


@kante.filter_type(models.TimepointView)
class TimepointViewFilter(IdsFilterMixin, ImageViewFilterMixin):
    id: auto
    era: Optional[EraFilter]
    ms_since_start: auto
    index_since_start: auto


@kante.filter_type(models.OpticsView)
class OpticsViewFilter(IdsFilterMixin, ImageViewFilterMixin):
    id: auto
    instrument: Optional[InstrumentFilter]
    objective: Optional[ObjectiveFilter]
    camera: Optional[CameraFilter]


@kante.filter_type(models.WellPositionView)
class WellPositionViewFilter(IdsFilterMixin, ImageViewFilterMixin):
    id: auto
    well: Optional[MultiWellPlateFilter]
    row: Optional[int]
    column: Optional[int]


@kante.filter_type(models.ContinousScanView)
class ContinousScanViewFilter(IdsFilterMixin, ImageViewFilterMixin):
    id: auto
    direction: auto


@kante.filter_type(models.MaskView)
class MaskViewFilter(IdsFilterMixin, ImageViewFilterMixin):
    id: auto

    @kante.filter_field(description="Filter by the reference view this mask refers to")
    def reference_view(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}reference_view_id": value})


@kante.filter_type(models.InstanceMaskView)
class InstanceMaskViewFilter(IdsFilterMixin, ImageViewFilterMixin):
    id: auto

    @kante.filter_field(description="Filter by the reference view this mask refers to")
    def reference_view(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}reference_view_id": value})


@kante.filter_type(models.ReferenceView)
class ReferenceViewFilter(IdsFilterMixin, ImageViewFilterMixin):
    id: auto


@kante.filter_type(models.RGBView)
class RGBViewFilter(IdsFilterMixin, ImageViewFilterMixin):
    id: auto
    color_map: auto
    active: Optional[bool]

    @kante.filter_field(description="Filter by the RGB contexts this view belongs to")
    def contexts(self, info: Info, queryset: QuerySet, value: list[strawberry.ID], prefix: str) -> tuple[QuerySet, Q]:
        # M2M join can duplicate rows when a view is in several matching contexts.
        return queryset.distinct(), Q(**{f"{prefix}contexts__id__in": value})


@kante.filter_type(models.FileView)
class FileViewFilter(IdsFilterMixin, ImageViewFilterMixin):
    id: auto
    series_identifier: Optional[FilterLookup[str]]

    @kante.filter_field(description="Filter by the file this view belongs to")
    def file(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}file": value})


# Core data filters


@kante.filter_type(models.Image)
class ImageFilter(IdsFilterMixin, SearchFilterMixin, OwnedFilterMixin, ScopeFilterMixin, PinnedFilterMixin, TagsFilterMixin, CreatedThroughFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]
    description: Optional[FilterLookup[str]]
    kind: auto
    store: Optional[ZarrStoreFilter]
    dataset: Optional[DatasetFilter]
    transformation_views: Optional[AffineTransformationViewFilter]
    timepoint_views: Optional[TimepointViewFilter]

    @kante.filter_field(description="Filter by a list of dataset IDs")
    def datasets(self, info: Info, value: list[strawberry.ID], prefix: str) -> Q:
        return Q(**{f"{prefix}dataset_id__in": value})

    @kante.filter_field(description="Filter for images that are not derived from another image")
    def not_derived(self, info: Info, value: bool, prefix: str) -> Q:
        underived = Q(**{f"{prefix}derived_views": None}) & Q(**{f"{prefix}scale_views": None})
        return underived if value else ~underived

    @kante.filter_field(description="Filter for images that have (or have no) ROIs")
    def has_rois(self, info: Info, queryset: QuerySet, value: bool, prefix: str) -> tuple[QuerySet, Q]:
        if value:
            return queryset.distinct(), Q(**{f"{prefix}rois__isnull": False})
        return queryset, Q(**{f"{prefix}rois__isnull": True})


@kante.filter_type(models.File)
class FileFilter(IdsFilterMixin, NameSearchFilterMixin, OwnedFilterMixin, ScopeFilterMixin, CreatedThroughFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]
    size: Optional[FilterLookup[int]]
    content_type: Optional[FilterLookup[str]]

    @kante.filter_field(description="Filter by the dataset this file belongs to")
    def dataset(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}dataset_id": value})

    @kante.filter_field(description="Filter by a list of dataset IDs")
    def datasets(self, info: Info, value: list[strawberry.ID], prefix: str) -> Q:
        return Q(**{f"{prefix}dataset_id__in": value})

    @kante.filter_field(description="Filter for files that are not derived from another file")
    def not_derived(self, info: Info, value: bool, prefix: str) -> Q:
        underived = Q(**{f"{prefix}origins": None})
        return underived if value else ~underived


@kante.filter_type(models.Table)
class TableFilter(IdsFilterMixin, SearchFilterMixin, OwnedFilterMixin, CreatedThroughFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]

    @kante.filter_field(description="Filter by the dataset this table belongs to")
    def dataset(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}dataset_id": value})

    @kante.filter_field(description="Filter for tables that are not derived from another table")
    def not_derived(self, info: Info, value: bool, prefix: str) -> Q:
        underived = Q(**{f"{prefix}origins": None})
        return underived if value else ~underived


@kante.filter_type(models.Mesh)
class MeshFilter(IdsFilterMixin, NameSearchFilterMixin, CreatedAtFilterMixin, PinnedFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]

    @kante.filter_field(description="Filter by the dataset this mesh belongs to")
    def dataset(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}dataset_id": value})


@kante.filter_type(models.Snapshot)
class SnapshotFilter(IdsFilterMixin, NameSearchFilterMixin, OwnedFilterMixin, CreatedThroughFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]

    @kante.filter_field(description="Filter by the image this snapshot renders")
    def image(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}image_id": value})

    @kante.filter_field(description="Filter by the RGB context this snapshot was rendered with")
    def context(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}context_id": value})


@kante.filter_type(models.ROI)
class ROIFilter(IdsFilterMixin, OwnedFilterMixin, PinnedFilterMixin, CreatedThroughFilterMixin):
    id: auto
    kind: auto
    label: Optional[FilterLookup[str]]
    min_x: Optional[FilterLookup[int]]
    max_x: Optional[FilterLookup[int]]
    min_y: Optional[FilterLookup[int]]
    max_y: Optional[FilterLookup[int]]
    min_z: Optional[FilterLookup[int]]
    max_z: Optional[FilterLookup[int]]
    min_t: Optional[FilterLookup[int]]
    max_t: Optional[FilterLookup[int]]

    @kante.filter_field(description="Filter by the image this ROI was drawn on")
    def image(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}image_id": value})

    @kante.filter_field(description="Filter by a list of images this ROI was drawn on")
    def images(self, info: Info, value: list[strawberry.ID], prefix: str) -> Q:
        return Q(**{f"{prefix}image_id__in": value})

    @kante.filter_field(description="Filter by the group this ROI belongs to")
    def group(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}group_id": value})

    @kante.filter_field(description="Search by the name of the image this ROI was drawn on")
    def search(self, info: Info, value: str, prefix: str) -> Q:
        return Q(**{f"{prefix}image__name__icontains": value})


@kante.filter_type(models.Experiment)
class ExperimentFilter(IdsFilterMixin, NameSearchFilterMixin, CreatedAtFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]
    description: Optional[FilterLookup[str]]


@kante.filter_type(models.RGBRenderContext)
class RGBContextFilter(IdsFilterMixin, NameSearchFilterMixin, PinnedFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]
    blending: auto

    @kante.filter_field(description="Filter by the image this context renders")
    def image(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}image_id": value})


@kante.filter_type(models.RenderTree)
class RenderTreeFilter(IdsFilterMixin, NameSearchFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]


@kante.filter_type(models.Accessor)
class AccessorFilter(IdsFilterMixin):
    keys: auto


# Multi-dimensional data system filters


@kante.filter_type(models.ADataset)
class ADatasetFilter(IdsFilterMixin, NameSearchFilterMixin, OwnedFilterMixin, ScopeFilterMixin, CreatedThroughFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]
    description: Optional[FilterLookup[str]]


@kante.filter_type(models.DataArray)
class DataArrayFilter(IdsFilterMixin):
    id: auto
    level: Optional[FilterLookup[int]]

    @kante.filter_field(description="Filter by the dataset this array belongs to")
    def dataset(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}dataset_id": value})


@kante.filter_type(models.DataRoi)
class DataRoiFilter(IdsFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]
    description: Optional[FilterLookup[str]]
    kind: auto
    x_min: Optional[FilterLookup[int]]
    x_max: Optional[FilterLookup[int]]
    y_min: Optional[FilterLookup[int]]
    y_max: Optional[FilterLookup[int]]
    z_min: Optional[FilterLookup[int]]
    z_max: Optional[FilterLookup[int]]

    @kante.filter_field(description="Filter by the dataset this ROI belongs to")
    def dataset(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}dataset_id": value})

    @kante.filter_field(description="Search by name (case-insensitive substring)")
    def search(self, info: Info, value: str, prefix: str) -> Q:
        return Q(**{f"{prefix}name__icontains": value})


@kante.filter_type(models.Lens)
class LensFilter(IdsFilterMixin):
    id: auto

    @kante.filter_field(description="Filter by the dataset this lens looks at")
    def dataset(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}dataset_id": value})


@kante.filter_type(models.LineageLink)
class LineageLinkFilter(IdsFilterMixin):
    id: auto
    source_lens: Optional[FilterLookup[strawberry.ID]]
    target_lens: Optional[FilterLookup[strawberry.ID]]
    source_mask: Optional[FilterLookup[strawberry.ID]]
    action: Optional[FilterLookup[str]]


@kante.filter_type(models.Scene)
class SceneFilter(IdsFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]
    blending: auto

    @kante.filter_field(description="Search by name (case-insensitive substring)")
    def search(self, info: Info, value: str, prefix: str) -> Q:
        return Q(**{f"{prefix}name__icontains": value})

    @kante.filter_field(description="Filter by the parent scene")
    def parent(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}parent_id": value})

    @kante.filter_field(description="Filter for scenes with (true) or without (false) a parent")
    def parentless(self, info: Info, value: bool, prefix: str) -> Q:
        if value:
            return Q(**{f"{prefix}parent": None})
        return ~Q(**{f"{prefix}parent": None})


@kante.filter_type(models.Layer)
class LayerFilter(IdsFilterMixin):
    id: auto
    status: auto
    validity: auto
    blending: auto

    @kante.filter_field(description="Filter by the scene this layer is placed in")
    def scene(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}scene_id": value})

    @kante.filter_field(description="Filter by the lens this layer renders")
    def lens(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}lens_id": value})


@kante.filter_type(models.CoordinateAnchor)
class CoordinateAnchorFilter(IdsFilterMixin):
    id: auto
    dataset: Optional[FilterLookup[strawberry.ID]]


@kante.filter_type(models.OptikitState)
class OptikitStateFilter(IdsFilterMixin):
    id: auto

    @kante.filter_field(description="Filter by the coordinate anchor")
    def anchor(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}anchor_id": value})


@kante.filter_type(models.OmeMetadata)
class OmeMetadataFilter(IdsFilterMixin):
    id: auto

    @kante.filter_field(description="Filter by the coordinate anchor")
    def anchor(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}anchor_id": value})


@kante.filter_type(models.OmePlaneMetadata)
class OmePlaneMetadataFilter(IdsFilterMixin):
    id: auto

    @kante.filter_field(description="Filter by the coordinate anchor")
    def anchor(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}anchor_id": value})


@kante.filter_type(models.LightPath)
class LightPathFilter(IdsFilterMixin):
    id: auto

    @kante.filter_field(description="Filter by the coordinate anchor")
    def anchor(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}anchor_id": value})


@kante.filter_type(models.ValueHistogram)
class ValueHistogramFilter(IdsFilterMixin):
    id: auto
    min: Optional[FilterLookup[float]]
    max: Optional[FilterLookup[float]]

    @kante.filter_field(description="Filter by the coordinate anchor")
    def anchor(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}anchor_id": value})


@kante.filter_type(models.ChannelLabel)
class ChannelLabelFilter(IdsFilterMixin):
    id: auto
    label: Optional[FilterLookup[str]]

    @kante.filter_field(description="Filter by the coordinate anchor")
    def anchor(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}anchor_id": value})


# Task provenance filters


@kante.filter_type(KoherentTask)
class TaskFilter(IdsFilterMixin):
    task_id: Optional[FilterLookup[str]]
    app: Optional[FilterLookup[str]]
    action: Optional[FilterLookup[str]]

    @kante.filter_field(description="Filter by the assigner's subject ID")
    def assigner(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}assigner__sub": value})
