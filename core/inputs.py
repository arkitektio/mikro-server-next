import strawberry_django
from core import models
from typing import List, Optional
from strawberry import ID
import strawberry
import kante
from core import base_models


@strawberry_django.input(models.Image)
class ImageInput:
    origins: Optional[List[ID]]
    dataset: Optional[ID]
    creator: ID


@strawberry_django.input(models.Dataset)
class DatasetInput:
    name: str
    description: str


@strawberry.input()
class AssociateInput:
    selfs: List[strawberry.ID]
    other: strawberry.ID


@strawberry.input()
class DesociateInput:
    selfs: List[strawberry.ID]
    other: strawberry.ID


@kante.pydantic_input(base_models.SliceInputModel, description="Input type for a dimension descriptor, which specifies a key and a kind for a dimension")
class SliceInput:
    dim: str = strawberry.field(description="The key of the dimension, e.g. 'x', 'y', 'z', 'c', or 't'")
    start: int | None = strawberry.field(default=None, description="The starting index of the slice, or None to start from the beginning")
    stop: int | None = strawberry.field(default=None, description="The stopping index of the slice, or None to go to the end")
    step: int | None = strawberry.field(default=None, description="The step size of the slice, or None to use the default step")
