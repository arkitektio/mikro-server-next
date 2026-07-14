"""Queries over the coordinate graph itself, rather than over one of its nodes."""

import strawberry
from kante.types import Info

from core import models, types
from core.logic import graph as graph_logic
from core.scoping import get_for_org


def coordinate_graph(
    info: Info,
    coordinate_system: strawberry.ID,
    max_depth: int | None = None,
) -> types.CoordinateGraph:
    """Walk the coordinate graph out from one system and return the subgraph it reaches.

    The list queries answer "which edges are there"; this answers "which edges relate to
    *this*", which no filter can, because relatedness is transitive and a filter is not. It
    is the one traversal that is not scene-scoped: `Layer.pathToWorld` answers where a layer
    sits in the scene it belongs to, whereas this hands back the neighbourhood -- a dataset's
    pixel grid, its pyramid levels, its lenses, its calibrations, the worlds it is registered
    into, and anything else registered into those.

    It still composes nothing. The subgraph comes back as nodes and directed edges, and
    turning that into a matrix is the client's job, for the same reason it always is: two
    scenes can place the same dataset two different ways.
    """
    root = get_for_org(models.CoordinateSystem, info, id=coordinate_system)

    systems, transformations = graph_logic.traverse(
        root,
        organization=info.context.request.organization,
        max_depth=max_depth,
    )

    return types.CoordinateGraph(root=root, systems=systems, transformations=transformations)
