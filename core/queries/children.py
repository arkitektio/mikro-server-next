from core import models, types, enums, filters as f, pagination as p
from core.utils import paginate_querysets
import strawberry
from typing import Union
from itertools import chain
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank


def children(
    info,
    parent: strawberry.ID,
    filters: f.DatasetChildrenFilter | None = None,
    pagination: p.ChildrenPaginationInput | None = None,
) -> list[Union[types.Dataset, types.Image, types.File]]:
    if filters is None:
        filters = f.DatasetChildrenFilter()
    if pagination is None:
        pagination = p.ChildrenPaginationInput()

    dataset = models.Dataset.objects.get(id=parent)

    images = dataset.images.all()
    children = dataset.children.all()
    files = dataset.files.all()

    if filters.search and filters.search.strip():
        search_vector = SearchVector("name", "description")
        search_query = SearchQuery(filters.search)

        images = images.annotate(search=search_vector, rank=SearchRank(search_vector, search_query)).filter(search=search_query).order_by("-rank")

        children = children.annotate(search=search_vector, rank=SearchRank(search_vector, search_query)).filter(search=search_query).order_by("-rank")

        files = files.annotate(search=SearchVector("name"), rank=SearchRank(SearchVector("name"), search_query)).filter(search=search_query).order_by("-rank")

    return paginate_querysets(
        images,
        children,
        files,
        limit=pagination.limit,
        offset=pagination.offset,
    )
