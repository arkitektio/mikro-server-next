import datetime
import strawberry
from core import enums, models
from core.inputs.coords import BoundingBoxInput, CoordinateInput
from core.logic import graph as graph_logic
from core.scoping import for_org
from koherent.models import Task as KoherentTask
from strawberry import auto
from typing import Optional
from strawberry_django.filters import FilterLookup
from kante.types import Info
from django.db.models import Count, Exists, F, OuterRef, Q, QuerySet
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

    @kante.filter_field(
        description=(
            "Filter for files nothing was exported into: the raw sources a converter read, as opposed to the files written out of data already here. Reads the file's links, "
            "which replaced the `origins` M2M -- that column was never written by any resolver, so this filter used to answer `true` for every file in the database"
        )
    )
    def not_derived(self, info: Info, value: bool, prefix: str) -> Q:
        """Match files nothing here was exported into."""
        written_out = Q(**{f"{prefix}links__direction": enums.FileLinkDirectionChoices.RENDITION.value})
        return ~written_out if value else written_out

    @kante.filter_field(description="Filter by the container this file was written from, or read into. Matches a link in either direction")
    def linked_to_dataset(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        """Match files linked to this dataset in either direction."""
        return Q(**{f"{prefix}links__dataset_id": value})


@kante.filter_type(models.FileLink)
class FileLinkFilter(IdsFilterMixin, OwnedFilterMixin, CreatedThroughFilterMixin):
    """Filters for the links between a file and the data it encodes."""

    id: auto
    direction: Optional[enums.FileLinkDirection]
    series_identifier: Optional[FilterLookup[str]]
    value_relation: Optional[enums.ValueRelation]

    @kante.filter_field(description="Filter by the file side of the link")
    def file(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        """Match links whose file side is this file."""
        return Q(**{f"{prefix}file_id": value})


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

    # `notDerived` is gone with `Table.origins`, the M2M it read. That column was never
    # written by any resolver, so the filter answered `true` for every table in the database
    # and `false` for none -- it could not have been used correctly. The live tabular
    # container is `TableDataset`, which states its lineage through `derivedFrom` (data) and
    # `sourceFiles` (bytes); `Table` is legacy alongside `Image` and gains neither.


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

    # What a dataset is, is materialized onto `stored_spec` at creation (see ADataset.spec and
    # core.logic.graph.create_pixel_axes), so this reads the column rather than re-deriving the
    # spec in SQL. A stored list holds exactly one spatial member plus a modifier per acquisition
    # axis, so JSONB containment gives the all-of semantics directly: two spatial members can
    # never co-occur in a stored list, so `[IMAGE, VOLUME]` matches nothing, and a headless
    # dataset (empty list) is excluded by any non-empty request without a special guard.

    @kante.filter_field(
        description="Filter to datasets satisfying every one of these specs, e.g. [VOLUME, TIMESERIES] for 3D timelapses. Materialized from the axes of the intrinsic coordinate system at creation. A dataset carries one spatial spec (by how many SPACE axes it has) plus a modifier per acquisition axis present, so two spatial specs together match nothing"
    )
    def spec(self, info: Info, queryset: QuerySet, value: list[enums.ADatasetSpec], prefix: str) -> tuple[QuerySet, Q]:
        if not value:
            return queryset, Q()
        return queryset, Q(**{f"{prefix}stored_spec__contains": [spec.value for spec in value]})

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
        description="Filter by whether the dataset has an edge into a space with real units. False finds the data that is still only pixels, with no pixel size or stage pose recorded. Unrelated to a phasor histogram's `calibrated`, which is about reference correction"
    )
    def has_physical_space(self, info: Info, queryset: QuerySet, value: bool, prefix: str) -> tuple[QuerySet, Q]:
        # A physical space is not a thing a dataset owns (RFC-9): it is an edge out of the
        # dataset's space into one whose axes carry units. So "has a physical space" is a
        # question about the graph, and it is asked as one -- an edge whose far side has a
        # united axis.
        physical_space = models.Transformation.objects.filter(
            input_id=OuterRef(f"{prefix}coordinate_system_id"),
            parent__isnull=True,
            output__axes__unit__isnull=False,
        ).exclude(kind=enums.TransformKindChoices.UNMAPPABLE.value)
        queryset = _annotate_once(queryset, "_has_physical_space", Exists(physical_space))
        return queryset, Q(_has_physical_space=value)

    @kante.filter_field(description="Filter to datasets rendered in this scene, through their lenses' layers. What is actually staged there -- for what merely could be, use `placeableIn`")
    def scene(self, info: Info, queryset: QuerySet, value: strawberry.ID, prefix: str) -> tuple[QuerySet, Q]:
        # The inverse of the `scenes` field, which is itself derived rather than stored:
        # a scene is a composition, so there is no dataset-to-scene column to filter on.
        # Two to-many hops (lenses, then layers), either of which can repeat the row.
        return queryset.distinct(), Q(**{f"{prefix}lenses__layers__scene_id": value})

    @kante.filter_field(description="Filter to datasets placeable into this coordinate system: those with a lens whose space has a traversable path into it, walking the transformation edges. Takes a *space*, not a scene, because that is all the answer depends on -- every scene over one world offers the same candidates. Pass `scene.worldCoordinateSystem.id` to ask it of a scene. What could be staged there -- for what already is, use `scene`")
    def placeable_in(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        space = _placeable_destination(info, value)
        if space is None:
            return Q(pk__in=[])
        return Q(**{f"{prefix}id__in": graph_logic.placeable_lens_dataset_ids(space)})

    @kante.filter_field(
        description="Filter to the datasets computed from this one -- the deconvolutions, segmentations and projections that named a space of it as their parent. Every child, not just the ones it places: a fusion that named it second is listed, and so is a child whose derivation is UNMAPPABLE, since it still came from here"
    )
    def derived_from(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}id__in": _derived_dataset_ids(source_id=value)})

    @kante.filter_field(description="Filter for datasets that were acquired rather than computed: true for the roots, those with no derivation edge into another dataset's space")
    def not_derived(self, info: Info, value: bool, prefix: str) -> Q:
        derived = Q(**{f"{prefix}id__in": _derived_dataset_ids()})
        return ~derived if value else derived

    @kante.filter_field(
        description=(
            "Filter to the datasets converted from this file -- every series of it, unless `sourceSeriesIdentifier` narrows that. A file link, not a derivation: this asks which "
            "bytes the arrays were read out of, where `derivedFrom` asks which data they were computed from. A dataset can honestly answer both"
        )
    )
    def source_file(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        """Match datasets converted from this file."""
        return Q(**{f"{prefix}file_links__file_id": value, f"{prefix}file_links__direction": enums.FileLinkDirectionChoices.SOURCE.value})

    @kante.filter_field(description="Filter to the datasets converted from one series of a file. Pair it with `sourceFile`; alone it matches that series identifier in any file")
    def source_series_identifier(self, info: Info, value: str, prefix: str) -> Q:
        """Match datasets converted from this series of a file."""
        return Q(**{f"{prefix}file_links__series_identifier": value, f"{prefix}file_links__direction": enums.FileLinkDirectionChoices.SOURCE.value})


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
    # answering it means a graph walk per scene -- see graph_logic.scenes_by_sole_dataset,
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


@kante.filter_type(models.AnnotationCollection)
class AnnotationCollectionFilter(IdsFilterMixin, OwnedFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]

    @kante.filter_field(description="Filter by the scene this collection was minted for as its default drawing surface")
    def scene(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}scene_id": value})

    @kante.filter_field(description="Filter by the coordinate system the annotations are drawn in (the collection's own)")
    def coordinate_system(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}coordinate_system__id": value})

    @kante.filter_field(description="Filter by the dataset the shapes are drawn over, following the derivation edge")
    def dataset(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}coordinate_system__in": _systems_derived_from_dataset(value)})

    @kante.filter_field(description="Search by name (case-insensitive substring)")
    def search(self, info: Info, value: str, prefix: str) -> Q:
        return Q(**{f"{prefix}name__icontains": value})


@kante.filter_type(models.Annotation)
class AnnotationFilter(IdsFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]
    description: Optional[FilterLookup[str]]
    kind: auto

    @kante.filter_field(description="Filter by the collection this annotation belongs to")
    def collection(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}collection_id": value})

    @kante.filter_field(description="Filter by the coordinate system this annotation is drawn in (its collection's own)")
    def coordinate_system(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}collection__coordinate_system__id": value})

    @kante.filter_field(description="Filter by the dataset the annotations are drawn over, following the collection's derivation edge")
    def dataset(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}collection__coordinate_system__in": _systems_derived_from_dataset(value)})

    @kante.filter_field(description="Search by name (case-insensitive substring)")
    def search(self, info: Info, value: str, prefix: str) -> Q:
        return Q(**{f"{prefix}name__icontains": value})

    def _require_frame(self, op: str) -> None:
        # Boxes only compare within one frame: every collection's bbox lives in its
        # own nearest-intrinsic space, so an unscoped spatial predicate would compare
        # numbers from different spaces and call the mismatches results.
        if self.collection is strawberry.UNSET and self.coordinate_system is strawberry.UNSET:
            raise ValueError(f"`{op}` compares boxes within one frame: pass `collection` or `coordinateSystem` alongside it.")

    @kante.filter_field(
        description="Filter to annotations pinned to every one of these coordinates, e.g. [{name: 't', value: 3}]. GIN-backed containment on the stored coordinate dict; an annotation that spans a coordinate does not match a pin on it"
    )
    def pinned_to(self, info: Info, value: list[CoordinateInput], prefix: str) -> Q:
        if not value:
            return Q()
        return Q(**{f"{prefix}coordinates__contains": {coordinate.name: coordinate.value for coordinate in value}})

    @kante.filter_field(
        description="Filter to annotations whose intrinsic bounding box overlaps this box (GiST-backed). Only meaningful within one frame: pass `collection` or `coordinateSystem` alongside. A box of lower rank is zero-filled on the missing coordinates"
    )
    def intersects(self, info: Info, value: BoundingBoxInput, prefix: str) -> Q:
        self._require_frame("intersects")
        return Q(**{f"{prefix}bbox_cube__overlaps": (value.min, value.max)})

    @kante.filter_field(
        description="Filter to annotations whose intrinsic bounding box contains this point (GiST-backed). Only meaningful within one frame: pass `collection` or `coordinateSystem` alongside"
    )
    def contains_point(self, info: Info, value: list[float], prefix: str) -> Q:
        self._require_frame("containsPoint")
        return Q(**{f"{prefix}bbox_cube__contains_point": value})


@kante.filter_type(models.Lens)
class LensFilter(IdsFilterMixin):
    id: auto

    @kante.filter_field(description="Filter by the dataset this lens looks at")
    def dataset(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}dataset_id": value})

    @kante.filter_field(description="Filter to lenses placeable into this coordinate system: those whose space has a traversable path into it, walking the transformation edges. Takes a *space*, not a scene -- pass `scene.worldCoordinateSystem.id` to ask it of a scene")
    def placeable_in(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        space = _placeable_destination(info, value)
        if space is None:
            return Q(pk__in=[])
        return Q(**{f"{prefix}dataset_id__in": graph_logic.placeable_lens_dataset_ids(space)})


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

    # `kind` is gone with ownership (RFC-9). What a space *is* follows from what lives in it,
    # and "nothing lives here" -- a pure reference frame, a world -- is the only distinction
    # the old four-value label was really carrying.
    @kante.filter_field(description="Filter to the spaces nothing lives in: pure reference frames, the worlds and atlases sources are registered into. False finds the spaces some data actually occupies")
    def uninhabited(self, info: Info, value: bool, prefix: str) -> Q:
        condition = Q(
            **{
                f"{prefix}datasets__isnull": True,
                f"{prefix}lenses__isnull": True,
                f"{prefix}data_arrays__isnull": True,
                f"{prefix}mesh_collections__isnull": True,
                f"{prefix}table_datasets__isnull": True,
                f"{prefix}annotation_collections__isnull": True,
            }
        )
        return condition if value else ~condition

    @kante.filter_field(description="Filter to the spaces this dataset's data lives in: its own grid, and the grids of its pyramid levels and lenses")
    def dataset(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}datasets__id": value}) | Q(**{f"{prefix}lenses__dataset_id": value}) | Q(**{f"{prefix}data_arrays__dataset_id": value})

    @kante.filter_field(description="Filter by a scene composing over this system as its world")
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

    # There is deliberately no `scene` filter. One used to walk `scenes__id`, the membership
    # M2M RFC-6 deleted -- so it had been raising `FieldError` ever since, unnoticed because
    # nothing selects it. It has no honest replacement either: an edge is not a member of a
    # composition. An edge *into a space* is `output: <systemId>` above, and the field form
    # of that same question is `CoordinateSystem.registrations`.

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

    @kante.filter_field(description="Filter to table datasets placeable into this coordinate system: those whose own coordinate system has a traversable path into it, walking the transformation edges. Takes a *space*, not a scene -- pass `scene.worldCoordinateSystem.id` to ask it of a scene")
    def placeable_in(self, info: Info, value: strawberry.ID, prefix: str) -> Q:
        space = _placeable_destination(info, value)
        if space is None:
            return Q(pk__in=[])
        return Q(**{f"{prefix}id__in": graph_logic.placeable_table_dataset_ids(space)})


def _placeable_destination(info: Info, value: strawberry.ID) -> "models.CoordinateSystem | None":
    """The space a `placeableIn` filter is asking about, or None when there is no such space here.

    Organization-scoped, unlike the scene lookup this replaced: the walk it feeds reads another
    org's edges otherwise, and while the rows that come back are scoped by the parent field
    anyway, "which of my datasets are placeable in your world" is still an answer this server
    has no reason to give. `None` rather than a raise, because a filter naming a space that is
    not there should return nothing, not fail the whole query.
    """
    return for_org(models.CoordinateSystem, info).filter(pk=value).first()


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
    An edge is a derivation when it leaves a space a dataset *lives in* (so
    `input__datasets` is what names the child, and a mesh or table collection's edge is
    excluded -- it does not set out from one) and lands in a space some *other* dataset's
    data lives in. The Coalesce is `graph_logic.system_dataset` in SQL: whichever resident
    the output space has is the dataset it came from.

    The self-exclusion is the load-bearing part. A level edge and a lens edge land in the
    dataset's own grid, which would otherwise make a dataset its own parent.
    `derivation_edges` drops them with `source.pk != dataset.pk`; the same test here
    compares two columns of the one row, so no subquery correlation is needed. A
    physical-space edge needs no exclusion any more -- it lands in a space *nothing* lives in,
    so the Coalesce is null and the `_source_dataset__isnull` filter drops it.

    Kind-blind, exactly as `derivation_edges` is: an UNMAPPABLE derivation is still a
    derivation, and it is the one machine-readable answer to why a dataset cannot be
    placed. Filtering it here would restore the silence that kind was invented to break.
    """
    source_dataset = Coalesce(
        "output__datasets__id",
        "output__lenses__dataset_id",
        "output__data_arrays__dataset_id",
    )
    edges = (
        models.Transformation.objects.filter(parent__isnull=True, input__datasets__isnull=False)
        .annotate(_source_dataset=source_dataset)
        .filter(_source_dataset__isnull=False)
        .exclude(_source_dataset=F("input__datasets__id"))
    )
    if source_id is not None:
        edges = edges.filter(_source_dataset=source_id)
    return edges.values_list("input__datasets__id", flat=True)


def _annotate_axis_type_count(queryset: QuerySet, prefix: str, types: set[str]) -> tuple[QuerySet, str]:
    """Annotate how many of `types` a dataset's intrinsic axes match, and return the alias to compare against.

    Counts the distinct axis *types* matched, which is how an all-of test is written:
    it equals `len(types)` exactly when every requested type is present.

    The alias names the expression, because an alias is global to the queryset while
    a filter is not: `AND`/`OR` recurse with the same prefix, so two branches can
    annotate one queryset. Two branches asking the same question then share the one
    annotation (identical expression, so the guard skips the second), and two asking
    different questions get different aliases instead of one silently shadowing the
    other. The Count is distinct because another filter may join in rows that
    multiply these out.
    """
    axes = f"{prefix}coordinate_system__axes"
    alias = f"_{prefix.replace('__', '_')}matched_axis_types__{'_'.join(sorted(types))}"
    expression = Count(f"{axes}__type", filter=Q(**{f"{axes}__type__in": list(types)}), distinct=True)
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
        Q(output__datasets__id=dataset_id) | Q(output__lenses__dataset_id=dataset_id) | Q(output__data_arrays__dataset_id=dataset_id)
    ).values("input_id")
