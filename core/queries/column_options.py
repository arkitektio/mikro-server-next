"""The options query: what a mesh layer may be coloured or filtered by.

Rooted on the **collection**, not on a coordinate system as ``attributePlans`` is, because the
question is asked while looking at a collection and the space is an implementation detail of the
answer. That is also the difference in kind between the two queries: a plan is an instruction to
execute per hover, an option is a choice to author once. They walk related ground and are not
substitutes -- see :mod:`core.logic.column_options` for what `attributePlans` includes that this
must not, and excludes that this must.
"""

import strawberry
from kante.types import Info
from strawberry_django.pagination import OffsetPaginationInput

from core import filters as core_filters
from core import enums, models, types
from core.logic import column_options as column_options_logic
from core.scoping import get_for_org
from core.utils import paginate_list


def _matches(spec: column_options_logic.ColumnOptionSpec, filters: "core_filters.ColumnOptionFilter") -> bool:
    """Whether one option survives the narrowings the caller asked for."""
    if filters.direct_only and spec.join_path:
        return False
    # The terminal table, deliberately: an option is where its *value* is read, and a table the
    # path merely passes through is not where anything is read from. Documented on the field,
    # because "involves this table" is the other plausible reading and the two disagree exactly
    # on the hopped options.
    if filters.table is not None and str(spec.table.pk) != str(filters.table):
        return False
    if filters.roles is not None and spec.column.role not in {role.value for role in filters.roles}:
        return False
    if filters.controls is not None:
        control = enums.ColumnControl.MEASURE if spec.is_measure else enums.ColumnControl.CATEGORICAL
        if control.value not in {choice.value for choice in filters.controls}:
            return False
    if filters.search:
        needle = filters.search.strip().casefold()
        haystack = " ".join(part for part in (spec.column.name, spec.column.long_name, spec.table.name) if part)
        if needle and needle not in haystack.casefold():
            return False
    return True


def _options(
    info: Info,
    mesh_collection: strawberry.ID,
    filters: "core_filters.ColumnOptionFilter | None",
    pagination: OffsetPaginationInput | None,
    max_join_depth: int,
) -> list[column_options_logic.ColumnOptionSpec]:
    """The candidates, narrowed and paged -- everything both queries share, which is everything.

    The two queries differ only in the name of the type they project into, the way `LabelColorBy`
    and `MeshColorBy` differ: a picker authoring a rule should not have to read a type named for
    colouring, and the set behind both is one walk and one answer.
    """
    collection = get_for_org(models.MeshCollection, info, id=mesh_collection)
    system = column_options_logic.mesh_collection_system(collection)

    specs = column_options_logic.build_column_options(
        system,
        info.context.request.organization,
        max_join_depth=max_join_depth,
    )

    if filters is not None:
        specs = [spec for spec in specs if _matches(spec, filters)]

    if pagination is not None:
        specs = paginate_list(specs, offset=pagination.offset or 0, limit=pagination.limit)

    return specs


def _control(spec: column_options_logic.ColumnOptionSpec) -> "enums.ColumnControl":
    """Which control a column admits, from the one frozenset the write path enforces."""
    return enums.ColumnControl.MEASURE if spec.is_measure else enums.ColumnControl.CATEGORICAL


def _join_path(spec: column_options_logic.ColumnOptionSpec) -> "list[types.ColumnOptionJoinStep]":
    """The hops that reach this column, as the client will pass them back."""
    return [types.ColumnOptionJoinStep(table=table, column=column) for table, column in spec.join_path]


def color_by_options(
    info: Info,
    mesh_collection: strawberry.ID,
    filters: "core_filters.ColumnOptionFilter | None" = None,
    pagination: OffsetPaginationInput | None = None,
    max_join_depth: int = 1,
) -> list[types.ColorByOption]:
    """Every column this collection's objects can be coloured or filtered by.

    The set is exactly what `createMeshLayer(colorBys:)` and `filterBys` accept: it is built from
    the same reachability walk the mutation validates against, and its `control` comes from the
    same frozenset the mutation enforces. An options query that drifts from its write path is
    worse than none -- it teaches a picker to offer refusals.

    What it deliberately does not carry is the columns' *values*. A picker wanting the classes of
    a categorical column, or the range of a measured one, reads them from the parquet itself: it
    holds an `accessGrant` for that store and is reading the table anyway, so a scan here would
    duplicate a query the client can make locally at a cost this server cannot bound.
    """
    return [
        types.ColorByOption(table=spec.table, column=spec.column, control=_control(spec), join_path=_join_path(spec))
        for spec in _options(info, mesh_collection, filters, pagination, max_join_depth)
    ]


def filter_by_options(
    info: Info,
    mesh_collection: strawberry.ID,
    filters: "core_filters.ColumnOptionFilter | None" = None,
    pagination: OffsetPaginationInput | None = None,
    max_join_depth: int = 1,
) -> list[types.FilterByOption]:
    """Every column this collection's objects can be filtered by.

    The same candidates `colorByOptions` returns, and deliberately so: a colouring and a rule
    read the same column through the same join and branch on the same role, so offering two
    different sets would mean one of them was wrong. What differs is the prose -- MEASURE means
    a `min`/`max` bound here and a colormap there -- which is why it is a second name rather
    than a second walk.
    """
    return [
        types.FilterByOption(table=spec.table, column=spec.column, control=_control(spec), join_path=_join_path(spec))
        for spec in _options(info, mesh_collection, filters, pagination, max_join_depth)
    ]
