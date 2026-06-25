from kante.types import Info
import strawberry
from core import types, models, scalars


@strawberry.input(description="Input for attaching free-form JSON metadata to a file")
class UnstructuredMetaInput:
    """Input for attaching free-form JSON metadata to a file"""

    name: str = strawberry.field(description="The name of the metadata entry")
    meta: scalars.Any = strawberry.field(description="The free-form JSON metadata to attach")
    file: strawberry.ID = strawberry.field(description="The ID of the file to attach the metadata to")
    schema: strawberry.ID | None = strawberry.field(default=None, description="The ID of the schema describing the metadata structure")


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
