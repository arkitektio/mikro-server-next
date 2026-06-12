from core import models, types, filters as f, pagination as p
from core.utils import paginate_querysets
import strawberry
from typing import Union
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from enum import Enum
from core.scoping import get_for_org


@strawberry.enum
class ChildrenOrderField(str, Enum):
    CREATED_AT = "created_at"
    NAME = "name"
    UPDATED_AT = "updated_at"


@strawberry.enum
class ChildrenOrderDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


@strawberry.input
class ChildrenOrder:
    field: ChildrenOrderField
    direction: ChildrenOrderDirection


def children(info, parent: strawberry.ID, filters: f.DatasetChildrenFilter | None = None, pagination: p.ChildrenPaginationInput | None = None, order: ChildrenOrder | None = None) -> list[Union[types.Dataset, types.Image, types.File]]:
    if filters is None:
        filters = f.DatasetChildrenFilter()
    if pagination is None:
        pagination = p.ChildrenPaginationInput()

    dataset = get_for_org(models.Dataset, info, id=parent)

    images = dataset.images.all()
    children = dataset.children.all()
    files = dataset.files.all()

    if filters.search and filters.search.strip():
        search_vector = SearchVector("name", "description")
        search_query = SearchQuery(filters.search)

        images = images.annotate(search=search_vector, rank=SearchRank(search_vector, search_query)).filter(search=search_query).order_by("-rank")

        children = children.annotate(search=search_vector, rank=SearchRank(search_vector, search_query)).filter(search=search_query).order_by("-rank")

        files = files.annotate(search=SearchVector("name"), rank=SearchRank(SearchVector("name"), search_query)).filter(search=search_query).order_by("-rank")

    if order:
        order_prefix = "" if order.direction == ChildrenOrderDirection.ASC else "-"
        order_field = order.field.value

        images = images.order_by(f"{order_prefix}{order_field}")
        children = children.order_by(f"{order_prefix}{order_field}")
        files = files.order_by(f"{order_prefix}{order_field}")

    return paginate_querysets(
        images,
        children,
        files,
        limit=pagination.limit,
        offset=pagination.offset,
    )
