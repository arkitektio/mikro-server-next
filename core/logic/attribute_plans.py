"""Building attribute plans: the read side the FIELD edge implies (RFC-7).

A FIELD edge records that a label mask's pixels *are* the map into a table of objects, so
"what is under this pixel, and what do we know about it?" is a graph question. This module
answers it with a **plan**, never a value: the server names the array to sample, the axes to
sample it on, the parquet to query and the columns to select, and a zarr+duckdb worker --
in the browser, or anywhere -- executes it with credentials it already has. The server reads
no store: there is no zarr, numpy or duckdb import here, and there must never be one.

A plan takes no coordinate, on purpose. "Sample the mask, that gives `i`; look up `i` in
that parquet" is the same plan for every pixel, so a client fetches it once and executes it
per hover, locally, with zero round-trips -- it is already rendering the mask, so it already
has the chunk. A coord-bearing query would be one request per pixel and could never beat
the client reading its own pixels.

Plans are discovered across the **fact component**, not just at the probed system: probe a
source image and the FIELD edges hanging off the instance mask derived from it are found
through the derivation edge, each plan carrying the ``(edge, inverted)`` path from the
probed system to its root (:func:`core.logic.graph.fact_paths`). The component's fences do
the semantic work -- registrations are never crossed and SHARED systems never stood on (the
walk has no scene), UNMAPPABLE never walks, a rank-changing derivation refuses the backward
hop -- so only grids that honestly correspond to the probed point are reached. FIELD edges
themselves are payload, never connectivity: an affine edge can never land on an INDEX space
(``assert_edge_rank`` refuses metric kinds there), and FIELD is not invertible, so tables
are always leaves. Relations *between* tables are schema facts (``TableColumn.references``),
not edges -- FIELD is the single crossing from geometry into record-land.

A refusal anywhere in the component (a lens-owned field, a storeless array) fails the whole
query, deliberately: the blast radius of a modelling error grows with discovery, and
surfacing it beats silently returning a subset that looks complete.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core import enums, models
from core.logic import graph as graph_logic

if TYPE_CHECKING:
    from authentikate.models import Organization


@dataclass(frozen=True)
class PlanKeySpec:
    """One key binding of a lookup: which sampled/passthrough value binds which parquet column.

    For a depth-1 plan the axis name and the column name coincide by construction (a
    coordinate column and its derived axis are the same fact), but the pair is kept
    explicit: the worker binds *values it holds under axis names* to *columns of a file*,
    and conflating the two namespaces is how off-by-one-table bugs are written.
    """

    axis: str
    column: "models.TableColumn"


@dataclass(frozen=True)
class PlanStepSpec:
    """One step of the path from the probed system to a plan's root: an edge, and its direction."""

    edge: "models.Transformation"
    inverted: bool


@dataclass(frozen=True)
class SampleSpec:
    """The zarr half of a plan: which array to sample, and what its value means."""

    system: "models.CoordinateSystem"
    store: "models.ZarrStore"
    consumes: list[str]
    produces: list[str]
    passthrough: list[str]


@dataclass(frozen=True)
class LookupSpec:
    """The duckdb half of a plan: which parquet to query, keyed and selected how."""

    store: "models.ParquetStore"
    key_columns: list[PlanKeySpec]
    attributes: list["models.TableColumn"]
    sql: str


@dataclass(frozen=True)
class AttributePlanSpec:
    """One executable answer to "what is under this point of `system`?"."""

    edge: "models.Transformation"
    table: "models.TableDataset"
    # Steps from the PROBED system to the FIELD edge's input system -- empty for a plan
    # rooted where the caller probed. Probe-relative, so it lives on the plan and not on
    # the sample step (whose own space can differ again, for a separate warp field).
    path: list[PlanStepSpec]
    sample: SampleSpec
    lookup: LookupSpec


def quote_identifier(name: str) -> str:
    """Quote a column name as a SQL identifier, doubling embedded quotes.

    The one thing standing between a stored column name and the SQL string, so it is a
    named function with its own test rather than an inline expression. Values never pass
    through here -- they are bound as ``?`` placeholders by the worker.
    """
    return '"' + name.replace('"', '""') + '"'


def build_lookup_sql(*, attribute_columns: list["models.TableColumn"], key_columns: list[PlanKeySpec]) -> str:
    """Build the parameterized DuckDB statement for one lookup.

    Identifiers come from validated ``TableColumn`` rows and are quoted; everything else is
    a ``?`` placeholder. Bind order is: the parquet path/URL first (the ``read_parquet``
    argument -- the worker supplies it from its own access grant, so credentials and
    locations never appear in a plan), then the key values in ``key_columns`` order.

    A table whose every column is a coordinate has nothing else to report, so the SELECT
    falls back to the key columns themselves -- the worker still learns the row exists.
    Never ``SELECT *``: the plan says exactly what comes back.
    """
    selected = [column.name for column in attribute_columns] or [key.column.name for key in key_columns]
    select_list = ", ".join(quote_identifier(name) for name in selected)
    where = " AND ".join(f"{quote_identifier(key.column.name)} = ?" for key in key_columns)
    return f"SELECT {select_list} FROM read_parquet(?) WHERE {where}"


def resolve_field_store(system: "models.CoordinateSystem") -> "models.ZarrStore":
    """The zarr store holding the array whose values are the map.

    Two owners resolve: an ARRAY system to its own level's store, an INTRINSIC system to
    the level-0 store (unique per ``(dataset, level)``). A lens-owned system is refused
    rather than guessed -- a lens is "a selection over a dataset, nothing else" and owns no
    array -- and so is anything else (a table's system, a hub): a FIELD standing on those
    is a modelling error this error message should surface, not paper over. Relations
    between tables belong on ``TableColumn.references``.
    """
    if system.lens_id:
        raise ValueError(f"Coordinate system '{system.name}' is lens-owned: a lens is a selection over a dataset and owns no array, so there is nothing to sample. Build the plan from the dataset's own system.")
    if system.data_array_id:
        store = system.data_array.store
    elif system.intrinsic_of_id:
        level_zero = system.intrinsic_of.data_arrays.filter(level=0).first()
        store = level_zero.store if level_zero else None
    else:
        raise ValueError(f"Coordinate system '{system.name}' is not array-backed, so its values cannot be sampled. A map out of a *table* is not a FIELD edge: declare it as a column reference (TableColumn.references) instead.")
    if store is None:
        raise ValueError(f"The array behind coordinate system '{system.name}' has no zarr store, so a worker could not sample it.")
    return store


def build_attribute_plans(
    system: "models.CoordinateSystem",
    organization: "Organization",
    max_depth: int | None = None,
) -> list[AttributePlanSpec]:
    """Every attribute plan reachable from ``system``: one per FIELD edge landing on a table.

    Discovery first (:func:`core.logic.graph.fact_paths`), then one query for the FIELD
    edges rooted at any reached system. Filtered on **input**, not ``field``: a
    self-dereference stores ``field`` as NULL (read through ``effective_field``), and an
    edge pointing *at* a warp field via ``field`` must not be followed -- its output is a
    pixel grid, which the ``table_dataset_id`` guard skips. Pure over ``Transformation``
    rows: nothing here reads a store, which is what makes it testable for real, unlike
    every other parquet path in this codebase.
    """
    paths = graph_logic.fact_paths(system, organization=organization, max_depth=max_depth)

    edges = (
        models.Transformation.objects.filter(
            input_id__in=paths.keys(),
            parent__isnull=True,
            kind=enums.TransformKindChoices.FIELD.value,
            organization=organization,
        )
        .select_related("output__table_dataset__store", "field", "input")
        .prefetch_related("input__axes", "output__axes")
        .order_by("id")
    )

    plans: list[AttributePlanSpec] = []
    for edge in edges:
        output = edge.output
        if output is None or output.table_dataset_id is None:
            continue  # a warp-field target: a pixel grid, not a table
        table = output.table_dataset

        field_system = edge.effective_field
        store = resolve_field_store(field_system)

        consumes = list(edge.input_axes or [])
        produces = list(edge.output_axes or [])
        # Off the EDGE's input system, never the probed one: a discovered plan's root can
        # have different axes than where the caller stands (a (t,c,y,x) image's (t,y,x)
        # mask must pass `t` through, and must not invent a `c`).
        passthrough = [axis.name for axis in edge.input.axes.all() if axis.name not in consumes]

        coordinate_columns = {column.name: column for column in table.columns_by_role(enums.TableColumnRoleChoices.COORDINATE.value)}
        key_columns: list[PlanKeySpec] = []
        for axis in output.axes.all():
            column = coordinate_columns.get(axis.name)
            if column is None:
                # The degenerate table: a synthetic `object` axis enumerating rows, with no
                # backing column to bind. The edge is a real fact (mask values as row
                # numbers), but positional parquet access is not a lookup a plan can state
                # honestly, so no plan -- the same table is also refused as a reference
                # target, for the same reason.
                key_columns = []
                break
            key_columns.append(PlanKeySpec(axis=axis.name, column=column))
        if not key_columns:
            continue

        attributes = [column for column in table.columns.all() if column.role != enums.TableColumnRoleChoices.COORDINATE.value]
        sql = build_lookup_sql(attribute_columns=attributes, key_columns=key_columns)

        plans.append(
            AttributePlanSpec(
                edge=edge,
                table=table,
                path=[PlanStepSpec(edge=step_edge, inverted=inverted) for step_edge, inverted in paths[edge.input_id]],
                sample=SampleSpec(system=field_system, store=store, consumes=consumes, produces=produces, passthrough=passthrough),
                lookup=LookupSpec(store=table.store, key_columns=key_columns, attributes=attributes, sql=sql),
            )
        )

    # Local plans first, then by distance, ties by edge pk -- so a client that only wants
    # what is rooted where it probed reads a stable prefix.
    plans.sort(key=lambda plan: (len(plan.path), plan.edge.pk))
    return plans
