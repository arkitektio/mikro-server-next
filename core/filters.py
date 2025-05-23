import strawberry
from core import models, enums, scalars
from strawberry import auto
from typing import Optional
from strawberry_django.filters import FilterLookup
import strawberry_django


@strawberry.input
class IDFilterMixin:
    ids: list[strawberry.ID] | None

    def filter_ids(self, queryset, info):
        if self.ids is None:
            return queryset
        return queryset.filter(id__in=self.ids)


@strawberry.input
class SearchFilterMixin:
    search: str | None

    def filter_search(self, queryset, info):
        if self.search is None:
            return queryset
        return queryset.filter(name__contains=self.search)


@strawberry_django.order(models.Image)
class ImageOrder:
    created_at: auto


@strawberry_django.order(models.ROI)
class ROIOrder:
    created_at: auto


@strawberry_django.order(models.RenderTree)
class RenderTreeOrder:
    created_at: auto


@strawberry_django.filter(models.RenderTree)
class RenderTreeFilter:
    id: auto


@strawberry_django.filter(models.Dataset)
class DatasetFilter(IDFilterMixin, SearchFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]


@strawberry_django.filter(models.File)
class FileFilter(IDFilterMixin, SearchFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]


@strawberry_django.filter(models.Stage)
class StageFilter(IDFilterMixin, SearchFilterMixin):
    id: auto
    kind: auto
    name: Optional[FilterLookup[str]]


@strawberry_django.filter(models.RGBRenderContext)
class RGBContextFilter(IDFilterMixin, SearchFilterMixin):
    id: auto


@strawberry_django.filter(models.MultiWellPlate)
class MultiWellPlateFilter(IDFilterMixin, SearchFilterMixin):
    id: auto


@strawberry_django.filter(models.Era)
class EraFilter:
    id: auto
    begin: auto


@strawberry_django.filter(models.Mesh)
class MeshFilter(IDFilterMixin, SearchFilterMixin):
    id: auto


@strawberry_django.filter(models.Instrument)
class InstrumentFilter:
    id: auto
    name: auto


@strawberry_django.filter(models.Objective)
class ObjectiveFilter:
    id: auto
    name: auto


@strawberry_django.filter(models.Camera)
class CameraFilter:
    id: auto
    name: auto


@strawberry_django.filter(models.MultiWellPlate)
class MultiWellPlateFilter(IDFilterMixin, SearchFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]


@strawberry_django.filter(models.View)
class ViewFilter:
    is_global: auto


@strawberry_django.filter(models.Accessor)
class AccessorFilter:
    keys: auto


@strawberry_django.filter(models.PixelLabel)
class PixelLabelFilter:
    value: float | None = None
    view: strawberry.ID | None = None
    entity_kind: strawberry.ID | None = None
    entity: strawberry.ID | None = None

    def filter_value(self, queryset, info):
        if self.value is None:
            return queryset
        return queryset.filter(value=self.value)

    def filter_view(self, queryset, info):
        if self.view is None:
            return queryset
        return queryset.filter(view_id=self.view)

    def filter_entity_kind(self, queryset, info):
        raise NotImplementedError("Not implemented")

    def filter_entity(self, queryset, info):
        if self.entity is None:
            return queryset
        return queryset.filter(entity=self.entity)


@strawberry_django.filter(models.AffineTransformationView)
class AffineTransformationViewFilter(ViewFilter):
    stage: StageFilter | None
    pixel_size: Optional[FilterLookup[float]]

    def filter_pixel_size(self, queryset, info):
        if self.pixel_size is None:
            return queryset
        return queryset


@strawberry_django.filter(models.TimepointView)
class TimepointViewFilter(ViewFilter):
    era: EraFilter | None
    ms_since_start: auto
    index_since_start: auto


@strawberry_django.filter(models.PixelView)
class PixelViewFilter(ViewFilter):
    pass


@strawberry_django.filter(models.OpticsView)
class OpticsViewFilter(ViewFilter):
    instrument: InstrumentFilter | None
    objective: ObjectiveFilter | None
    camera: CameraFilter | None


@strawberry_django.filter(models.StructureView)
class StructureViewFilter(ViewFilter):
    structure: scalars.StructureString | None

    def filter_structure(self, queryset, info):
        if self.structure is None:
            return queryset
        return queryset.filter(structure=self.structure)


@strawberry_django.filter(models.WellPositionView)
class WellPositionViewFilter(ViewFilter):
    well: MultiWellPlateFilter | None
    row: int | None
    column: int | None


@strawberry_django.filter(models.ContinousScanView)
class ContinousScanViewFilter(ViewFilter):
    direction: auto


@strawberry_django.filter(models.ZarrStore)
class ZarrStoreFilter:
    shape: Optional[FilterLookup[int]]


@strawberry_django.filter(models.Snapshot)
class SnapshotFilter:
    name: Optional[FilterLookup[str]]
    ids: list[strawberry.ID] | None

    def filter_ids(self, queryset, info):
        if self.ids is None:
            return queryset
        return queryset.filter(id__in=self.ids)


@strawberry_django.filter(models.Image)
class ImageFilter:
    name: Optional[FilterLookup[str]]
    ids: list[strawberry.ID] | None
    store: ZarrStoreFilter | None
    dataset: DatasetFilter | None
    transformation_views: AffineTransformationViewFilter | None
    timepoint_views: TimepointViewFilter | None
    not_derived: bool | None = None

    def filter_ids(self, queryset, info):
        if self.ids is None:
            return queryset
        return queryset.filter(id__in=self.ids)

    def filter_not_derived(self, queryset, info):
        if self.not_derived is None:
            return queryset
        return queryset.filter(derived_views=None)


@strawberry_django.filter(models.ROI)
class ROIFilter(IDFilterMixin):
    id: auto
    kind: auto
    image: strawberry.ID | None = None
    search: str | None

    def filter_image(self, queryset, info):
        if self.image is None:
            return queryset
        return queryset.filter(image_id=self.image)

    def filter_search(self, queryset, info):
        if self.search is None:
            return queryset
        return queryset.filter(image__name__contains=self.search)


@strawberry_django.filter(models.Table)
class TableFilter(IDFilterMixin, SearchFilterMixin):
    id: auto
    ids: list[strawberry.ID] | None

    def filter_ids(self, queryset, info):
        if self.ids is None:
            return queryset
        return queryset.filter(id__in=self.ids)


@strawberry.input
class DatasetChildrenFilter:
    show_children: bool | None = None


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


@strawberry_django.filter(models.Experiment)
class ExperimentFilter(IDFilterMixin, SearchFilterMixin):
    id: auto
