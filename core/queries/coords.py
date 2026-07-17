"""Queries over the coordinate graph itself, rather than over one of its nodes."""

import strawberry
from kante.types import Info

from core import models, types
from core.logic import attribute_plans as attribute_plans_logic
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


def attribute_plans(info: Info, system: strawberry.ID, max_depth: int | None = None) -> list[types.AttributePlan]:
    """Every attribute plan reachable from one system: one per FIELD edge landing on a table.

    The server returns a plan; a worker executes it. The plan names the array to sample,
    the axes to sample it on, the parquet to query and the columns to select -- and takes
    no coordinate, so a client fetches it once and executes it per hover, locally, against
    the mask chunks it is already rendering. Plans are discovered across the fact
    component -- probe a source image and the derived instance mask's plans come back,
    each carrying the `path` of steps to its root -- but never through a registration.
    Scene-independent by construction, like `coordinateGraph`: a table's space is not
    scene-owned, so no `scene:` argument exists to be wrong about.
    """
    root = get_for_org(models.CoordinateSystem, info, id=system)
    specs = attribute_plans_logic.build_attribute_plans(root, organization=info.context.request.organization, max_depth=max_depth)

    return [
        types.AttributePlan(
            edge=spec.edge,
            table=spec.table,
            path=[types.PlacementStep(transformation=step.edge, inverted=step.inverted) for step in spec.path],
            sample=types.SampleStep(
                system=spec.sample.system,
                store=spec.sample.store,
                consumes=spec.sample.consumes,
                produces=spec.sample.produces,
                passthrough=spec.sample.passthrough,
            ),
            lookup=types.LookupStep(
                store=spec.lookup.store,
                key_columns=[types.PlanKeyColumn(axis=key.axis, column=key.column) for key in spec.lookup.key_columns],
                attributes=spec.lookup.attributes,
                sql=spec.lookup.sql,
            ),
        )
        for spec in specs
    ]
