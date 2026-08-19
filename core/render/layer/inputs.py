"""GraphQL input types for the in-layer render graph.

GraphQL has no input unions, so — exactly like ``core/render/inputs/types.py`` —
a single recursive "fat" node input carries the fields of every node kind and is
discriminated at runtime by ``kind``. The mutation lowers this into the strict
tagged-union storage model (``core.render.layer.models``).
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Annotated, Optional

import strawberry
from strawberry.experimental import pydantic

from kanne_server import quantities
from kanne_server import scalars as kanne_scalars

from core import enums
from core.input_unions import prose_errors
from core.inputs.validators import assert_alpha, assert_contrast_limits, assert_positive, assert_rgba
from core.render import filter_by as filter_by_models
from core.render import joins


class LookupStopInputModel(BaseModel):
    position: float
    value: float

    @field_validator("value")
    @classmethod
    def _value_is_normalized(cls, value: float) -> float:
        # The output of the curve, not one of its inputs: what the colormap is indexed with,
        # so it runs 0..1 whatever the data's own scale is. `position` deliberately carries no
        # such rule -- it is a raw intensity, and 4000 is an ordinary 12-bit reading.
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"`value` is what a stop's intensity maps *to* -- the normalized value the colormap is indexed with -- so it runs from 0 to 1, but got {value}. `position` is the side carrying the data's own units.")
        return value


class TransferFunctionInputModel(BaseModel):
    clim_min: float | None = None
    clim_max: float | None = None
    colormap: enums.ColorMap | None = None
    color: list[int] | None = None
    gamma: float | None = None
    opacity: float | None = None
    invert: bool | None = None
    stops: list[LookupStopInputModel] | None = None

    @field_validator("stops")
    @classmethod
    def _stops_draw_a_curve(cls, stops: list[LookupStopInputModel] | None) -> list[LookupStopInputModel] | None:
        # Two rules, both about a list that cannot be read as a curve at all. One stop -- or
        # none -- has no interval to interpolate over, and omitting the field is how a client
        # says it wants no curve, so an empty list is a mistake rather than a way to say that.
        # An out-of-order list is refused rather than sorted, exactly as an inverted contrast
        # window is: the stored value is what the client wrote. Equal positions stay legal --
        # that is how a hard break in the curve is authored.
        if stops is None:
            return stops

        if len(stops) < 2:
            raise ValueError(f"`stops` is an intensity transfer curve, so it is drawn from at least two control points, but got {len(stops)}. Omit `stops` to use `climMin`/`climMax` and `gamma` instead.")

        positions = [stop.position for stop in stops]
        if positions != sorted(positions):
            raise ValueError(f"`stops` runs along the intensity axis, so its positions cannot go backwards, but got {positions}. Two stops may share a position -- that is a hard break in the curve -- but a later one may not sit below an earlier one.")

        return stops

    @field_validator("opacity")
    @classmethod
    def _opacity_is_an_alpha(cls, opacity: float | None) -> float | None:
        if opacity is not None:
            assert_alpha(opacity, field="opacity")
        return opacity

    @field_validator("gamma")
    @classmethod
    def _gamma_is_positive(cls, gamma: float | None) -> float | None:
        # A gamma is the exponent of a power law on normalized intensities. Zero flattens
        # every intensity to 1 and a negative one inverts and diverges at black -- neither
        # is a correction, and neither is what a client passing 0 meant.
        if gamma is not None:
            assert_positive(gamma, field="gamma", because="it is the exponent of a power law on normalized intensities")
        return gamma

    @field_validator("color")
    @classmethod
    def _color_is_rgba(cls, color: list[int] | None) -> list[int] | None:
        if color is not None:
            assert_rgba(color, field="color", maximum=255)
        return color

    @model_validator(mode="after")
    def _contrast_limits_are_a_range(self) -> "TransferFunctionInputModel":
        assert_contrast_limits(self.clim_min, self.clim_max)
        return self


class PhasorCursorInputModel(BaseModel):
    kind: enums.PhasorCursorKind | None = None
    g: float | None = None
    s: float | None = None
    radius: float | None = None
    points: list[list[float]] | None = None
    color: list[int] | None = None
    label: str | None = None
    visible: bool | None = None

    @field_validator("color")
    @classmethod
    def _color_is_rgba(cls, color: list[int] | None) -> list[int] | None:
        if color is not None:
            assert_rgba(color, field="color", maximum=255)
        return color


class PhasorTransferInputModel(BaseModel):
    mode: enums.PhasorColorMode | None = None
    min: quantities.GenericQuantity | None = None
    max: quantities.GenericQuantity | None = None
    colormap: enums.ColorMap | None = None
    weight_by_intensity: bool | None = None
    intensity: TransferFunctionInputModel | None = None
    cursors: list[PhasorCursorInputModel] | None = None


class ColorByInputModel(BaseModel):
    """One entry of a colour picker, as a client sends it.

    One input model for both layer kinds, because the claim is one: this table, this column,
    reached by these hops, rendered this way. The validators here are the fact, and two
    independently declared sets of them would be two things free to drift. What differs
    between the two named subclasses below is only the prose their GraphQL types carry.
    """

    table: str
    column: str
    colormap: enums.ColorMap | None = None
    min: float | None = None
    max: float | None = None
    class_colors: dict[str, list[int]] | None = None
    # The caption a picker row shows. Deliberately not what distinguishes two entries: the
    # same rendering twice under two names is refused at the mutation boundary.
    label: str | None = None
    join_path: list[joins.JoinStepModel] = Field(default_factory=list)

    @field_validator("class_colors")
    @classmethod
    def _class_colors_are_rgba(cls, class_colors: dict[str, list[int]] | None) -> dict[str, list[int]] | None:
        for value, color in (class_colors or {}).items():
            assert_rgba(color, field=f"classColors['{value}']", maximum=255)
        return class_colors

    @model_validator(mode="after")
    def _one_way_to_color(self) -> "ColorByInputModel":
        # Which of the two applies follows from the column's declared role, so naming both
        # is not a choice between them -- it is two answers to a question the table already
        # settled. Whether the *right* one was named needs the table, and is checked at the
        # mutation boundary.
        if self.colormap is not None and self.class_colors is not None:
            raise ValueError("`colorBy` takes either a `colormap` (for a measure column) or `classColors` (for a categorical one), never both: which applies follows from the column's declared role, not from a choice here")
        return self

    @model_validator(mode="after")
    def _window_belongs_to_the_colormap(self) -> "ColorByInputModel":
        # Shape, not role: whatever the column turns out to be, a value-to-color map has
        # already answered what every value looks like, so there is no window left to set.
        if self.class_colors is not None and (self.min is not None or self.max is not None):
            raise ValueError("`min`/`max` window the colormap -- the values mapped to its bottom and its top -- so they mean nothing next to `classColors`, which names each value's color outright")
        return self

    @model_validator(mode="after")
    def _window_is_a_range(self) -> "ColorByInputModel":
        # Ordering only, like a contrast window: both ends are in the column's own unit, so
        # there is no interval to hold them to, but an inverted pair maps the colormap
        # backwards by accident rather than on purpose.
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"`min` is the value mapped to the bottom of the colormap, so it cannot exceed `max`, but got {self.min} > {self.max}")
        return self


class LabelColorByInputModel(ColorByInputModel):
    """One entry of a label layer's colour picker, over a mask's objects."""


class MeshColorByInputModel(ColorByInputModel):
    """One entry of a mesh layer's colour picker, over a collection's objects."""


_JOIN_PATH_DESCRIPTION = (
    "How a column further than one table away is reached: the chain of `references` hops from the table this layer's ids land in to the table `column` lives in. Empty -- the common case -- "
    "means `table` is itself keyed by this layer's source. Each hop names the table it stands in and a column of that table whose `references` identifies rows of the next one; the renderer performs "
    "one lookup per hop, exactly as it already does for the first"
)


class MeshFilterByInputModel(filter_by_models.MeshFilterByModel):
    """The rule a client sends, which is the rule that gets stored.

    A subclass of the storage model rather than a parallel declaration: every check the model
    carries is a check on the *shape* of the rule -- one kind at a time, a range that is not
    empty, a value list that is not -- and none of them needs the table. The checks that do
    (does the column exist, is it the kind of column this rule can be run on) live at the
    mutation boundary, with `colorBy`'s, where the table is in hand.
    """


class LabelFilterByInputModel(filter_by_models.LabelFilterByModel):
    """The same rule over a mask's objects, sent and stored the same way."""


class LabelRenderInputModel(BaseModel):
    intensity_axis: str | None = None
    intensity_index: int | None = None
    seed: int | None = None
    background: int | None = None
    opacity: float | None = None
    contour: bool | None = None
    contour_width: float | None = None
    selected: list[int] | None = None
    selection_color: list[int] | None = None
    show_unselected: bool | None = None
    color_bys: list[LabelColorByInputModel] | None = None
    active_color_by: int | None = None
    filter_bys: list[LabelFilterByInputModel] | None = None
    active_filter_bys: list[int] | None = None

    @field_validator("opacity")
    @classmethod
    def _opacity_is_an_alpha(cls, opacity: float | None) -> float | None:
        if opacity is not None:
            assert_alpha(opacity, field="opacity")
        return opacity

    @field_validator("contour_width")
    @classmethod
    def _contour_width_is_positive(cls, contour_width: float | None) -> float | None:
        if contour_width is not None:
            assert_positive(contour_width, field="contourWidth", because="it is the width of a drawn outline")
        return contour_width

    @field_validator("selection_color")
    @classmethod
    def _selection_color_is_rgba(cls, selection_color: list[int] | None) -> list[int] | None:
        if selection_color is not None:
            assert_rgba(selection_color, field="selectionColor", maximum=255)
        return selection_color


class LayerNodeInputModel(BaseModel):
    kind: str
    label: str | None = None
    # channel node fields
    intensity_axis: str | None = None
    intensity_index: int | None = None
    visible: bool | None = None
    transfer: TransferFunctionInputModel | None = None
    # blend node fields
    blending: enums.Blending | None = None
    # projection node fields
    mode: enums.ProjectionMode | None = None
    # phasor node fields
    phasor_axis: str | None = None
    harmonic: int | None = None
    phasor_transfer: PhasorTransferInputModel | None = None
    children: list["LayerNodeInputModel"] | None = None


class LayerRenderGraphInputModel(BaseModel):
    root: LayerNodeInputModel


LayerNodeInputModel.update_forward_refs()
LayerRenderGraphInputModel.update_forward_refs()


@prose_errors
@pydantic.input(
    LookupStopInputModel,
    description="One control point of an intensity transfer curve: a raw intensity, and the normalized value it maps to. The two sides are on different scales -- `position` in the data's units, `value` in the 0..1 the colormap is indexed with",
)
class LookupStopInput:
    position: float = strawberry.field(description="The intensity this stop sits at, in the data's own intensity units -- the same scale as `climMin`/`climMax`, not a normalized fraction. Any finite value: 4000 is an ordinary 12-bit reading")
    value: float = strawberry.field(description="The normalized value that intensity maps to, from 0 to 1. This is what the colormap is indexed with, so 0 is the bottom of the LUT and 1 the top")


@prose_errors
@pydantic.input(TransferFunctionInputModel, description="Transfer-function settings for a channel source in a layer render graph")
class TransferFunctionInput:
    clim_min: float | None = strawberry.field(default=None, description="Lower contrast limit, in the data's own intensity units -- not a normalized fraction")
    clim_max: float | None = strawberry.field(default=None, description="Upper contrast limit, in the data's own intensity units -- not a normalized fraction")
    colormap: enums.ColorMap | None = strawberry.field(default=None, description="The colormap (transfer function LUT) applied to the channel")
    color: list[int] | None = strawberry.field(default=None, description="A solid RGBA color to tint the channel with, instead of a colormap: four components, each 0..255")
    gamma: float | None = strawberry.field(default=None, description="Gamma correction applied to the normalized intensities. The exponent of a power law, so greater than zero. Ignored when `stops` gives an explicit curve")
    opacity: float | None = strawberry.field(default=None, description="Per-channel opacity within the layer, from 0 (transparent) to 1 (opaque)")
    invert: bool | None = strawberry.field(default=None, description="Whether the contrast mapping is inverted")
    stops: list[LookupStopInput] | None = strawberry.field(default=None, description="An explicit intensity transfer curve, as at least two control points ordered by position. When given, the curve *is* the transfer: it supersedes `gamma` and the `climMin`/`climMax` window, which are the one-parameter and two-point special cases of the same mapping. Null uses those instead")


@prose_errors
@pydantic.input(PhasorCursorInputModel, description="A region of phasor space, and the color the pixels falling inside it are painted. A color rule on the image, not a plot widget")
class PhasorCursorInput:
    kind: enums.PhasorCursorKind | None = strawberry.field(default=None, description="The shape of the region (default 'circle')")
    g: float | None = strawberry.field(default=None, description="(circle) The g coordinate of the centre. Required for a circle")
    s: float | None = strawberry.field(default=None, description="(circle) The s coordinate of the centre. Required for a circle")
    radius: float | None = strawberry.field(default=None, description="(circle) The radius of the disc, in phasor units. Required for a circle")
    points: list[list[float]] | None = strawberry.field(default=None, description="(polygon) The (g, s) vertices of the region. At least three are required for a polygon")
    color: list[int] | None = strawberry.field(default=None, description="The RGBA color the pixels inside this region take, overriding the colormap")
    label: str | None = strawberry.field(default=None, description="An optional human-readable label, e.g. the species this region selects")
    visible: bool | None = strawberry.field(default=None, description="Whether this cursor colors the image (default true)")


@pydantic.input(PhasorTransferInputModel, description="How a phasor becomes the pixel's color: the transfer function of a phasor source")
class PhasorTransferInput:
    mode: enums.PhasorColorMode | None = strawberry.field(default=None, description="What the hue is derived from: the phasor's phase, its modulus, or the mean of both (default 'phase')")
    min: kanne_scalars.GenericQuantity | None = strawberry.field(default=None, description="The lower bound of the derived value, in its own dimension: a duration ('0.5 ns') over a microtime axis, a wavelength ('480 nm') over a spectrum axis")
    max: kanne_scalars.GenericQuantity | None = strawberry.field(default=None, description="The upper bound of the derived value, in its own dimension")
    colormap: enums.ColorMap | None = strawberry.field(default=None, description="The colormap the derived value is mapped through (default 'rainbow')")
    weight_by_intensity: bool | None = strawberry.field(default=None, description="Whether the photon count modulates the brightness, so hue carries the phasor and brightness the signal (default true)")
    intensity: TransferFunctionInput | None = strawberry.field(default=None, description="The transfer function applied to that photon count: contrast limits, gamma, opacity")
    cursors: list[PhasorCursorInput] | None = strawberry.field(default=None, description="Regions of phasor space whose pixels take a fixed color, overriding the colormap")


@pydantic.input(
    LayerNodeInputModel,
    description="A node in a layer's internal render graph. A 'channel' node carries an intensity source and transfer function; a 'phasor' node reduces an axis to a phasor and colors the pixel by it; a 'blend' node composites its children; a 'projection' node projects theirs over z.",
)
class LayerNodeInput:
    kind: str = strawberry.field(description="The node discriminator: 'channel', 'phasor', 'blend' or 'projection'")
    label: str | None = strawberry.field(default=None, description="An optional human-readable label for the node")
    intensity_axis: str | None = strawberry.field(default=None, description="(channel/phasor) The lens axis carrying the intensity channels")
    intensity_index: int | None = strawberry.field(default=None, description="(channel/phasor) The index along the intensity axis to render")
    visible: bool | None = strawberry.field(default=None, description="(channel/phasor) Whether the node participates in the composite")
    transfer: TransferFunctionInput | None = strawberry.field(default=None, description="(channel) The transfer function mapping this channel to color")
    blending: enums.Blending | None = strawberry.field(default=None, description="(blend) The blend mode used to composite the children")
    mode: enums.ProjectionMode | None = strawberry.field(default=None, description="(projection) The 3D projection / rendering mode applied over the z-axis")
    phasor_axis: str | None = strawberry.field(default=None, description="(phasor) The lens axis the phasor is taken over. Must be a MICROTIME or SPECTRUM axis. Required for a phasor node; defaults to the lens' only such axis")
    harmonic: int | None = strawberry.field(default=None, description="(phasor) The harmonic of the transform (default 1)")
    phasor_transfer: PhasorTransferInput | None = strawberry.field(default=None, description="(phasor) How the resulting phasor becomes the pixel's color. Named apart from `transfer` because it maps a (g, s) pair rather than a sampled scalar")
    children: Optional[list[Annotated["LayerNodeInput", strawberry.lazy(__name__)]]] = strawberry.field(default=None, description="(blend/projection) The child nodes composited or projected by this node")


@pydantic.input(LayerRenderGraphInputModel, description="The composable render recipe inside a single layer, rooted at a blend node")
class LayerRenderGraphInput:
    root: LayerNodeInput = strawberry.field(description="The root blend node of the layer's render graph")


@prose_errors
@pydantic.input(
    joins.JoinStepModel,
    description="One hop of a join path: the column whose values identify rows of the next table. The target is not named here -- the next step names it, and which of its columns holds row identity is already declared on it",
)
class JoinStepInput:
    table: strawberry.ID = strawberry.field(description="The table this hop stands in. The first step's table is the one the FIELD edge lands on; every later one is the table the previous hop pointed at")
    column: str = strawberry.field(description="A column of that table whose `references` names the next table. A column that references nothing is a value, not a hop")


@prose_errors
@pydantic.input(
    LabelColorByInputModel,
    description="One entry of a label layer's colour picker: colour objects by a column of the table this mask's FIELD edge keys into, instead of by hashing their id",
)
class LabelColorByInput:
    table: strawberry.ID = strawberry.field(description="The table dataset holding one row per object. Must be reachable from the layer's lens by a FIELD edge -- the edge `createTableDataset(keyedBy:)` authors and `attributePlans` discovers")
    column: str = strawberry.field(description="The column of that table whose value colors each object")
    colormap: enums.ColorMap | None = strawberry.field(default=None, description="The colormap the column's value is mapped through. For a measure column (role COORDINATE or ATTRIBUTE)")
    min: float | None = strawberry.field(default=None, description="The value mapped to the bottom of the colormap, in the column's own declared `unit`. For a measure column. Omit to let the viewer stretch the map from the smallest value it reads")
    max: float | None = strawberry.field(default=None, description="The value mapped to the top of the colormap, in the column's own declared `unit`. For a measure column. Omit to let the viewer stretch the map to the largest value it reads")
    class_colors: strawberry.scalars.JSON | None = strawberry.field(default=None, description="An explicit value-to-RGBA map, e.g. {'nucleus': [255, 0, 0, 255]}. For a categorical column (role ID, LABEL, TRACK_ID or COLOR), where a colormap would impose an order the values do not have")
    label: str | None = strawberry.field(default=None, description="What to call this colouring in a picker, e.g. 'Area' or 'Cell type'. A caption only -- two entries that render identically are refused however they are labelled")
    join_path: list[JoinStepInput] = strawberry.field(default_factory=list, description=_JOIN_PATH_DESCRIPTION)


@prose_errors
@pydantic.input(
    MeshColorByInputModel,
    description="Color a mesh collection's objects by a column of the table its FIELD edge keys into, instead of by the layer's flat material color",
)
class MeshColorByInput:
    table: strawberry.ID = strawberry.field(description="The table dataset holding one row per object. Must be reachable from this layer's collection by a FIELD edge -- the edge `createTableDataset(keyedBy: {kind: MESH_COLLECTION})` authors and `attributePlans` discovers")
    column: str = strawberry.field(description="The column of that table whose value colors each object")
    colormap: enums.ColorMap | None = strawberry.field(default=None, description="The colormap the column's value is mapped through. For a measure column (role COORDINATE or ATTRIBUTE)")
    min: float | None = strawberry.field(default=None, description="The value mapped to the bottom of the colormap, in the column's own declared `unit`. For a measure column. Omit to let the viewer stretch the map from the smallest value it reads")
    max: float | None = strawberry.field(default=None, description="The value mapped to the top of the colormap, in the column's own declared `unit`. For a measure column. Omit to let the viewer stretch the map to the largest value it reads")
    class_colors: strawberry.scalars.JSON | None = strawberry.field(default=None, description="An explicit value-to-RGBA map, e.g. {'nucleus': [255, 0, 0, 255]}. For a categorical column (role ID, LABEL, TRACK_ID or COLOR), where a colormap would impose an order the values do not have")
    label: str | None = strawberry.field(default=None, description="What to call this colouring in a picker, e.g. 'Volume' or 'Cell type'. A caption only -- two entries that render identically are refused however they are labelled")
    join_path: list[JoinStepInput] = strawberry.field(default_factory=list, description=_JOIN_PATH_DESCRIPTION)


@prose_errors
@pydantic.input(
    MeshFilterByInputModel,
    description="Draw only the objects whose row in a table this collection's FIELD edge keys into satisfies this rule. Which half applies follows from the column's declared role -- bounds for a measure column, an explicit value set for a categorical one",
)
class MeshFilterByInput:
    table: strawberry.ID = strawberry.field(description="The table dataset holding one row per object. Must be reachable from this layer's collection by a FIELD edge -- the edge `createTableDataset(keyedBy: {kind: MESH_COLLECTION})` authors and `attributePlans` discovers")
    column: str = strawberry.field(description="The column of that table whose value decides whether an object is drawn")
    min: float | None = strawberry.field(default=None, description="Lower bound, inclusive, in the column's own declared `unit`. For a measure column (role COORDINATE or ATTRIBUTE). Omit for an open lower end")
    max: float | None = strawberry.field(default=None, description="Upper bound, inclusive, in the column's own declared `unit`. For a measure column (role COORDINATE or ATTRIBUTE). Omit for an open upper end")
    values: list[str] | None = strawberry.field(default=None, description="The values that match, as strings -- ids included, the same vocabulary `classColors`' keys use. For a categorical column (role ID, LABEL, TRACK_ID or COLOR), where a bound would impose an order the values do not have")
    exclude: bool = strawberry.field(default=False, description="Whether the rule *removes* what it matches rather than keeping it. Inverts the whole rule, bounds and values alike")
    label: str | None = strawberry.field(default=None, description="What to call this filter in a picker, e.g. 'Large cells'. Two entries may share a column -- 'small' and 'large' over one measure are two different rules -- and this is what tells them apart")
    join_path: list[JoinStepInput] = strawberry.field(default_factory=list, description=_JOIN_PATH_DESCRIPTION)


@prose_errors
@pydantic.input(
    LabelFilterByInputModel,
    description="One entry of a label layer's filter picker: draw only the objects whose row in a table this mask's FIELD edge keys into satisfies this rule. Which half applies follows from the column's declared role -- bounds for a measure column, an explicit value set for a categorical one",
)
class LabelFilterByInput:
    table: strawberry.ID = strawberry.field(description="The table dataset holding one row per object. Must be reachable from the layer's lens by a FIELD edge -- the edge `createTableDataset(keyedBy:)` authors and `attributePlans` discovers")
    column: str = strawberry.field(description="The column of that table whose value decides whether an object is drawn")
    min: float | None = strawberry.field(default=None, description="Lower bound, inclusive, in the column's own declared `unit`. For a measure column (role COORDINATE or ATTRIBUTE). Omit for an open lower end")
    max: float | None = strawberry.field(default=None, description="Upper bound, inclusive, in the column's own declared `unit`. For a measure column (role COORDINATE or ATTRIBUTE). Omit for an open upper end")
    values: list[str] | None = strawberry.field(default=None, description="The values that match, as strings -- ids included, the same vocabulary `classColors`' keys use. For a categorical column (role ID, LABEL, TRACK_ID or COLOR), where a bound would impose an order the values do not have")
    exclude: bool = strawberry.field(default=False, description="Whether the rule *removes* what it matches rather than keeping it. Inverts the whole rule, bounds and values alike")
    label: str | None = strawberry.field(default=None, description="What to call this filter in a picker, e.g. 'Large cells'. Two entries may share a column -- 'small' and 'large' over one measure are two different rules -- and this is what tells them apart")
    join_path: list[JoinStepInput] = strawberry.field(default_factory=list, description=_JOIN_PATH_DESCRIPTION)


_LABEL_COLOR_BYS_DESCRIPTION = (
    "The colourings this layer offers, in the order a picker should show them -- area through a colormap, cell type through class colours -- instead of hashing each id to a colour. Each names a "
    "table reachable from the layer's lens by a FIELD edge (author it with `createTableDataset(keyedBy:)`) and a column that table declares, because a colorBy naming an unrelated table is not a "
    "preference to hold onto until the edge shows up, it is a join nothing can execute. Which entry is drawn is `activeColorBy`; publishing a picker is not the same as choosing within it. Replaces "
    "the published picker wholesale -- its order is the display order, so there is nothing to merge on. Pass `[]` to remove every colouring and fall back to the hash"
)

_LABEL_ACTIVE_COLOR_BY_DESCRIPTION = (
    "Which entry of `colorBys` is drawn, as an index into it. Null hashes each id to a colour -- what having no colouring has always meant. Re-checked against the picker being written, never the "
    "stored one: if a new `colorBys` no longer holds the entry that was active, the layer falls back to the hash -- name `activeColorBy` in the same call to point at another entry instead"
)

_LABEL_FILTER_BYS_DESCRIPTION = (
    "The filters this layer offers, in the order a picker should show them -- 'large cells', 'not debris' -- each keeping or dropping objects by a column of a table this mask's FIELD edge keys into. "
    "Which half of the rule applies follows from the column's declared role: `min`/`max` bounds over a measure column, an explicit `values` set over a categorical one. Two entries may share a column, "
    "because two ranges over one measure are two different rules. Which of them are actually applied is `activeFilterBys`. Replaces the published filters wholesale, as `colorBys` does; pass `[]` to "
    "remove every rule and draw all objects"
)

_LABEL_ACTIVE_FILTER_BYS_DESCRIPTION = (
    "Which entries of `filterBys` are applied, as indices into it. Several at once is the normal case -- they combine with AND, and an object is drawn when every active rule keeps it. Empty applies "
    "none of them, so everything draws. Re-checked against the filters being written: a new `filterBys` that no longer holds an applied rule drops it from this set rather than leaving it dangling"
)


@prose_errors
@pydantic.input(
    LabelRenderInputModel,
    description="How a label layer's discrete object ids become color. Every field is optional; omitted ones keep their current value on an update, and take their default on a create",
)
class LabelRenderInput:
    intensity_axis: str | None = strawberry.field(default=None, description="The lens axis to index, or null when the pixel value itself is the id (the common case for masks)")
    intensity_index: int | None = strawberry.field(default=None, description="The index along that axis to render (default 0)")
    seed: int | None = strawberry.field(default=None, description="The seed of the hash mapping an id to its color. Changing it repaints every object, which is how two touching objects that happened to hash alike are separated (default 0)")
    background: int | None = strawberry.field(default=None, description="The id drawn fully transparent -- the 'not an object' value (default 0)")
    opacity: float | None = strawberry.field(default=None, description="Opacity applied to the colored ids within the layer, from 0 to 1 (default 1.0)")
    contour: bool | None = strawberry.field(default=None, description="Whether objects are drawn as outlines rather than filled, so the data underneath stays visible (default false)")
    contour_width: float | None = strawberry.field(default=None, description="The width of that outline, in pixels of the mask (default 1.0)")
    selected: list[int] | None = strawberry.field(default=None, description="The ids singled out for emphasis. An empty list means nothing is selected, which is not the same as everything")
    selection_color: list[int] | None = strawberry.field(default=None, description="The RGBA the selected ids take, overriding their hashed color: four components, each 0..255")
    show_unselected: bool | None = strawberry.field(default=None, description="Whether ids outside the selection still render. False isolates the selection (default true)")
    color_bys: list[LabelColorByInput] | None = strawberry.field(default=None, description=_LABEL_COLOR_BYS_DESCRIPTION)
    active_color_by: int | None = strawberry.field(default=None, description=_LABEL_ACTIVE_COLOR_BY_DESCRIPTION)
    filter_bys: list[LabelFilterByInput] | None = strawberry.field(default=None, description=_LABEL_FILTER_BYS_DESCRIPTION)
    active_filter_bys: list[int] | None = strawberry.field(default=None, description=_LABEL_ACTIVE_FILTER_BYS_DESCRIPTION)
