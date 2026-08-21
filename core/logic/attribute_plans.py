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
are always leaves. Relations *between* tables are schema facts (``Column.references``),
not edges -- FIELD is the single crossing from geometry into record-land.

A refusal anywhere in the component (a lens-owned field, a storeless array) fails the whole
query, deliberately: the blast radius of a modelling error grows with discovery, and
surfacing it beats silently returning a subset that looks complete.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable

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
    column: "models.Column"


@dataclass(frozen=True)
class PlanStepSpec:
    """One step of the path from the probed system to a plan's root: an edge, and its direction."""

    edge: "models.Transformation"
    inverted: bool


@dataclass(frozen=True)
class SampleSpec:
    """The first half of a plan: where the id comes from, and what it means.

    ``store`` discriminates the two substrates on its own, so there is no ``kind`` beside
    it to disagree with it: a ``ZarrStore`` is an array the worker samples at a coordinate,
    a ``FabriksStore`` is a collection whose geometry already carries the id.
    """

    system: "models.CoordinateSystem"
    store: "models.ZarrStore | models.FabriksStore"
    consumes: list[str]
    produces: list[str]
    passthrough: list[str]


@dataclass(frozen=True)
class LookupSpec:
    """The second half of a plan: where the id lands, and how to read it there.

    **Two shapes, flat with a discriminator**, for the reason the stored colouring is flat: a
    GraphQL interface over these would carry almost nothing in common -- one has SQL and key
    columns over a parquet, the other two axes over a zarr group and no database anywhere near
    it -- and every client reading a plan would gain a fragment for the privilege.

    * ``kind="TABLE"``: the duckdb half. One row per id, selected by a parameterized statement.
    * ``kind="SPARSE"``: two reads of a sparse store. The id selects a *slice* rather than a
      row, so what comes back is every position along the other axes with a value -- which is
      exactly what "what is in this object" means for a matrix, at any rank.
    """

    kind: str = "TABLE"

    # (TABLE)
    store: "models.ParquetStore | None" = None
    key_columns: list[PlanKeySpec] = field(default_factory=list)
    attributes: list["models.Column"] = field(default_factory=list)
    sql: str | None = None

    # (SPARSE) The layout to read, and the two axes that do different jobs. `key_axis` is bound
    # from the sample exactly as `key_columns` are, and **must be the axis that layout's `indptr`
    # indexes** -- that is what makes the read one contiguous range rather than a scan, and a
    # plan is rooted in a layout where it holds or not at all. `value_axes` are what comes back
    # indexed by: not keys, because the client supplies no value for them and receives every
    # position.
    #
    # The *array* rather than the store, because both layouts of a matrix live in one prefix:
    # the store says where the bytes are and `sparse_array.path` says which child of it to open.
    #
    # `value_axes` is plural because the axes other than the key are however many the matrix has
    # left: one at rank two, two at rank three. The client unravels a returned position into one
    # coordinate per entry, in order, through `sparse_array.path`'s recorded `index_order`.
    sparse_array: "models.SparseArray | None" = None
    key_axis: str | None = None
    value_axes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AttributePlanSpec:
    """One executable answer to "what is under this point of `system`?"."""

    edge: "models.Transformation"
    # Steps from the PROBED system to the FIELD edge's input system -- empty for a plan
    # rooted where the caller probed. Probe-relative, so it lives on the plan and not on
    # the sample step (whose own space can differ again, for a separate warp field).
    path: list[PlanStepSpec]
    sample: SampleSpec
    lookup: LookupSpec
    # Where the id lands. One or the other, never both -- `lookup.kind` says which, and a
    # nullable pair rather than a union for the reason `LookupSpec` gives. Last because they
    # carry defaults, which a dataclass requires of every field after the first one that has one.
    table: "models.TableDataset | None" = None
    sparse_dataset: "models.SparseDataset | None" = None


def quote_identifier(name: str) -> str:
    """Quote a column name as a SQL identifier, doubling embedded quotes.

    The one thing standing between a stored column name and the SQL string, so it is a
    named function with its own test rather than an inline expression. Values never pass
    through here -- they are bound as ``?`` placeholders by the worker.
    """
    return '"' + name.replace('"', '""') + '"'


def build_lookup_sql(*, attribute_columns: list["models.Column"], key_columns: list[PlanKeySpec]) -> str:
    """Build the parameterized DuckDB statement for one lookup.

    Identifiers come from validated ``Column`` rows and are quoted; everything else is
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


def resolve_field_store(system: "models.CoordinateSystem") -> "models.ZarrStore | models.FabriksStore":
    """The store holding whatever carries the ids: an array's zarr, or a collection's fabriks.

    Three owners resolve. An ARRAY system answers with its own level's store and an
    INTRINSIC system with the level-0 store (unique per ``(dataset, level)``) -- both zarr,
    both sampled at a coordinate. A **mesh collection**'s system answers with its fabriks
    store, and nothing is sampled there: the ids ride on the geometry rows, so a client that
    picked a surface already holds one. The store is named anyway because a headless worker
    that did not do the picking needs somewhere to read the object catalog from.

    Whether the system carries a map at all is
    :func:`core.logic.graph.assert_field_is_dereferenceable`, the same check
    ``build_registration_edge`` runs when the edge is written -- shared so the two cannot
    drift, and so a modelling error (a FIELD standing on a table, whose honest form is
    ``Column.references``) reads the same whether it is caught at write or at read.
    What stays here is the *store*, which an array legitimately acquires after its row
    exists and so cannot be demanded at write time.
    """
    graph_logic.assert_field_is_dereferenceable(system)

    # A level living here answers first, and a dataset second: a downsampled level has a
    # space of its own, while level 0 shares the dataset's, so asking the arrays first gets
    # the right store either way without a special case for the shared node.
    array = next(iter(system.data_arrays.all()[:1]), None)
    if array is not None:
        store = array.store
    else:
        dataset = next(iter(system.datasets.all()[:1]), None)
        if dataset is not None:
            level_zero = dataset.data_arrays.filter(level=0).first()
            store = level_zero.store if level_zero else None
        else:
            # A collection, which the guard above already established is what is left.
            # `store` is a non-null FK, so there is no storeless-collection case to refuse:
            # a collection whose bytes are not addressable is not a collection.
            collection = next(iter(system.mesh_collections.all()[:1]))
            store = collection.store
    if store is None:
        raise ValueError(f"The array behind coordinate system '{system.name}' has no zarr store, so a worker could not sample it.")
    return store


def field_edges_from(
    system: "models.CoordinateSystem",
    organization: "Organization",
    max_depth: int | None = None,
    excluding: "Iterable[int]" = (),
) -> tuple[dict, Iterable["models.Transformation"]]:
    """The FIELD edges rooted anywhere fact-reachable from ``system``, and the paths that reached them.

    Discovery first (:func:`core.logic.graph.fact_paths`), then one query for the edges.
    Filtered on **input**, not ``field``: a self-dereference stores ``field`` as NULL (read
    through ``effective_field``), and an edge pointing *at* a warp field via ``field`` must
    not be followed -- its output is a pixel grid, which callers skip by asking for a table.
    Pure over ``Transformation`` rows: nothing here reads a store, which is what makes it
    testable for real, unlike every other parquet path in this codebase.

    ``excluding`` answers a hypothetical rather than a fact: *would* these tables still be
    reachable if those edges were gone. Deleting a FIELD edge is the one operation that can
    strand a picker entry which was valid when it was written, and the only honest way to know
    is to ask the walk without the edge -- guessing from the edge alone is wrong the moment a
    rival edge (RFC-9 allows them) still provides the crossing.
    """
    paths = graph_logic.fact_paths(system, organization=organization, max_depth=max_depth)

    edges = (
        models.Transformation.objects.filter(
            input_id__in=paths.keys(),
            parent__isnull=True,
            kind=enums.TransformKindChoices.FIELD.value,
            organization=organization,
        )
        .exclude(pk__in=list(excluding))
        .select_related("field", "input", "output").prefetch_related("output__table_datasets__store")
        .prefetch_related("input__axes", "output__axes")
        .order_by("id")
    )
    return paths, edges


def field_reachable_tables(
    system: "models.CoordinateSystem",
    organization: "Organization",
    max_depth: int | None = None,
    excluding: "Iterable[int]" = (),
) -> dict[str, "models.TableDataset"]:
    """The tables ``system``'s pixels can be dereferenced into, keyed by id.

    The same relation :func:`build_attribute_plans` publishes, without resolving any store:
    a boundary that only needs to know *whether* the edge exists must not fail because the
    mask's zarr store has not been filled in yet.

    **A product-space table is not reachable in this sense**, even though its edge is real. Its
    row is identified by a pair and this source supplies one half, so nothing standing in
    ``system`` can resolve a row: not a plan (see :func:`build_attribute_plans`), and not a
    colouring either, which is why the filter lives here rather than in one of them. Both the
    picker's options query and the mutation that writes an entry validate against this
    function, so excluding it once keeps "the set offered is the set accepted" true -- putting
    the filter in only one of them is precisely how that invariant breaks.

    What such a table can answer is a *slice* rather than a row, and that wants a source that
    states which slice. A sparse colouring does, by naming the position along the identified
    axis; a column colouring has nowhere to put one.
    """
    _, edges = field_edges_from(system, organization, max_depth=max_depth, excluding=excluding)
    candidates: dict[str, "models.TableDataset"] = {}
    for edge in edges:
        output = edge.output
        table = next(iter(output.table_datasets.all()[:1]), None) if output is not None else None
        if table is not None:
            candidates[str(table.pk)] = table

    excluded = graph_logic.product_space_tables(candidates.values())
    return {key: table for key, table in candidates.items() if table.pk not in excluded}


def field_reachable_sparse_datasets(
    system: "models.CoordinateSystem",
    organization: "Organization",
    max_depth: int | None = None,
    excluding: "Iterable[int]" = (),
) -> dict[str, "models.SparseDataset"]:
    """The sparse matrices ``system``'s ids can index into, keyed by id.

    The sibling of :func:`field_reachable_tables` over the other kind of target, sharing the one
    walk rather than repeating it -- a FIELD edge is a FIELD edge, and what differs is only what
    it lands in.

    A sibling rather than a generalisation of that function, because the two are consumed
    differently and merging them would mean every caller re-splitting the result: a table
    colouring names a column and a sparse one names a position, and no caller wants both in one
    dict keyed by ids from two id spaces.

    Unlike a table, a product-space *matrix* is not excluded here -- being indexed on one axis
    and identified on the other is what a sparse dataset **is**, and a sparse colouring says
    which slice it means. That is the whole difference between the two variants.
    """
    _, edges = field_edges_from(system, organization, max_depth=max_depth, excluding=excluding)
    datasets: dict[str, "models.SparseDataset"] = {}
    for edge in edges:
        output = edge.output
        dataset = next(iter(output.sparse_datasets.all()[:1]), None) if output is not None else None
        if dataset is not None:
            datasets[str(dataset.pk)] = dataset
    return datasets


def build_attribute_plans(
    system: "models.CoordinateSystem",
    organization: "Organization",
    max_depth: int | None = None,
) -> list[AttributePlanSpec]:
    """Every attribute plan reachable from ``system``: one per FIELD edge landing on a table."""
    paths, edges = field_edges_from(system, organization, max_depth=max_depth)

    # One query for the whole set rather than one per edge: whether a target is a product space
    # is a schema fact about its columns, and asking it inside the loop is an N+1 that grows
    # with the graph. See `graph_logic.product_space_tables`.
    product_spaces = graph_logic.product_space_tables(
        table for edge in edges if edge.output is not None for table in edge.output.table_datasets.all()[:1]
    )

    plans: list[AttributePlanSpec] = []
    for edge in edges:
        output = edge.output
        table = next(iter(output.table_datasets.all()[:1]), None) if output is not None else None
        matrix = next(iter(output.sparse_datasets.all()[:1]), None) if output is not None else None
        if table is None and matrix is None:
            continue  # a warp-field target: a pixel grid, and neither record-land nor a matrix

        field_system = edge.effective_field
        store = resolve_field_store(field_system)

        consumes = list(edge.input_axes or [])
        produces = list(edge.output_axes or [])
        # Off the EDGE's input system, never the probed one: a discovered plan's root can
        # have different axes than where the caller stands (a (t,c,y,x) image's (t,y,x)
        # mask must pass `t` through, and must not invent a `c`).
        passthrough = [axis.name for axis in edge.input.axes.all() if axis.name not in consumes]

        if matrix is not None:
            # **The id selects a slice, not a row.** One read of `indptr` at the id, one of the
            # range it names, and what comes back is every position along the other axis with a
            # value -- which is what "what is in this object" means for a matrix. No SQL, and no
            # database in the path at all; the rule that this module reads no store holds either
            # way, because a plan is instructions rather than values.
            key_axis = produces[0] if len(produces) == 1 else None
            names = matrix.axis_names
            if key_axis is None or key_axis not in names:
                continue
            # Only from the layout whose `indptr` indexes the id. From the other one the same
            # question is a scan of every byte -- 1 777 ms against 2.2 ms, measured -- and a
            # plan for that is not a slow lookup, it is a lookup nobody should execute. So the
            # dataset simply publishes no plan until the transposed layout is registered.
            sparse_array = matrix.array_indexing(key_axis)
            if sparse_array is None:
                continue
            # However many axes are left, not exactly one. At rank two the slice is a value per
            # position along the single other axis; at rank three it is a value per (metabolite,
            # adduct) pair, raveled in the layout's own `index_order` and unravelled by the client.
            # Either way it is one contiguous read of one object's whole profile, which is what a
            # hover is -- the rank only changes how many numbers a returned position is.
            others = [name for name in names if name != key_axis]
            plans.append(
                AttributePlanSpec(
                    edge=edge,
                    sparse_dataset=matrix,
                    path=[PlanStepSpec(edge=step_edge, inverted=inverted) for step_edge, inverted in paths[edge.input_id]],
                    sample=SampleSpec(system=field_system, store=store, consumes=consumes, produces=produces, passthrough=passthrough),
                    lookup=LookupSpec(kind="SPARSE", sparse_array=sparse_array, key_axis=key_axis, value_axes=others),
                )
            )
            continue

        # A product space -- a table whose row is identified by a pair, one half of which it
        # identifies itself through `references` -- has no plan a worker can execute. It holds
        # only what this edge supplies, which is one id; the other half would have to be bound
        # to nothing, and `build_lookup_sql` would emit a `WHERE` term with no value for it.
        # Dropping the term instead is worse: the lookup then returns every row of that half,
        # silently, where one was meant.
        #
        # So: no plan, which is the same conclusion the degenerate table below reaches and for
        # the same reason -- a lookup this cannot state honestly is one it does not state. What
        # such a table *can* answer is a slice rather than a row, and that wants a lookup kind
        # of its own (RFC-7's `SparseLookup`), not a `WHERE` with a hole in it.
        if table.pk in product_spaces:
            continue

        coordinate_columns = {column.name: column for column in table.columns_by_role(enums.ColumnRoleChoices.COORDINATE.value)}
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

        # Every non-coordinate column. There is no narrower rule available: a table declares
        # all of its columns, so "the caller meant this one" is true of every one of them.
        # The width of a plan is therefore the width of the table, which is what
        # `_MAX_TABLE_COLUMNS` bounds -- a file wide enough for that to hurt is a matrix, and
        # `createSparseDataset` is where it belongs.
        attributes = [column for column in table.columns.all() if column.role != enums.ColumnRoleChoices.COORDINATE.value]
        sql = build_lookup_sql(attribute_columns=attributes, key_columns=key_columns)

        plans.append(
            AttributePlanSpec(
                edge=edge,
                table=table,
                path=[PlanStepSpec(edge=step_edge, inverted=inverted) for step_edge, inverted in paths[edge.input_id]],
                sample=SampleSpec(system=field_system, store=store, consumes=consumes, produces=produces, passthrough=passthrough),
                lookup=LookupSpec(kind="TABLE", store=table.store, key_columns=key_columns, attributes=attributes, sql=sql),
            )
        )

    # Local plans first, then by distance, ties by edge pk -- so a client that only wants
    # what is rooted where it probed reads a stable prefix.
    plans.sort(key=lambda plan: (len(plan.path), plan.edge.pk))
    return plans
