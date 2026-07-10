from kante.types import Info
import kante
import strawberry
from pydantic import BaseModel, Field
from core import types, models
from core.render.inputs.types import RenderTreeInput
from core.mutations._generic import make_delete


def traverse_context_tree(tree, collection: list[str]):
    if getattr(tree, "context", None) is not None:
        collection.append(tree.context)

    if tree.children is None:
        return
    for child in tree.children:

        traverse_context_tree(child, collection)


def create_render_tree(
    info: Info,
    input: RenderTreeInput,
) -> types.RenderTree:

    collection = []

    traverse_context_tree(input.tree, collection)

    contexts = models.RGBRenderContext.objects.filter(id__in=collection)

    context = models.RenderTree.objects.create(
        name=input.name,
        tree=strawberry.asdict(input.tree),
        organization=info.context.request.organization,
    )

    context.linked_contexts.set(contexts)

    return context


class DeleteRenderTreeInputModel(BaseModel):
    id: str = Field(description="The ID of the render tree to delete")


@kante.pydantic_input(DeleteRenderTreeInputModel, description="Input for deleting a render tree by ID")
class DeleteRenderTreeInput:
    """Input for deleting a render tree by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the render tree to delete")


delete_render_tree = make_delete(models.RenderTree, DeleteRenderTreeInput)
