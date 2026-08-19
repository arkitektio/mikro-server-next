"""Coloring objects by a column of the table their source keys into.

One model, because it is one fact. A label layer and a mesh layer both render *objects*
carrying ids, both reach a table of per-object rows through the same ``FIELD`` edge
(``createTableDataset(keyedBy:)``), and both then pick one of its columns to color by.
The layers differ in everything else -- a mask has a hash, a background id, contours; a
collection has a material, a wireframe and a shading model -- but not in what one of these
says, so storing that twice would be two copies of one truth free to drift.

Both kinds now publish an ordered *picker* of these rather than one colouring, which is why
the caption sits on :class:`PickerColorByModel` between the base and the two named
subclasses: an author publishes the readings worth switching between and the person at the
screen chooses among them, and that is as true of a mask's objects as of a collection's.

The GraphQL surface keeps two *names* (``LabelColorBy`` and ``MeshColorBy``), because a
type named for label layers reads wrong on a mesh and the descriptions differ. What they
share is this model, and one validator at the mutation boundary
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

    ``min`` and ``max`` window the colormap: the value mapped to its bottom and the value
    mapped to its top, so the map's whole width spends itself on the range that matters
    instead of being stretched flat by one outlier. They belong to the colormap half only --
    a categorical column has no order to window -- and an omitted end leaves the viewer to
    stretch the map over the values it actually reads.
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
    # The colormap's window, inclusive on both ends and in the column's own declared `unit` --
    # bare numbers for the same reason a filter's bounds are (see core.render.filter_by): the
    # column is the one place that says what "500" means, and a quantity here would be a second
    # statement of it, free to drift. Stored dumps written before these existed rehydrate to
    # None, which is exactly what they meant: stretch over what you see.
    min: float | None = None
    max: float | None = None
    class_colors: dict[str, list[int]] | None = None


class PickerColorByModel(ColorByModel):
    """One entry of a layer's colour picker: a joined column, and what to call it in the UI.

    The caption is the only thing a picker entry adds to a colouring, and it belongs to the
    picker rather than to the colouring: it is what a menu row says, not part of what gets
    drawn. Which is exactly why it is *not* what distinguishes two entries -- the same
    (table, column, colormap, class colours) twice under two names is refused at the
    boundary, because a picker whose two rows render identically is a bug wearing two labels.

    Shared by both layer kinds. A mask is one map and a collection is a set of surfaces, but
    "these are the readings worth switching between, and this one is showing now" is the same
    statement over both, and the two subclasses below exist only so the GraphQL surface can
    name it twice.
    """

    label: str | None = None


class MeshColorByModel(PickerColorByModel):
    """One entry of a mesh layer's colour picker, named for the GraphQL type it backs."""


class LabelColorByModel(PickerColorByModel):
    """One entry of a label layer's colour picker, named for the GraphQL type it backs."""
