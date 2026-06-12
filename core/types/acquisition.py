import strawberry
from strawberry import auto
from typing import TYPE_CHECKING, List, Annotated, cast
from core import models, filters
from kante.types import Info
import kante

from core import order

from core.types.auth import ProvenanceEntry, Task

if TYPE_CHECKING:
    from core.types.image import AffineTransformationView, TimepointView, WellPositionView


@kante.django_type(models.Stage, filters=filters.StageFilter, ordering=order.StageOrder, pagination=True)
class Stage:
    id: auto
    affine_views: List[Annotated["AffineTransformationView", strawberry.lazy("core.types.image")]]
    description: str | None
    name: str
    created_through: Task | None = kante.django_field(description="The task this stage was created through, if any")
    provenance_entries: List["ProvenanceEntry"] = kante.django_field(description="Provenance entries for this camera")

    @kante.django_field()
    def pinned(self, info: Info) -> bool:
        return cast(models.Image, self).pinned_by.filter(id=info.context.request.user.id).exists()


@kante.django_type(models.Era, filters=filters.EraFilter, ordering=order.EraOrder, pagination=True)
class Era:
    id: auto
    begin: auto
    views: List[Annotated["TimepointView", strawberry.lazy("core.types.image")]]
    name: str
    created_through: Task | None = kante.django_field(description="The task this era was created through, if any")
    provenance_entries: List["ProvenanceEntry"] = kante.django_field(description="Provenance entries for this camera")


@kante.django_type(
    models.MultiWellPlate,
    filters=filters.MultiWellPlateFilter,
    ordering=order.MultiWellPlateOrder,
    pagination=True,
    fields="__all__",
)
class MultiWellPlate:
    id: auto
    views: List[Annotated["WellPositionView", strawberry.lazy("core.types.image")]]
