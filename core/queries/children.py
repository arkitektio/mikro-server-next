
from core import models, types, enums, filters as f, pagination as p, age
import strawberry
from typing import Union
from itertools import chain



def children(info, parent: strawberry.ID, filters: f.DatasetChildrenFilter | None = None) -> list[Union[types.Dataset, types.Image, types.File]]:
    if filters is None:
        filters = f.DatasetChildrenFilter()


    dataset = models.Dataset.objects.get(id=parent)

    images = []

    if not filters.show_children:
        images = dataset.images.filter(origins__isnull=True)




    return list(chain(images, dataset.files.all(), dataset.children.all()))

