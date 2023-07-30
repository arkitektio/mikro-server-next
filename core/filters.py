import strawberry
from core import models
from koherent.filters import ProvenanceFilter
from strawberry import auto
from typing import Optional
from strawberry_django.filters import FilterLookup


@strawberry.django.order(models.Image)
class ImageOrder:
    created_at: auto


@strawberry.django.filter(models.Dataset)
class DatasetFilter:
    id: auto
    name: Optional[FilterLookup[str]]
    provenance: ProvenanceFilter | None


@strawberry.django.filter(models.Stage)
class StageFilter:
    id: auto
    kind: auto
    name: Optional[FilterLookup[str]]
    provenance: ProvenanceFilter | None


@strawberry.django.filter(models.Image)
class ImageFilter:
    dataset: DatasetFilter | None
    provenance: ProvenanceFilter | None


@strawberry.django.filter(models.ROI)
class ROIFilter:
    id: auto
    kind: auto


@strawberry.django.filter(models.View)
class ViewFilter:
    is_global: bool | None
    provenance: ProvenanceFilter | None

    def filter_is_global(self, queryset, info):
        if self.is_global is None:
            return queryset
        if self.is_global:
            return queryset.filter(
                x_min=None,
                x_max=None,
                y_min=None,
                y_max=None,
                z_min=None,
                z_max=None,
                t_min=None,
                t_max=None,
                c_min=None,
                c_max=None,
            )

        return queryset.exclude(
            x_min=None,
            x_max=None,
            y_min=None,
            y_max=None,
            z_min=None,
            z_max=None,
            t_min=None,
            t_max=None,
            c_min=None,
            c_max=None,
        )
