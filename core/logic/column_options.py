"""What a picker may offer: every column a source's ids can reach, and how they are reached.

The answer to "what can I colour or filter this by", and it has exactly one job -- **to be the
set the mutation accepts**. That is why it is built on
:func:`core.logic.attribute_plans.field_reachable_tables`, the same function ``createMeshLayer``
and ``createLabelLayer`` both validate against, rather than on :func:`~core.logic.attribute_plans.build_attribute_plans`:
the plan builder answers a different question and answers it differently. It walks the whole
fact component and hands back plans rooted at a *source mask* that a client holding geometry-row
ids cannot execute; it drops an edge whose output has no matching COORDINATE column, which the
validator keeps; and it resolves stores, so a storeless array anywhere in the component fails the
whole query while the validator sails past. Offer a set that is neither a subset nor a superset
of what is accepted and a picker either hides legal choices or proposes ones the mutation
refuses. The house states the invariant on the other picker already
(``LensPlaceableFilter``): *"every lens it keeps is one createLayer accepts, and every lens it
drops is too."*

The two sources that publish pickers each get a resolver here (:func:`mesh_collection_system`,
:func:`lens_source_system`) and nothing else differs between them: everything past the system is
one walk and one answer, which is what lets one options query serve both under two names.

Two walks compose here, and they are different in kind. The first is over the **coordinate
graph** -- FIELD edges, the single crossing from geometry into record-land. The second is over
the **schema**: ``TableColumn.references``, a declared foreign key between two tables that no
coordinate walk consults (see :mod:`core.render.joins`). Depth is counted in the second, because
the first has no depth to speak of: FIELD is not invertible and tables are leaves.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db.models import Prefetch

from core import enums, models
from core.logic import attribute_plans as attribute_plans_logic

if TYPE_CHECKING:
    from authentikate.models import Organization


#: The roles whose values are measured, and so admit a colormap and a range. The rest -- an id, a
#: track id, a class label, a colour -- are categorical: a colormap over them would impose an
#: order they do not have, and so would a bound. The same split ``TableColumn`` uses to decide
#: which columns may carry a unit.
#:
#: Lives here rather than in ``core.mutations.layer`` because the options query publishes it (as
#: each option's control) and the mutations enforce it. Two copies of this frozenset would be a
#: picker offering a colormap the write path then refuses.
MEASURE_ROLES = frozenset({enums.TableColumnRoleChoices.COORDINATE.value, enums.TableColumnRoleChoices.ATTRIBUTE.value})

#: How many ``references`` hops a path may take. A bound, not a judgement: the schema graph can
#: cycle and can fan out, and an unbounded walk over someone's warehouse is a denial of service
#: with a friendly name. Four is far past any chain anyone has asked for.
MAX_JOIN_DEPTH = 4


def mesh_collection_system(collection) -> "models.CoordinateSystem":
    """The space a collection's FIELD edges leave from, or the refusal if it has none.

    Here rather than in the mutations because both sides of the picker need it: the write path
    to check an entry, and the options query to enumerate the candidates. One definition, so the
    two cannot disagree about what a collection with no space means.
    """
    system = getattr(collection, "coordinate_system", None)
    if system is None:
        raise ValueError(f"Mesh collection {collection.pk} has no coordinate system, so there is no FIELD edge out of it and nothing to colour by or filter on.")
    return system


def lens_source_system(lens) -> "models.CoordinateSystem":
    """The space a mask's pixels are expressed in, or the refusal if it has none.

    :func:`~core.logic.graph.lens_source_system`'s strict twin, and here beside
    :func:`mesh_collection_system` because the two pickers ask the same question of their two
    sources: which system do the FIELD edges leave from. Returning ``None`` into a reachability
    walk would answer "no tables" where the honest answer is "this lens is not placed".
    """
    from core.logic import graph as graph_logic

    system = graph_logic.lens_source_system(lens)
    if system is None:
        raise ValueError(f"Lens {lens.pk} is in no coordinate system, so there is no FIELD edge out of it and nothing to colour by or filter on.")
    return system


def is_measure(column: "models.TableColumn") -> bool:
    """Whether this column's values are measured, and so take a colormap or a range."""
    return column.role in MEASURE_ROLES


@dataclass(frozen=True)
class ColumnOptionSpec:
    """One offerable column, and the hops that reach it.

    ``join_path`` is empty for a column of the table the FIELD edge landed on -- the direct
    case. Each step is the (table, column) whose values identify rows of the next table, ending
    at ``table``, where ``column`` is the value itself.
    """

    join_path: tuple[tuple["models.TableDataset", "models.TableColumn"], ...]
    table: "models.TableDataset | None" = None
    column: "models.TableColumn | None" = None

    # The sparse half. Flat with the column half rather than a second spec type, for the reason
    # the stored colouring is flat: both pickers read one list, and splitting the option would
    # mean every filter, every sort and every page boundary handling two.
    #
    # **One option per dataset, never per position.** A matrix with 19 059 features has 19 059
    # positions, and enumerating them here is precisely what this design exists to avoid -- the
    # option says *which axes a position is named along*, and the client picks the positions by
    # searching the tables those axes reference, which it already holds grants for. That is the
    # same line `core.logic.tables` draws about a picker wanting a column's values.
    #
    # `axes` is plural because a colouring names a position along **every** identified axis, and a
    # rank-three matrix has two of them. An option carrying one of a pair would not be something a
    # client could write back, which would break the one thing this module exists to guarantee.
    sparse_dataset: "models.SparseDataset | None" = None
    axes: tuple[str, ...] = ()

    @property
    def depth(self) -> int:
        """How many reference hops away this column is. 0 is the table the ids land in."""
        return len(self.join_path)

    @property
    def is_sparse(self) -> bool:
        """Whether this option names a slice of a matrix rather than a column of a table."""
        return self.sparse_dataset is not None

    @property
    def name(self) -> str:
        """What the option is called, whichever half it is -- for searching and for ordering.

        A sparse option is named by its axes joined, so a search for `gene` still finds the matrix
        it is an axis of, and two matrices over different axis sets order stably against each other.
        """
        if self.is_sparse:
            return " ".join(self.axes)
        return self.column.name if self.column else ""

    @property
    def is_measure(self) -> bool:
        """Whether the value is measured, and so takes a colormap or a range.

        A slice of a matrix always is: it is a value per object, and there is nothing
        categorical about it. Nothing stores categories sparsely, because the zeros would be a
        category too -- which is also why a sparse colouring refuses `classColors` outright.
        """
        return True if self.is_sparse else is_measure(self.column)


def _tables_with_columns(table_ids: "set[int]", organization: "Organization") -> "dict[int, models.TableDataset]":
    """One query for a whole level of the walk, columns and their reference targets attached.

    Prefetched here rather than by widening ``field_edges_from``: that walk is shared with
    ``build_attribute_plans``, which does not need columns, and making every hover-plan query pay
    for them to serve this one would be the wrong trade.

    Scoped to the organization even for hop targets. A reference is authored through
    ``get_for_org`` so a cross-org target should not exist, but "should not exist" is not a
    guarantee a read path gets to lean on.
    """
    tables = models.TableDataset.objects.filter(pk__in=table_ids, organization=organization).prefetch_related(
        Prefetch("columns", queryset=models.TableColumn.objects.select_related("references").order_by("order")),
    )
    return {table.pk: table for table in tables}


def build_column_options(
    system: "models.CoordinateSystem",
    organization: "Organization",
    *,
    max_join_depth: int = 1,
    max_depth: int | None = None,
) -> list[ColumnOptionSpec]:
    """Every column reachable from ``system``, direct ones first, then one hop out, then two.

    Breadth-first, so the list is ordered by distance and a client that only wants the direct
    columns reads a stable prefix -- the same courtesy ``build_attribute_plans`` extends by
    sorting local plans first.

    The order within a level is (table pk, column order), and it is *stable across calls*,
    because this list gets paginated: a picker whose second page reshuffles is a menu whose rows
    move under the cursor.

    Cycles are cut per branch, not globally: a table reached by two different paths is two
    genuinely different options and both survive, while a path that revisits a table it already
    stands in is dropped -- following it forever would produce longer and longer chains that all
    read the same rows. **No cycle can be authored today** -- a reference target must already
    exist when the referencing table is created, and `references` has no update path -- so both
    that guard and ``MAX_JOIN_DEPTH`` are defence in depth against a schema this server does not
    currently let anyone write, not against one it has seen.
    """
    reachable = attribute_plans_logic.field_reachable_tables(system, organization, max_depth=max_depth)

    options: list[ColumnOptionSpec] = []
    # (path so far, the table to expand, the tables this branch has already stood in)
    frontier = [((), int(pk), frozenset({int(pk)})) for pk in sorted(reachable, key=int)]

    for depth in range(max_join_depth + 1):
        if not frontier:
            break

        tables = _tables_with_columns({table_id for _, table_id, _ in frontier}, organization)
        next_frontier: list[tuple[tuple, int, frozenset]] = []

        for path, table_id, visited in frontier:
            table = tables.get(table_id)
            if table is None:
                continue
            for column in table.columns.all():
                options.append(ColumnOptionSpec(join_path=path, table=table, column=column))

                target = column.references
                if target is None or depth >= max_join_depth or target.pk in visited:
                    continue
                next_frontier.append((path + ((table, column),), target.pk, visited | {target.pk}))

        # Sorted by the path already taken, then by table: the walk's own order is dict order,
        # which is not an order anyone can page through twice.
        frontier = sorted(next_frontier, key=lambda entry: ([(step[0].pk, step[1].order) for step in entry[0]], entry[1]))


    # The sparse half, after the column half so a picker shows tables first -- the common case
    # stays where it was. No BFS: a matrix is not hopped through, because a position along its
    # axis is a row of the table that axis references, and following *that* is the client's
    # choice one lookup away, exactly as `TableColumn.references` already is.
    matrices = attribute_plans_logic.field_reachable_sparse_datasets(system, organization, max_depth=max_depth)
    for _, dataset in sorted(matrices.items(), key=lambda entry: int(entry[0])):
        names = dataset.axis_names
        indexed = {names[array.indexed_axis] for array in dataset.arrays.all() if 0 <= array.indexed_axis < len(names)}
        identified = tuple(sorted(reference.axis for reference in dataset.axis_references.all()))
        # Offered when **at least one** of those axes has a layout, which is exactly the rule the
        # mutation applies: the read is one contiguous slice along an indexed named axis, then a
        # filter by the other named positions. Requiring all of them would hide legal colourings;
        # requiring none would offer a scan. Either way the picker and the write path would
        # disagree, which is the one thing this module must not allow.
        if identified and any(axis in indexed for axis in identified):
            options.append(ColumnOptionSpec(join_path=(), sparse_dataset=dataset, axes=identified))

    return options
