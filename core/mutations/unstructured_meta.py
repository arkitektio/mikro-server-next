from kante.types import Info
import strawberry
from core import types, models, scalars


@strawberry.input
class UnstructuredMetaInput:
    name: str
    meta: scalars.Any
    file: strawberry.ID
    schema: strawberry.ID | None = None


def attach_unstructured_meta(
    info: Info,
    input: UnstructuredMetaInput,
) -> types.UnstructuredMeta:
    view = models.UnstructuredMeta.objects.create(
        file_id=input.file,
        name=input.name,
        meta=input.meta,
        schema_id=input.schema,
    )
    return view
