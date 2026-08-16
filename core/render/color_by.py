"""Coloring objects by a column of the table their source keys into.

One model, because it is one fact. A label layer and a mesh layer both render *objects*
carrying ids, both reach a table of per-object rows through the same ``FIELD`` edge
(``createTableDataset(keyedBy:)``), and both then pick one of its columns to color by.
The layers differ in everything else -- a mask has a hash, a background id, contours; a
collection has a material and a wireframe -- but not in this, so storing it twice would be
two copies of one truth free to drift.

The GraphQL surface keeps two *names* (``LabelColorBy`` and ``MeshColorBy``), because a
type named for label layers reads wrong on a mesh and the descriptions differ. What they
share is this model, and one validator at the mutation boundary
(``core.mutations.layer._build_color_by``), which is where the two claims that cannot be
checked from the input alone are checked: that the table really is reachable by a FIELD
edge, and that the column exists on it.
"""

from pydantic import BaseModel

from core import enums


class ColorByModel(BaseModel):
    """Color objects by a column of the table their source's ``FIELD`` edge keys into.

    The table is named, never the join: which column of it holds row identity is already
    declared there (its single INDEX coordinate column), and the edge that makes the
    lookup possible is already in the coordinate graph. A second per-layer copy of either
    could disagree with the fact it copies.

    ``colormap`` and ``class_colors`` are the two ways a column becomes color, and which
    one applies follows from the column's declared role, not from a choice here: a measure
    column takes the colormap, a categorical one (an id, a class label) takes the explicit
    map. Naming both is refused at the boundary.
    """

    table: str
    column: str
    colormap: enums.ColorMap | None = None
    class_colors: dict[str, list[int]] | None = None
