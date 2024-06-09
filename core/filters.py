import strawberry
from core import models
from koherent.strawberry.filters import ProvenanceFilter
from strawberry import auto
from typing import Optional
from strawberry_django.filters import FilterLookup

print("Test")


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


@strawberry.django.order(models.Image)
class ImageOrder:
    created_at: auto

@strawberry.django.order(models.RenderTree)
class RenderTreeOrder:
    created_at: auto

@strawberry.django.filter(models.RenderTree)
class RenderTreeFilter:
    id: auto
    provenance: ProvenanceFilter | None


@strawberry.django.filter(models.Dataset)
class DatasetFilter:
    id: auto
    name: Optional[FilterLookup[str]]
    provenance: ProvenanceFilter | None


@strawberry.django.filter(models.File)
class FileFilter:
    id: auto
    name: Optional[FilterLookup[str]]
    provenance: ProvenanceFilter | None


@strawberry.django.filter(models.Stage)
class StageFilter(IDFilterMixin, SearchFilterMixin):
    id: auto
    kind: auto
    name: Optional[FilterLookup[str]]
    provenance: ProvenanceFilter | None


@strawberry.django.filter(models.RGBRenderContext)
class RGBContextFilter(IDFilterMixin, SearchFilterMixin):
    id: auto
    provenance: ProvenanceFilter | None


@strawberry.django.filter(models.MultiWellPlate)
class MultiWellPlateFilter(IDFilterMixin, SearchFilterMixin):
    id: auto
    provenance: ProvenanceFilter | None

@strawberry.django.filter(models.Era)
class EraFilter:
    id: auto
    begin: auto
    provenance: ProvenanceFilter | None


@strawberry.django.filter(models.Instrument)
class InstrumentFilter:
    id: auto
    name: auto
    provenance: ProvenanceFilter | None


@strawberry.django.filter(models.Objective)
class ObjectiveFilter:
    id: auto
    name: auto
    provenance: ProvenanceFilter | None


@strawberry.django.filter(models.Camera)
class CameraFilter:
    id: auto
    name: auto
    provenance: ProvenanceFilter | None


@strawberry.django.filter(models.Fluorophore)
class FluorophoreFilter:
    id: auto
    emission_wavelength: Optional[FilterLookup[int]]
    excitation_wavelength: Optional[FilterLookup[int]]
    provenance: ProvenanceFilter | None
    search: str | None
    ids: list[strawberry.ID] | None

    def filter_ids(self, queryset, info):
        print(self.ids)
        if self.ids is None:
            return queryset
        return queryset.filter(id__in=self.ids)

    def filter_search(self, queryset, info):
        print(self.search)
        if self.search is None:
            return queryset
        return queryset.filter(name__icontains=self.search)


@strawberry.django.filter(models.Antibody)
class AntibodyFilter(IDFilterMixin, SearchFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]


@strawberry.django.filter(models.MultiWellPlate)
class MultiWellPlateFilter(IDFilterMixin, SearchFilterMixin):
    id: auto
    name: Optional[FilterLookup[str]]


@strawberry.django.filter(models.View)
class ViewFilter:
    is_global: auto
    provenance: ProvenanceFilter | None


@strawberry.django.filter(models.AffineTransformationView)
class AffineTransformationViewFilter(ViewFilter):
    stage: StageFilter | None
    pixel_size: Optional[FilterLookup[float]]

    def filter_pixel_size(self, queryset, info):
        if self.pixel_size is None:
            return queryset
        return queryset


@strawberry.django.filter(models.TimepointView)
class TimepointViewFilter(ViewFilter):
    era: EraFilter | None
    ms_since_start: auto
    index_since_start: auto


@strawberry.django.filter(models.OpticsView)
class OpticsViewFilter(ViewFilter):
    instrument: InstrumentFilter | None
    objective: ObjectiveFilter | None
    camera: CameraFilter | None


@strawberry.django.filter(models.WellPositionView)
class WellPositionViewFilter(ViewFilter):
    well: MultiWellPlateFilter | None
    row: int | None
    column: int | None


@strawberry.django.filter(models.ContinousScanView)
class ContinousScanViewFilter(ViewFilter):
    direction: auto


@strawberry.django.filter(models.ZarrStore)
class ZarrStoreFilter:
    shape: Optional[FilterLookup[int]]


@strawberry.django.filter(models.Snapshot)
class SnapshotFilter:
    name: Optional[FilterLookup[str]]
    ids: list[strawberry.ID] | None

    def filter_ids(self, queryset, info):
        if self.ids is None:
            return queryset
        return queryset.filter(id__in=self.ids)


@strawberry.django.filter(models.Image)
class ImageFilter:
    name: Optional[FilterLookup[str]]
    ids: list[strawberry.ID] | None
    store: ZarrStoreFilter | None
    dataset: DatasetFilter | None
    transformation_views: AffineTransformationViewFilter | None
    timepoint_views: TimepointViewFilter | None

    provenance: ProvenanceFilter | None

    def filter_ids(self, queryset, info):
        if self.ids is None:
            return queryset
        return queryset.filter(id__in=self.ids)


@strawberry.django.filter(models.ROI)
class ROIFilter:
    id: auto
    kind: auto
