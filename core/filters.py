import strawberry
from core import models, enums, scalars
from strawberry import auto
from typing import Optional
from strawberry_django.filters import FilterLookup
from kante.types import Info
import strawberry_django
from django.db.models import Q


@strawberry.input
class ChannelInfoFilter:
    search: Optional[str] = None
    ids: Optional[list[strawberry.ID]] = None



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
    
  

@strawberry.input
class ScopeFilter:
    public: bool | None = None
    org: bool | None = None
    shared: bool | None = None
    me: bool | None = None
  
    


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


@strawberry_django.filter_type(models.File)
class FileFilter:
    id: auto
    ids: list[strawberry.ID] | None = None
    search: Optional[str] = None
    name: Optional[FilterLookup[str]]
    
    
    @strawberry_django.filter_field(filter_none=True)
    def scope(self, info: Info, value: enums.ScopeKind, prefix) -> Q:
        print(f"Scope filter value: {value}")
        if value == None:
            # If no scope is provided, default to the organization of the request
            return Q(**{f"{prefix}organization": info.contex.request.organization})
        
        if value == enums.ScopeKind.PUBLIC:
            return Q(**{f"{prefix}is_public": True})
        
        if value == enums.ScopeKind.ORG:
            return Q(**{f"{prefix}organization": info.context.request.organization})
        
        if value == enums.ScopeKind.SHARED:
            # Shared scope filtering is not implemented
            raise NotImplementedError("Shared scope filtering not implemented")
        
        if value == enums.ScopeKind.ME:
            return Q(**{f"{prefix}creator": info.context.request.user})
        
        
        
        raise ValueError(f"Invalid scope value: {value}")
    
    
    @strawberry_django.filter_field()
    def search(self, info: Info, value: str, prefix) -> Q:
        
        return Q(**{f"{prefix}name__icontains": value})
    
    
    @strawberry_django.filter_field()
    def ids(self, info: Info, value: list[strawberry.ID], prefix) -> Q:
        print(f"IDs filter value: {value}") 
        return Q(**{f"{prefix}id__in": value})
    
    
        

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
    scope: ScopeFilter | None = None
    name: Optional[FilterLookup[str]]
    ids: list[strawberry.ID] | None
    store: ZarrStoreFilter | None
    dataset: DatasetFilter | None
    transformation_views: AffineTransformationViewFilter | None
    timepoint_views: TimepointViewFilter | None
    not_derived: bool | None = None

    def filter_scope(self, queryset, info):
        if self.scope is None:
            return queryset
        if self.scope.public:
            queryset = queryset.filter(is_public=True)
        if self.scope.org:
            queryset = queryset.filter(org=info.context.request.user.active_org)
        if self.scope.shared:
            # django guardian of shared objects
            raise NotImplementedError("Shared scope filtering not implemented")
        if self.scope.me:
            queryset = queryset.filter(creator=info.context.request.user)
        return queryset

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
