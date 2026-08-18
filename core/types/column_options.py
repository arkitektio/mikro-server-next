"""GraphQL types for the picker options: what a layer may be coloured or filtered by.

One pair of types for every source that publishes pickers -- a mesh collection and, through its
lens, a label layer's mask -- because an option is the same thing over both: a column the
source's ids reach, and the hops that reach it.

Computed types, like attribute plans and for the same reason: an option is derived from the
coordinate graph and the table schemas at query time, and nothing about it is stored. What it
publishes is not a new fact -- the column, its role and its unit are all declared on the table
already -- but a *narrowing*: these are the columns this source's ids can actually reach, and
every one of them is one the write path accepts.

The one derived field is ``control``, and it is here rather than left to the client because the
measure-vs-categorical split is the mutation's rule (``core.logic.column_options.MEASURE_ROLES``,
the same frozenset the boundary enforces). A client deriving it from ``role`` would be a second
copy of a rule, free to disagree the day a role is added.
"""

from typing import List

import strawberry

from core import enums
from core.types.table_dataset import TableDataset, TableDatasetColumn


@strawberry.type(description="One hop of a join path: the column whose values identify rows of the next table")
class ColumnOptionJoinStep:
    """One reference hop on the way to an offerable column."""

    table: TableDataset = strawberry.field(description="The table this hop stands in")
    column: TableDatasetColumn = strawberry.field(description="The column of it whose `references` identifies rows of the next table")


@strawberry.type(
    description=(
        "One column a layer may be coloured or filtered by, and how it is reached. Both pickers read the same options: `colorBys` and `filterBys` turn on the same measure-vs-categorical split, "
        "so two lists would be two copies of one answer. Every option returned is one the mutation that publishes the picker accepts -- `createMeshLayer` over a collection, `createLabelLayer` "
        "over a lens -- and every column it omits is one that mutation refuses; that invariant is why this exists rather than a client filtering `attributePlans`, which walks a different set"
    )
)
class ColorByOption:
    """An offerable (join path, table, column) triple."""

    table: TableDataset = strawberry.field(description="The table the value is read from. With an empty `joinPath` this is a table the source's ids key directly")
    column: TableDatasetColumn = strawberry.field(description="The column holding the value. Its `name` is what `colorBys`/`filterBys` take, and its `role`, `unit` and `dtype` are declared on the table")
    control: enums.ColumnControl = strawberry.field(
        description="Which control this column admits, derived from its role by the same rule the write path enforces: MEASURE takes a colormap and a `min`/`max` range, CATEGORICAL an explicit colour map and a `values` set"
    )
    join_path: List[ColumnOptionJoinStep] = strawberry.field(
        description="The `references` hops from the table the source's ids land in to `table`. Empty is the direct case. Pass it back verbatim as `colorBys[].joinPath` to select this option"
    )

    # No `values`, and no numeric domain. A picker wanting the classes of a categorical column or
    # the range of a measured one reads them from the parquet itself -- it holds an `accessGrant`
    # for that store and is already reading the table. A scan here would be this server paying,
    # per request and without a bound it sets, for a query the client can make locally.


@strawberry.type(
    description=(
        "One column a layer may be filtered by, and how it is reached. The same set the colour-options query returns, under the name that reads right where a rule is being authored: both pickers "
        "turn on the same measure-vs-categorical split, so the candidates are one answer and this is the second way to ask for it. Every option returned is one the mutation that publishes the "
        "picker accepts -- `createMeshLayer(filterBys:)` over a collection, `createLabelLayer(render: {filterBys: ...})` over a lens"
    )
)
class FilterByOption:
    """An offerable (join path, table, column) triple, described for the filter picker."""

    table: TableDataset = strawberry.field(description="The table the value is read from. With an empty `joinPath` this is a table the source's ids key directly")
    column: TableDatasetColumn = strawberry.field(description="The column the rule is written against. Its `name` is what `filterBys` takes, and its `unit` is the unit a `min`/`max` bound is stated in")
    control: enums.ColumnControl = strawberry.field(
        description="Which rule this column admits, derived from its role by the same rule the write path enforces: MEASURE takes a `min`/`max` bound, CATEGORICAL an explicit `values` set. Passing the wrong one is refused at the boundary"
    )
    join_path: List[ColumnOptionJoinStep] = strawberry.field(
        description="The `references` hops from the table the ids land in to `table`. Empty is the direct case. Pass it back verbatim as `filterBys[].joinPath` to write a rule against this column"
    )
