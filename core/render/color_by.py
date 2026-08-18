"""Coloring objects by a column of the table their source keys into.

One model, because it is one fact. A label layer and a mesh layer both render *objects*
carrying ids, both reach a table of per-object rows through the same ``FIELD`` edge
(``createTableDataset(keyedBy:)``), and both then pick one of its columns to color by.
The layers differ in everything else -- a mask has a hash, a background id, contours; a
collection has a material, a wireframe and a shading model, and holds a whole ordered
*list* of these rather than one -- but not in what one of them says, so storing that twice
would be two copies of one truth free to drift.

The GraphQL surface keeps two *names* (``LabelColorBy`` and ``MeshColorBy``), because a
type named for label layers reads wrong on a mesh and the descriptions differ. What they
share is this model -- the mesh side subclasses it, adding only the caption its picker
needs -- and one validator at the mutation boundary
(``core.mutations.layer._build_color_by``), which is where the two claims that cannot be
checked from the input alone are checked: that the table really is reachable by a FIELD
edge, and that the column exists on it.
"""

from pydantic import BaseModel, Field

from core import enums
from core.render.joins import JoinStepModel


class ColorByModel(BaseModel):
    """Color objects by a column of the table their source's ``FIELD`` edge keys into.

    Each table is named, never its key: which column of a table holds row identity is
    already declared there (its single INDEX coordinate column), and the edge that makes
    the first lookup possible is already in the coordinate graph. A second per-layer copy
    of either could disagree with the fact it copies.

    ``join_path`` is how a column further than one table away is reached -- a chain of
    ``references`` hops, empty for the common case. See :mod:`core.render.joins`.

    ``colormap`` and ``class_colors`` are the two ways a column becomes color, and which
    one applies follows from the column's declared role, not from a choice here: a measure
    column takes the colormap, a categorical one (an id, a class label) takes the explicit
    map. Naming both is refused at the boundary.
    """

    # Where the value is read. With an empty `join_path` this is the table the FIELD edge
    # landed on -- what every colouring written before join paths existed means, and still
    # the common case. With a path, it is the table the last hop points at.
    table: str
    column: str
    # Empty is the direct case, so a stored dump written before this field existed rehydrates
    # as one: `ColorByModel(**entry)` fills the default, which is why this needs no migration.
    join_path: list[JoinStepModel] = Field(default_factory=list)
    colormap: enums.ColorMap | None = None
    class_colors: dict[str, list[int]] | None = None


class MeshColorByModel(ColorByModel):
    """One entry of a mesh layer's picker: a joined column, and what to call it in the UI.

    A subclass rather than a widening of :class:`ColorByModel`, and rather than a mesh-only
    copy. A label layer holds exactly one colouring and has no picker to caption, so ``label``
    would be a field nothing there could ever mean; a mesh layer publishes an ordered list and
    every entry needs a name a viewer can put in a menu. The shared half -- which table, which
    column, and how its values become colour -- is still one shape, checked by one validator.

    The caption is deliberately *not* what distinguishes two entries: the same (table, column)
    twice under two names is refused at the boundary, because a picker whose two rows resolve
    to one column is a bug wearing two labels.
    """

    label: str | None = None
