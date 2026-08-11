"""How a segmentation or instance map becomes color.

A label layer renders an array whose values are *object ids*, and none of the image
layer's vocabulary survives the change of value domain: contrast limits and gamma are
contrast on a continuous intensity, a colormap maps an ordered scalar (ids 41 and 42 are
adjacent in no sense), and the intensity projections -- MIP, mean -- are statistics whose
result is not an object. So this is not a :class:`~core.render.layer.models.TransferFunctionModel`
with a flag, and deliberately not a node union either: a label layer has exactly one
source and no compositing tree to put under a blend node.

What it carries instead is the vocabulary ids actually have: a hash from id to color, a
background id drawn transparent, contour-or-fill, a selection, and -- the one that needs
the coordinate graph -- ``color_by``, which dereferences the ``FIELD`` edge keying this
mask's pixels to a table of objects (``createTableDataset(keyedBy:)``). Coloring instances
by a measured column, or a class column, is the same display pick a point layer makes with
``color_column``: honestly per-layer view state, and RFC-8 says so.

Nothing here is a spatial fact. The mask's placement is its dataset's, derived over the
graph, exactly as for an image layer.
"""

from pydantic import BaseModel, Field

from core import enums


class LabelColorByModel(BaseModel):
    """Color objects by a column of the table this mask's ``FIELD`` edge keys into.

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


class LabelRenderModel(BaseModel):
    """The full render recipe of a label layer."""

    intensity_axis: str | None = None
    intensity_index: int = 0
    seed: int = 0
    background: int = 0
    opacity: float | None = 1.0
    contour: bool = False
    contour_width: float | None = 1.0
    selected: list[int] = Field(default_factory=list)
    selection_color: list[int] | None = None
    show_unselected: bool = True
    color_by: LabelColorByModel | None = None
