"""GraphQL types for attribute plans: instructions, never attributes (RFC-7).

Computed types, not django types: a plan is derived from the graph at query time and reads
no store. The server names the array to sample, the axes to sample it on, the parquet to
query and the columns to select; a zarr+duckdb worker executes it with credentials it
already has (the stores' own ``accessGrant``). Anything that wants *values* runs the plan.
"""

from typing import List

import strawberry

import kante
from datalayer.types import ParquetStore, ZarrStore

from core.types.coords import CoordinateSystem, FieldTransformation, PlacementStep
from core.types.table_dataset import TableDataset, TableDatasetColumn


@kante.type(
    description="One key binding of a lookup: the sampled or passthrough value named `axis` binds the parquet column `column`. For a depth-1 plan the two names coincide by construction (a coordinate column and its derived axis are the same fact), but the worker should always bind by this pair: values live under axis names, columns live in a file, and the plan is the bridge"
)
class PlanKeyColumn:
    """One key binding of a lookup step: an axis-named value bound to a parquet column."""

    axis: str = strawberry.field(description="The name the worker holds the value under: a passthrough axis of the sampled array (e.g. `t`) or an axis the sample produced (e.g. `i`)")
    column: TableDatasetColumn = strawberry.field(description="The declared coordinate column this value binds, carrying the parquet column name and its dtype")


@kante.type(
    description="The zarr half of a plan: sample this array at the point's coordinates. The client that is already rendering the array reads the value from the chunk it already has; a headless worker fetches it through the store's access grant. Either way the plan never says what is in the array -- the client owns pixels"
)
class SampleStep:
    """Sample the field array at the point: which array, which axes, what the value means."""

    system: CoordinateSystem = strawberry.field(description="The coordinate system of the array being sampled. Equal to the queried system when the array's own pixels are the map (a label mask); a different, array-backed system when the map is a separate field. `consumes` is stated in this system's axis order")
    store: ZarrStore = strawberry.field(description="The zarr store holding the array (the level-0 store for an intrinsic system). Ask it for an accessGrant to actually read chunks -- credentials never appear in a plan")
    consumes: List[str] = strawberry.field(description="The axes the sample consumes, in the field system's axis order: index the array here with the point's coordinates, e.g. ['y', 'x']")
    produces: List[str] = strawberry.field(description="The axis names the sampled value produces, per-edge: two sibling edges off one mask may name their produced axis differently (`i`, `label_id`), so always zip the value against THIS edge's names, never a shared key set")
    passthrough: List[str] = strawberry.field(description="The axes the edge did not consume, e.g. ['t']: their coordinates pass through by name and join the produced values as lookup keys")


@kante.type(
    description="The duckdb half of a plan: look the sampled value up in the parquet. Bind order for `sql` is the parquet path/URL first (the read_parquet argument, supplied by the worker from its own access grant), then the key values in `keyColumns` order. Do not assume one row per point: (t, i) uniqueness is a convention no unique index backs, so the worker gets rows, plural"
)
class LookupStep:
    """Query the table's parquet for the row(s) the sampled value identifies."""

    store: ParquetStore = strawberry.field(description="The parquet store holding the rows. Ask it for an accessGrant to actually read it -- credentials and locations never appear in a plan")
    key_columns: List[PlanKeyColumn] = strawberry.field(description="The key bindings, in bind order: each names the value the worker holds (by axis name) and the parquet column it binds")
    attributes: List[TableDatasetColumn] = strawberry.field(description="What the SQL selects -- every declared non-coordinate column, never `*`. A column whose `references` names another table holds row ids of that table; following them is the client's choice, one more lookup away")
    sql: str = strawberry.field(description="The parameterized DuckDB statement: identifiers from validated declared columns and quoted, values as `?` placeholders, never interpolated. Bind the parquet path first, then the key values in `keyColumns` order. A non-duckdb consumer ignores this and reads `keyColumns` + `attributes` instead")


@kante.type(
    description="One executable answer to 'what is under this point?': map the point along `path` if the plan is not rooted where you probed, sample the field array, then look the value up in the table's parquet. Plans are discovered across the fact component -- probe a source image and the plans of the instance mask derived from it are found through the derivation edge -- but never through a registration: which claims compose is a scene's say-so, and this query has no scene. A plan takes no coordinate -- it is the same plan for every point, so fetch it once, cache it, and execute per hover locally with zero round-trips. attributePlans returns instructions, never attributes: anything that wants values runs the plan"
)
class AttributePlan:
    """A coordinate-free recipe: map along the path, sample the field array, look the value up."""

    edge: FieldTransformation = strawberry.field(description="The FIELD edge this plan was built from. The plan's cache key is this edge's (id, version) together with every `path` step's transformation (id, version): the stores and columns of a table are written once, so a deleted or version-bumped edge -- the FIELD, or any step on the way to it -- is the only thing that can stale a cached plan")
    table: TableDataset = strawberry.field(description="The table the plan lands in: the home of the attributes, its columns and their `references`")
    path: List[PlacementStep] = strawberry.field(
        description="The steps from the PROBED system to this plan's root (the FIELD edge's input system -- equal to `sample.system` when the mask's own pixels are the map). Empty when the plan is rooted where you probed. Compose in order, inverting the flagged steps, to map a probed-space point into the space `consumes` and `passthrough` are stated in -- the same contract as `pathToWorld`. The path crosses derivations, levels, lenses and calibrations, never a registration"
    )
    sample: SampleStep = strawberry.field(description="The zarr half: sample the field array at the (path-mapped) point")
    lookup: LookupStep = strawberry.field(description="The duckdb half: look the sampled value up in the parquet")
