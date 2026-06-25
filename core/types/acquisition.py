import strawberry
from strawberry import auto
from typing import TYPE_CHECKING, List, Annotated, cast
from core import models, filters
from kante.types import Info
import kante

from core import order

from core.types.auth import ProvenanceEntry, Task, User

if TYPE_CHECKING:
    from core.types.image import AffineTransformationView, TimepointView, WellPositionView


@kante.django_type(
    models.Stage,
    filters=filters.StageFilter,
    ordering=order.StageOrder,
    pagination=True,
    description="A stage is a 3D space corresponding to the physical space on a microscope during an experiment. Clients use stages to contextualize images according to their real-world physical location via affine transformation views.",
)
class Stage:
    """A stage is a 3D space corresponding to the physical space on a microscope during an experiment. Clients use stages to contextualize images according to their real-world physical location via affine transformation views."""

    id: auto
    affine_views: List[Annotated["AffineTransformationView", strawberry.lazy("core.types.image")]]
    description: str | None
    name: str
    created_through: Task | None = kante.django_field(description="The task this stage was created through, if any")
    created_through_by: User | None = kante.django_field(description="The assigner of the creating task, if any")
    provenance_entries: List["ProvenanceEntry"] = kante.django_field(description="Provenance entries for this stage")

    @kante.django_field()
    def pinned(self, info: Info) -> bool:
        return cast(models.Image, self).pinned_by.filter(id=info.context.request.user.id).exists()


@kante.django_type(
    models.Era,
    filters=filters.EraFilter,
    ordering=order.EraOrder,
    pagination=True,
    description="An era is a time space corresponding to an epoch on a microscope during an experiment. Clients use eras to contextualize images in real-world time via timepoint views.",
)
class Era:
    """An era is a time space corresponding to an epoch on a microscope during an experiment. Clients use eras to contextualize images in real-world time via timepoint views."""

    id: auto
    begin: auto
    views: List[Annotated["TimepointView", strawberry.lazy("core.types.image")]]
    name: str
    created_through: Task | None = kante.django_field(description="The task this era was created through, if any")
    created_through_by: User | None = kante.django_field(description="The assigner of the creating task, if any")
    provenance_entries: List["ProvenanceEntry"] = kante.django_field(description="Provenance entries for this era")


@kante.django_type(
    models.MultiWellPlate,
    filters=filters.MultiWellPlateFilter,
    ordering=order.MultiWellPlateOrder,
    pagination=True,
    fields="__all__",
    description="A multi-well plate with a grid of rows and columns used during acquisition. Clients use it to locate images within specific wells via well position views.",
)
class MultiWellPlate:
    """A multi-well plate with a grid of rows and columns used during acquisition. Clients use it to locate images within specific wells via well position views."""

    id: auto
    views: List[Annotated["WellPositionView", strawberry.lazy("core.types.image")]]
