"""Splitting a set of declared identifications into the two things they become.

An axis says what its positions are, and the answer lands in one of two places depending on
which of them it is (:mod:`core.inputs.identification` argues why the split is real):

* a **mask** or a **collection** identifies by having contents that *are* the ids, which is a
  claim about space, so it authors a FIELD edge from that source's system into this one;
* a **table** identifies by its rows being the positions, which is a foreign key, so it
  authors no edge and is written on the axis' own column instead.

One function, because the two creates were about to grow two copies of it -- and because the
resolution a table identification needs (:func:`resolve_reference_target`: the target must be
dereferenceable, one INDEX coordinate column, not synthetic row enumeration) is the part it
would be easiest to write once and forget once.

Deliberately *not* here: "is every axis identified?". That is true of a sparse matrix by
construction and false of a table -- a localization table's `x` axis is identified by nothing
and should be -- so it belongs to the caller that means it.
"""

from typing import Sequence

from kante.types import Info

from core import models


def split_identifications(
    info: Info,
    *,
    name: str,
    entries: Sequence[tuple[str, Sequence[object]]],
    index_axes: set[str] | None = None,
) -> tuple[dict[str, "models.TableDataset"], list[tuple[str, object]]]:
    """Resolve the table references, and collect the identifications that author edges.

    Args:
        info: The request, for org-scoped lookups.
        name: What to call the thing being created, in an error.
        entries: ``(axis name, identifications)``, in declaration order. The identifications
            are the lowered union members, so each carries ``AUTHORS_EDGE`` and ``source_id``.
        index_axes: The axes that are INDEX, or ``None`` when every axis is (a sparse matrix,
            where INDEX is the only thing an axis could be). A ``TABLE`` identification on an
            axis outside this set is refused.

    Returns:
        ``(references, keyed)`` -- the resolved table per axis, and one
        ``(axis name, identification)`` per edge-authoring source, in declaration order.
        An axis identified by two masks appears twice in ``keyed``, which is what fan-in is.
    """
    references: dict[str, "models.TableDataset"] = {}
    keyed: list[tuple[str, object]] = []

    for axis_name, identifications in entries:
        for identification in identifications:
            if identification.AUTHORS_EDGE:
                keyed.append((axis_name, identification))
                continue

            # A coordinate column's values ARE its coordinates -- they place the row in this
            # space. For a SPACE or TIME axis, claiming they simultaneously identify rows
            # elsewhere would make the axis two different maps at once: a position in
            # nanometres and a row id are different things, and which one a reader follows
            # would be convention. An INDEX axis is the exception, and not an arbitrary one:
            # its values are *already* ids, so naming the table it enumerates is not a second
            # map, it is what the enumeration is of. That is what makes a product space
            # expressible -- a contact map indexed by (nucleus, cell) has two coordinate axes
            # because a row is the pair, and one pixel holds one value, so a mask supplies
            # only one of them.
            if index_axes is not None and axis_name not in index_axes:
                raise ValueError(
                    f"Axis '{axis_name}' of '{name}' is identified by a table, but it is not an INDEX axis: its values are positions rather than ids, so they place the row in "
                    "this space and cannot also identify rows elsewhere. Declare the reference on a data column (ID, TRACK_ID, ...) -- or, if its values really are rows of the "
                    "other table, declare the column INDEX, which is an enumeration and may say what it enumerates."
                )

            if axis_name in references:
                # One column carries one `references`, and one axis is one enumeration. Two
                # tables would be two answers to "what are these positions", which is not a
                # richer claim, it is an ambiguous one.
                raise ValueError(
                    f"Axis '{axis_name}' of '{name}' is identified by more than one table. An axis enumerates one thing: two tables would be two different answers to what a "
                    "position along it is. Fan-in is only meaningful for the kinds that author an edge -- two masks may key one axis, because each edge stands on its own."
                )

            references[axis_name] = resolve_reference_target(info, identification.source_id, f"Axis '{axis_name}'")

    return references, keyed


def resolve_reference_target(info: Info, target_id: str, label: str) -> "models.TableDataset":
    """The table an identification names, checked to be one an id can be looked up in.

    Re-exported from :mod:`core.mutations.table_dataset`, where it lived while only that
    module needed it. Imported lazily for the reason every `core.logic` module imports
    mutations lazily: the mutation imports this one at module level.
    """
    from core.mutations.table_dataset import resolve_reference_target as resolve

    return resolve(info, target_id, label)
