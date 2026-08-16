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

from core.render.color_by import ColorByModel

#: Coloring objects by a joined column is not a label-layer fact -- a mesh layer does the
#: same thing through the same FIELD edge -- so the model lives in
#: :mod:`core.render.color_by` and is spelled under its old name here. The GraphQL surface
#: keeps two names for the two contexts; the stored shape is one.
LabelColorByModel = ColorByModel


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
