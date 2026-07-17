import datetime
import strawberry
from core import enums, models
from core.logic import coords as coords_logic
from core.logic import graph as graph_logic
from koherent.models import Task as KoherentTask
from strawberry import auto
from typing import Optional
from strawberry_django.filters import FilterLookup
from kante.types import Info
from django.db.models import Count, F, Q, QuerySet
from django.db.models.functions import Coalesce
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
class CreatedThroughFilterMixin:
    @kante.filter_field(description="Filter by the rekuest task id the item was created through")
    def created_through_task(self, info: Info, value: str, prefix: str) -> Q:
        return Q(**{f"{prefix}created_through__task_id": value})

    @kante.filter_field(description="Filter by the database ID of the task the item was created through (the `createdThrough { id }` field)")
    def created_through(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        """Match items created through the task with this database ID."""
        return Q(**{f"{prefix}created_through_id": value})

    @kante.filter_field(description="Filter by the sub of the user that assigned the creating task")
    def assigned_by(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        # Hits the denormalized FK on the model itself; the join through the
        # (very large) task table would scale with the user's task count.
        return Q(**{f"{prefix}created_through_by__sub": value})

    @kante.filter_field(description="Filter by the database ID of the user that assigned the creating task (the `createdThroughBy { id }` field)")
    def created_through_by(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        """Match items whose creating task was assigned by the user with this database ID."""
        return Q(**{f"{prefix}created_through_by_id": value})


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
class DatasetFilter(IdsFilterMixin, SearchFilterMixin, OwnedFilterMixin, PinnedFilterMixin, TagsFilterMixin, CreatedThroughFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]
    description: Optional[FilterLookup[str]]
    is_default: Optional[bool]

    @kante.filter_field(description="Filter for datasets with (true) or without (false) a parent")
    def parentless(self, info: Info, value: bool, prefix: str) -> Q:
        if value:
            return Q(**{f"{prefix}parent": None})
        return ~Q(**{f"{prefix}parent": None})

    @kante.filter_field(description="Filter by the parent dataset (list the children of a dataset)")
    def parent(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        """Match datasets that are direct children of the dataset with this ID."""
        return Q(**{f"{prefix}parent_id": value})


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
    time_since_start: auto
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
class ImageFilter(IdsFilterMixin, SearchFilterMixin, OwnedFilterMixin, PinnedFilterMixin, TagsFilterMixin, CreatedThroughFilterMixin):
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

    @kante.filter_field(description="Filter for images converted from this file (through their file views)")
    def file(self, info: Info, queryset: QuerySet, value: strawberry.ID, prefix: str) -> tuple[QuerySet, Q]:
        """Match images that have a file view referencing the file with this ID."""
        # Crosses the to-many file_views relation, so duplicate rows must be collapsed.
        return queryset.distinct(), Q(**{f"{prefix}file_views__file_id": value})


@kante.filter_type(models.File)
class FileFilter(IdsFilterMixin, NameSearchFilterMixin, OwnedFilterMixin, CreatedThroughFilterMixin):
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

    @kante.filter_field(description="Filter by a list of dataset IDs")
    def datasets(self, info: Info, value: list[strawberry.ID], prefix: str) -> Q:
        """Match tables belonging to any of the given datasets."""
        return Q(**{f"{prefix}dataset_id__in": value})

    @kante.filter_field(description="Filter for tables that are not derived from another table")
    def not_derived(self, info: Info, value: bool, prefix: str) -> Q:
        underived = Q(**{f"{prefix}origins": None})
        return underived if value else ~underived


@kante.filter_type(models.Snapshot)
class SnapshotFilter(IdsFilterMixin, NameSearchFilterMixin, OwnedFilterMixin, CreatedThroughFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]

    @kante.filter_field(description="Filter by the image this snapshot renders")
    def image(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}image_id": value})

    @kante.filter_field(description="Filter by a list of images this snapshot renders (fetch thumbnails for a set of images)")
    def images(self, info: Info, value: list[strawberry.ID], prefix: str) -> Q:
        """Match snapshots rendering any of the given images."""
        return Q(**{f"{prefix}image_id__in": value})

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
class ADatasetFilter(IdsFilterMixin, NameSearchFilterMixin, OwnedFilterMixin, CreatedThroughFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]
    description: Optional[FilterLookup[str]]

    # What a dataset is, is derived from its intrinsic axes rather than stored, so these two
    # translate the derivation in core.logic.coords into a query -- the same shape as
    # CoordinateSystemFilter.kind above, one layer further out.
    #
    # Both annotate, which nothing else in this module does. Two things make that necessary:
    # a spatial spec is a *count* of axes, and all-of matching cannot be written as ANDed Qs
    # at all. `Q(axes__type=TIME) & Q(axes__type=CHANNEL)` asks one axis row to be both types
    # and matches nothing, because a single .filter() over a to-many relation binds one row --
    # so an all-of test has to count distinct matches instead. Every Count is distinct: another
    # filter (tags, say) may add a join that multiplies the rows out from under these.
    #
    # Annotating means these must pick an alias, and an alias is global to the queryset while
    # a filter is not: `AND`/`OR` recurse into the same filter type with the *same* prefix, so
    # `{spec: [MULTICHANNEL], AND: {spec: [TIMESERIES]}}` runs this method twice over one
    # queryset. Django keeps the first annotation of a repeated alias and drops the second --
    # silently, while the second branch's Q goes on reading the alias and so tests the first
    # branch's expression. That returns wrong rows, not an error. So an alias must name the
    # expression it stands for: anything the Count filters on goes in the name, and the guard
    # below makes reuse explicit rather than leaning on which duplicate Django keeps.

    @kante.filter_field(
        description="Filter to datasets satisfying every one of these specs, e.g. [VOLUME, TIMESERIES] for 3D timelapses. Derived from the axes of the intrinsic coordinate system, never stored. A dataset carries one spatial spec (by how many SPACE axes it has) plus a modifier per acquisition axis present, so two spatial specs together match nothing"
    )
    def spec(self, info: Info, queryset: QuerySet, value: list[enums.ADatasetSpec], prefix: str) -> tuple[QuerySet, Q]:
        q = Q()

        modifier_types = {axis_type for axis_type in (coords_logic.axis_type_for_spec(spec) for spec in value) if axis_type is not None}
        if modifier_types:
            queryset, alias = _annotate_axis_type_count(queryset, prefix, modifier_types)
            q &= Q(**{alias: len(modifier_types)})

        spatial = [spec for spec in value if coords_logic.is_spatial_spec(spec)]
        if spatial:
            # One annotation for every spatial spec asked for: the expression does not vary,
            # only the count compared against it does. `[IMAGE, VOLUME]` is then `= 2 AND = 3`,
            # which is empty -- the right answer, since only one spatial spec can ever hold.
            queryset, alias = _annotate_axis_type_count(queryset, prefix, {enums.AxisTypeChoices.SPACE.value}, count_axes=True)
            # A dataset whose intrinsic system does not exist yet counts zero SPACE axes over
            # the outer join and would answer to SCALAR, while `ADataset.spec` reports nothing
            # for it. The guard is what keeps the filter and the field from disagreeing.
            q &= Q(**{f"{prefix}intrinsic_system__isnull": False})
            for spec in spatial:
                count = coords_logic.spatial_count_for_spec(spec)
                q &= Q(**{alias: count}) if count is not None else Q(**{f"{alias}__gte": coords_logic.hypervolume_min_spatial_count()})

        return queryset, q

    @kante.filter_field(description="Filter to datasets whose intrinsic coordinate system carries every one of these axis types, e.g. [TIME, CHANNEL]. The raw form of `spec`, for the types no spec names: COORDINATE, DISPLACEMENT, INDEX")
    def has_axis_types(self, info: Info, queryset: QuerySet, value: list[enums.AxisType], prefix: str) -> tuple[QuerySet, Q]:
        types = {axis_type.value for axis_type in value}
        if not types:
            return queryset, Q()
        queryset, alias = _annotate_axis_type_count(queryset, prefix, types)
        return queryset, Q(**{alias: len(types)})

    @kante.filter_field(description="Filter by whether the dataset carries a resolution pyramid: true for the multiscale ones, false for those with a single level")
    def multiscale(self, info: Info, queryset: QuerySet, value: bool, prefix: str) -> tuple[QuerySet, Q]:
        # The same derivation as the `multiscale` property -- more than one level -- as a query.
        alias = f"_{prefix.replace('__', '_')}level_count"
        queryset = _annotate_once(queryset, alias, Count(f"{prefix}data_arrays", distinct=True))
        return queryset, Q(**{f"{alias}__gt": 1}) if value else Q(**{f"{alias}__lte": 1})

    @kante.filter_field(
        description="Filter by whether the dataset carries at least one PHYSICAL calibration -- a space with real units. False finds the data that is still only pixels, with no pixel size or stage pose recorded. Unrelated to a phasor histogram's `calibrated`, which is about reference correction"
    )
    def calibrated(self, info: Info, queryset: QuerySet, value: bool, prefix: str) -> tuple[QuerySet, Q]:
        # Physical space enters the model exactly once, as a calibration edge off the
        # intrinsic system, so carrying a PHYSICAL system *is* being calibrated.
        if value:
            # A dataset may carry several calibrations (stage space, specimen space, a
            # re-calibration), and each would repeat the row.
            return queryset.distinct(), Q(**{f"{prefix}calibrations__isnull": False})
        return queryset, Q(**{f"{prefix}calibrations__isnull": True})

    @kante.filter_field(description="Filter to datasets rendered in this scene, through their lenses' layers. What is actually staged there -- for what merely could be, use `placeableIn`")
    def scene(self, info: Info, queryset: QuerySet, value: strawberry.ID, prefix: str) -> tuple[QuerySet, Q]:
        # The inverse of the `scenes` field, which is itself derived rather than stored:
        # a scene is a composition, so there is no dataset-to-scene column to filter on.
        # Two to-many hops (lenses, then layers), either of which can repeat the row.
        return queryset.distinct(), Q(**{f"{prefix}lenses__layers__scene_id": value})

    @kante.filter_field(description="Filter to datasets placeable into this scene: those with a lens whose space has a traversable path to the scene's world, walking the transformation edges. What could be staged there -- for what already is, use `scene`")
    def placeable_in(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        scene = models.Scene.objects.filter(pk=value).first()
        if scene is None:
            return Q(pk__in=[])
        return Q(**{f"{prefix}id__in": graph_logic.placeable_lens_dataset_ids(scene)})

    @kante.filter_field(
        description="Filter to the datasets computed from this one -- the deconvolutions, segmentations and projections that named a space of it as their parent. Every child, not just the ones it places: a fusion that named it second is listed, and so is a child whose derivation is UNMAPPABLE, since it still came from here"
    )
    def derived_from(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}id__in": _derived_dataset_ids(source_id=value)})

    @kante.filter_field(description="Filter for datasets that were acquired rather than computed: true for the roots, those with no derivation edge into another dataset's space")
    def not_derived(self, info: Info, value: bool, prefix: str) -> Q:
        derived = Q(**{f"{prefix}id__in": _derived_dataset_ids()})
        return ~derived if value else derived


@kante.filter_type(models.Animation)
class AnimationFilter(IdsFilterMixin, NameSearchFilterMixin, OwnedFilterMixin, CreatedThroughFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]

    @kante.filter_field(description="Filter by the scene this tour flies through")
    def scene(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}scene_id": value})


@kante.filter_type(models.SceneSnapshot)
class SceneSnapshotFilter(IdsFilterMixin, NameSearchFilterMixin, OwnedFilterMixin, PinnedFilterMixin, CreatedThroughFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]

    # No `dataset` filter: a snapshot is a picture of a composition and has no dataset
    # FK to hang one off. Which datasets a picture shows is a placement question, and
    # answering it means a graph walk per scene -- see graph_logic.scenes_showing_only,
    # which ADataset.latestSnapshot pays for deliberately and a list filter should not.

    @kante.filter_field(description="Filter by the scene this snapshot is a picture of")
    def scene(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}scene_id": value})

    @kante.filter_field(description="Filter by a list of scenes (fetch the tiles for a set of scenes in one query, the way a picker does)")
    def scenes(self, info: Info, value: list[strawberry.ID], prefix: str) -> Q:
        """Match snapshots of any of the given scenes."""
        return Q(**{f"{prefix}scene_id__in": value})


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

    @kante.filter_field(description="Filter by the coordinate system this ROI is drawn in")
    def coordinate_system(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}coordinate_system_id": value})

    @kante.filter_field(description="Filter by the dataset this ROI's coordinate system belongs to, whichever way the system hangs off it (intrinsic, calibration, pyramid level or lens)")
    def dataset(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return (
            Q(**{f"{prefix}coordinate_system__intrinsic_of_id": value})
            | Q(**{f"{prefix}coordinate_system__dataset_id": value})
            | Q(**{f"{prefix}coordinate_system__data_array__dataset_id": value})
            | Q(**{f"{prefix}coordinate_system__lens__dataset_id": value})
        )

    @kante.filter_field(description="Search by name (case-insensitive substring)")
    def search(self, info: Info, value: str, prefix: str) -> Q:
        return Q(**{f"{prefix}name__icontains": value})


@kante.filter_type(models.Lens)
class LensFilter(IdsFilterMixin):
    id: auto

    @kante.filter_field(description="Filter by the dataset this lens looks at")
    def dataset(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}dataset_id": value})

    @kante.filter_field(description="Filter to lenses placeable into this scene: those whose space has a traversable path to the scene's world, walking the transformation edges under the scene's membership")
    def placeable_in(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        scene = models.Scene.objects.filter(pk=value).first()
        if scene is None:
            return Q(pk__in=[])
        return Q(**{f"{prefix}dataset_id__in": graph_logic.placeable_lens_dataset_ids(scene)})


@kante.filter_type(models.Scene)
class SceneFilter(IdsFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]
    blending: auto

    @kante.filter_field(description="Search by name (case-insensitive substring)")
    def search(self, info: Info, value: str, prefix: str) -> Q:
        return Q(**{f"{prefix}name__icontains": value})



@kante.filter_type(models.Layer)
class LayerFilter(IdsFilterMixin):
    id: auto
    kind: auto
    blending: auto

    @kante.filter_field(description="Filter by the scene this layer is placed in")
    def scene(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}scene_id": value})

    @kante.filter_field(description="Filter image layers by the lens they render")
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
class TaskFilter(IdsFilterMixin, CreatedAtFilterMixin):
    task_id: Optional[FilterLookup[str]]
    parent_task_id: Optional[FilterLookup[str]]
    root_task_id: Optional[FilterLookup[str]]
    agent_client_id: Optional[FilterLookup[str]]
    issuer: Optional[FilterLookup[str]]

    @kante.filter_field(description="Filter by the assigner's subject ID")
    def assigner(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}assigner__sub": value})

    @kante.filter_field(description="Filter by the assigner's database user ID")
    def assigner_id(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        """Match tasks assigned by the user with this database ID."""
        return Q(**{f"{prefix}assigner_id": value})

    @kante.filter_field(description="Search by task id or executing agent client id (case-insensitive substring)")
    def search(self, info: Info, value: str, prefix: str) -> Q:
        """Match tasks whose task id or executing agent client id contains the given text."""
        return Q(**{f"{prefix}task_id__icontains": value}) | Q(**{f"{prefix}agent_client_id__icontains": value})


@kante.filter_type(models.CoordinateSystem)
class CoordinateSystemFilter(IdsFilterMixin, NameSearchFilterMixin, OwnedFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]

    # Kind is derived from ownership, not stored, so the filter translates each value
    # into the owner-FK condition that *defines* it -- the same derivation as
    # models.CoordinateSystem.kind, expressed as a query.
    @kante.filter_field(description="Filter by what the system denotes, derived from its owner: INTRINSIC (a container's own native space), ARRAY (a pyramid level's or lens' grid), PHYSICAL (a calibration), SHARED (a scene's world or an ownerless hub)")
    def kind(self, info: Info, value: enums.CoordinateSystemKind, prefix: str) -> Q:
        if value == enums.CoordinateSystemKind.INTRINSIC:
            return Q(**{f"{prefix}intrinsic_of__isnull": False}) | Q(**{f"{prefix}mesh_collection__isnull": False}) | Q(**{f"{prefix}table_dataset__isnull": False})
        if value == enums.CoordinateSystemKind.ARRAY:
            return Q(**{f"{prefix}data_array__isnull": False}) | Q(**{f"{prefix}lens__isnull": False})
        if value == enums.CoordinateSystemKind.PHYSICAL:
            return Q(**{f"{prefix}dataset__isnull": False})
        return Q(
            **{
                f"{prefix}intrinsic_of__isnull": True,
                f"{prefix}dataset__isnull": True,
                f"{prefix}data_array__isnull": True,
                f"{prefix}lens__isnull": True,
                f"{prefix}mesh_collection__isnull": True,
                f"{prefix}table_dataset__isnull": True,
            }
        )

    # `kind: SHARED` cannot express this: it matches a scene's minted world too, and only a
    # hub can be registered into or shared between scenes. Same owner-FK derivation as
    # models.CoordinateSystem.is_hub, expressed as a query.
    @kante.filter_field(description="Filter to ownerless shared spaces -- the hubs, the only systems that can receive registrations and be shared between scenes. Narrower than `kind: SHARED`, which also matches each scene's own minted world")
    def is_hub(self, info: Info, value: bool, prefix: str) -> Q:
        ownerless = Q(
            **{
                f"{prefix}intrinsic_of__isnull": True,
                f"{prefix}dataset__isnull": True,
                f"{prefix}data_array__isnull": True,
                f"{prefix}lens__isnull": True,
                f"{prefix}scene__isnull": True,
                f"{prefix}mesh_collection__isnull": True,
                f"{prefix}table_dataset__isnull": True,
            }
        )
        return ownerless if value else ~ownerless

    @kante.filter_field(description="Filter by the dataset this system belongs to directly: its INTRINSIC pixel grid or one of its PHYSICAL calibrations")
    def dataset(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}intrinsic_of_id": value}) | Q(**{f"{prefix}dataset_id": value})

    @kante.filter_field(description="Filter by a scene composing over this system -- its minted world or an adopted hub")
    def scene(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}scenes__pk": value})


@kante.filter_type(models.Axis)
class AxisFilter(IdsFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]
    type: auto

    @kante.filter_field(description="Filter by the coordinate system this axis belongs to")
    def coordinate_system(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}coordinate_system_id": value})


@kante.filter_type(models.Transformation)
class TransformationFilter(IdsFilterMixin, OwnedFilterMixin):
    id: auto
    kind: auto

    # Not `auto`: that would mint a second SDL enum from the TextChoices twin
    # (PlacementValidityChoices) beside the strawberry PlacementValidity every
    # other field uses.
    @kante.filter_field(description="Filter by how much the edge's map is actually known, e.g. UNKNOWN to list every placement that is still an assumption")
    def validity(self, info: Info, value: enums.PlacementValidity, prefix: str) -> Q:
        return Q(**{f"{prefix}validity": value.value})

    @kante.filter_field(description="Filter by the coordinate system this transformation maps from")
    def input(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}input_id": value})

    @kante.filter_field(description="Filter by the coordinate system this transformation maps to")
    def output(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}output_id": value})

    @kante.filter_field(description="Filter by the scene this transformation is a member of")
    def scene(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}scenes__id": value})

    @kante.filter_field(description="Show only top-level edges, excluding the children of SEQUENCE / BY_DIMENSION wrappers")
    def roots_only(self, info: Info, value: bool, prefix: str) -> Q:
        return Q(**{f"{prefix}parent__isnull": True}) if value else Q()


@kante.filter_type(models.MeshCollection)
class MeshCollectionFilter(IdsFilterMixin, OwnedFilterMixin):
    id: auto
    version: Optional[FilterLookup[str]]

    @kante.filter_field(description="Filter by the coordinate system the mesh geometry is expressed in (the collection's own)")
    def coordinate_system(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}coordinate_system__id": value})

    @kante.filter_field(description="Filter by the dataset the meshes were extracted from, following the derivation edge")
    def dataset(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}coordinate_system__in": _systems_derived_from_dataset(value)})


@kante.filter_type(models.TableDataset)
class TableDatasetFilter(IdsFilterMixin, NameSearchFilterMixin, OwnedFilterMixin, CreatedThroughFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]
    description: Optional[FilterLookup[str]]

    @kante.filter_field(description="Filter by the dataset the table was computed from, following its derivation edge")
    def dataset(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}coordinate_system__in": _systems_derived_from_dataset(value)})

    @kante.filter_field(description="Filter to tables that declare a column of this role, e.g. TRACK_ID")
    def has_column_role(self, info: Info, value: enums.TableColumnRole, prefix: str) -> Q:
        return Q(**{f"{prefix}columns__role": value.value})

    @kante.filter_field(description="Filter to table datasets placeable into this scene: those whose coordinate system has a traversable path to the scene's world, walking the transformation edges under the scene's membership")
    def placeable_in(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        scene = models.Scene.objects.filter(pk=value).first()
        if scene is None:
            return Q(pk__in=[])
        return Q(**{f"{prefix}id__in": graph_logic.placeable_table_dataset_ids(scene)})


def _annotate_once(queryset: QuerySet, alias: str, expression) -> QuerySet:
    """Add an annotation unless the alias is already taken by an identical one.

    An alias is global to the queryset while a filter is not: `AND`/`OR` recurse with
    the same prefix, so two branches may annotate one queryset. Django keeps the first
    annotation of a repeated alias and silently drops the second, so callers must name
    an alias for the *expression* it stands for -- then a repeat is the same question
    asked twice, and skipping it is right. Never call this with an alias whose
    expression can vary.
    """
    if alias in queryset.query.annotations:
        return queryset
    return queryset.annotate(**{alias: expression})


def _derived_dataset_ids(source_id: strawberry.ID | None = None):
    """The ids of every dataset that was derived, or only those derived from one source.

    `graph_logic.derivation_edges` expressed as a query, and it has to agree with it.
    An edge is a derivation when it leaves a dataset's intrinsic system (so
    `input__intrinsic_of` is what names the child, and a mesh or table collection's
    edge is excluded -- it does not start at one) and lands in a space belonging to
    *another* dataset. The Coalesce is `graph_logic.system_dataset` in SQL: whichever
    owner FK the output space has is the dataset it came from.

    The self-exclusion is the load-bearing part. A calibration edge runs from a
    dataset's intrinsic system to its own PHYSICAL space, and a level edge and a lens
    edge land in its own intrinsic -- all three would otherwise make a dataset its own
    parent. `derivation_edges` drops them with `source.pk != dataset.pk`; the same test
    here compares two columns of the one row, so no subquery correlation is needed.

    Kind-blind, exactly as `derivation_edges` is: an UNMAPPABLE derivation is still a
    derivation, and it is the one machine-readable answer to why a dataset cannot be
    placed. Filtering it here would restore the silence that kind was invented to break.
    """
    source_dataset = Coalesce(
        "output__intrinsic_of_id",
        "output__dataset_id",
        "output__lens__dataset_id",
        "output__data_array__dataset_id",
    )
    edges = (
        models.Transformation.objects.filter(parent__isnull=True, input__intrinsic_of__isnull=False)
        .annotate(_source_dataset=source_dataset)
        .filter(_source_dataset__isnull=False)
        .exclude(_source_dataset=F("input__intrinsic_of_id"))
    )
    if source_id is not None:
        edges = edges.filter(_source_dataset=source_id)
    return edges.values_list("input__intrinsic_of_id", flat=True)


def _annotate_axis_type_count(queryset: QuerySet, prefix: str, types: set[str], count_axes: bool = False) -> tuple[QuerySet, str]:
    """Annotate how many of `types` a dataset's intrinsic axes match, and return the alias to compare against.

    Two counts, one shape. `count_axes=False` counts the distinct axis *types*
    matched, which is how an all-of test is written: it equals `len(types)` exactly
    when every requested type is present. `count_axes=True` counts the matching
    *axes* themselves, which is what a spatial spec compares against -- three SPACE
    axes is a VOLUME, and counting types there would only ever say 1.

    The alias names the expression, because an alias is global to the queryset while
    a filter is not: `AND`/`OR` recurse with the same prefix, so two branches can
    annotate one queryset. Two branches asking the same question then share the one
    annotation (identical expression, so the guard skips the second), and two asking
    different questions get different aliases instead of one silently shadowing the
    other. The Count is distinct because another filter may join in rows that
    multiply these out.
    """
    axes = f"{prefix}intrinsic_system__axes"
    stem = "space_axis_count" if count_axes else "matched_axis_types"
    alias = f"_{prefix.replace('__', '_')}{stem}__{'_'.join(sorted(types))}"
    expression = Count(axes if count_axes else f"{axes}__type", filter=Q(**{f"{axes}__type__in": list(types)}), distinct=True)
    return _annotate_once(queryset, alias, expression), alias


def _systems_derived_from_dataset(dataset_id: strawberry.ID):
    """The collection systems whose derivation edge lands in this dataset.

    A subquery rather than a join: `Transformation.input`/`output` are declared
    `related_name="+"`, so there is no reverse accessor to filter across, and a collection
    keeps no dataset column of its own -- the edge is the only place that fact lives, and
    duplicating it onto the collection is the copy this whole graph exists to avoid.
    """
    return models.Transformation.objects.filter(
        parent__isnull=True,
        input__isnull=False,
    ).filter(
        Q(output__intrinsic_of_id=dataset_id) | Q(output__dataset_id=dataset_id) | Q(output__lens__dataset_id=dataset_id) | Q(output__data_array__dataset_id=dataset_id)
    ).values("input_id")
