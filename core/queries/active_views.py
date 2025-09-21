from itertools import chain
import strawberry
import kante
from core import models, types
from django.db.models import Q
from enum import Enum


@strawberry.enum
class DimSelectorKind(str, Enum):
    SLICE = "SLICE"
    INDICES = "SELECTION"
    ALL = "ALL"
    INDEX = "INDEX"


@strawberry.input
class DimSelector:
    kind: DimSelectorKind
    start: int | None = None
    end: int | None = None
    step: int | None = None
    indices: list[int] | None = None
    index: int | None = None


@strawberry.input
class Selector:
    x: DimSelector | None = None
    y: DimSelector | None = None
    z: DimSelector | None = None
    c: DimSelector | None = None
    t: DimSelector | None = None


def build_dim_selector(selector: DimSelector, field_prefix: str):
    if selector.kind == DimSelectorKind.ALL:
        return Q()

    elif selector.kind == DimSelectorKind.SLICE:
        q = Q()
        if selector.start is not None:
            # Include records where min is None (unbounded) or min >= start
            q &= Q(**{f"{field_prefix}_min__isnull": True}) | Q(**{f"{field_prefix}_min__gte": selector.start})
        if selector.end is not None:
            # Include records where max is None (unbounded) or max <= end
            q &= Q(**{f"{field_prefix}_max__isnull": True}) | Q(**{f"{field_prefix}_max__lte": selector.end})
        return q

    elif selector.kind == DimSelectorKind.INDEX:
        if selector.index is None:
            return Q()
        # Include records where the index falls within [min, max] or either bound is None
        return (Q(**{f"{field_prefix}_min__isnull": True}) | Q(**{f"{field_prefix}_min__lte": selector.index})) & (Q(**{f"{field_prefix}_max__isnull": True}) | Q(**{f"{field_prefix}_max__gte": selector.index}))

    elif selector.kind == DimSelectorKind.INDICES:
        if not selector.indices:
            return Q()
        # Create OR condition for all indices
        combined_q = Q()
        for idx in selector.indices:
            idx_q = (Q(**{f"{field_prefix}_min__isnull": True}) | Q(**{f"{field_prefix}_min__lte": idx})) & (Q(**{f"{field_prefix}_max__isnull": True}) | Q(**{f"{field_prefix}_max__gte": idx}))
            combined_q |= idx_q
        return combined_q

    return Q()


def active_image_views(info: kante.Info, image: strawberry.ID, selector: Selector | None = None, include: list[types.ViewKind] | None = strawberry.UNSET, exclude: list[types.ViewKind] | None = strawberry.UNSET) -> list[types.View]:
    user = info.context.request.user
    if not user.is_authenticated:
        return []

    image = models.Image.objects.get(id=image)

    if include is strawberry.UNSET:
        view_relations = [
            "affine_transformation_views",
            "channel_views",
            "timepoint_views",
            "optics_views",
            "label_views",
            "rgb_views",
            "wellposition_views",
            "continousscan_views",
            "acquisition_views",
            "mask_views",
            "instance_mask_views",
            "reference_views",
            "scale_views",
            "roi_views",
            "file_views",
            "derived_views",
            "histogram_views",
            "lightpath_views",
        ]

        if exclude is not strawberry.UNSET and exclude:
            exclude_relations = [kind.value for kind in exclude]
            view_relations = [rel for rel in view_relations if rel not in exclude_relations]

    else:
        view_relations = [kind.value for kind in include]

    results = []

    for relation in view_relations:
        qs = getattr(image, relation).all()

        if selector:
            if selector.x:
                qs = qs.filter(build_dim_selector(selector.x, "x"))
            if selector.y:
                qs = qs.filter(build_dim_selector(selector.y, "y"))
            if selector.z:
                qs = qs.filter(build_dim_selector(selector.z, "z"))
            if selector.c:
                qs = qs.filter(build_dim_selector(selector.c, "c"))
            if selector.t:
                qs = qs.filter(build_dim_selector(selector.t, "t"))

        results.append(qs)

    return list(chain(*results))
