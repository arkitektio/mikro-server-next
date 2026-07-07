"""GraphQL input types for the in-layer render graph.

GraphQL has no input unions, so — exactly like ``core/render/inputs/types.py`` —
a single recursive "fat" node input carries the fields of every node kind and is
discriminated at runtime by ``kind``. The mutation lowers this into the strict
tagged-union storage model (``core.render.layer.models``).
"""

from pydantic import BaseModel
from typing import Annotated, Optional

import strawberry
from strawberry.experimental import pydantic

from core import enums


class TransferFunctionInputModel(BaseModel):
    clim_min: float | None = None
    clim_max: float | None = None
    colormap: enums.ColorMap | None = None
    color: list[int] | None = None
    gamma: float | None = None
    opacity: float | None = None
    invert: bool | None = None
    categorical: bool | None = None


class LayerNodeInputModel(BaseModel):
    kind: str
    label: str | None = None
    # channel node fields
    intensity_dim: str | None = None
    intensity_index: int | None = None
    visible: bool | None = None
    transfer: TransferFunctionInputModel | None = None
    # blend node fields
    blending: enums.Blending | None = None
    # projection node fields
    mode: enums.ProjectionMode | None = None
    children: list["LayerNodeInputModel"] | None = None


class LayerRenderGraphInputModel(BaseModel):
    root: LayerNodeInputModel


LayerNodeInputModel.update_forward_refs()
LayerRenderGraphInputModel.update_forward_refs()


@pydantic.input(TransferFunctionInputModel, description="Transfer-function settings for a channel source in a layer render graph")
class TransferFunctionInput:
    clim_min: float | None = strawberry.field(default=None, description="Normalized (0..1) lower contrast limit")
    clim_max: float | None = strawberry.field(default=None, description="Normalized (0..1) upper contrast limit")
    colormap: enums.ColorMap | None = strawberry.field(default=None, description="The colormap (transfer function LUT) applied to the channel")
    color: list[int] | None = strawberry.field(default=None, description="A solid RGBA color to tint the channel with, instead of a colormap")
    gamma: float | None = strawberry.field(default=None, description="Gamma correction applied to the normalized intensities")
    opacity: float | None = strawberry.field(default=None, description="Per-channel opacity within the layer (0..1)")
    invert: bool | None = strawberry.field(default=None, description="Whether the contrast mapping is inverted")
    categorical: bool | None = strawberry.field(default=None, description="Whether values are discrete labels (e.g. a segmentation / instance map) to be rendered as distinct colors rather than a continuous colormap")


@pydantic.input(LayerNodeInputModel, description="A node in a layer's internal render graph. A 'channel' node carries an intensity source and transfer function; a 'blend' node composites its children.")
class LayerNodeInput:
    kind: str = strawberry.field(description="The node discriminator, either 'channel' or 'blend'")
    label: str | None = strawberry.field(default=None, description="An optional human-readable label for the node")
    intensity_dim: str | None = strawberry.field(default=None, description="(channel) The lens dimension carrying the intensity channels")
    intensity_index: int | None = strawberry.field(default=None, description="(channel) The index along the intensity dimension to render")
    visible: bool | None = strawberry.field(default=None, description="(channel) Whether the channel participates in the composite")
    transfer: TransferFunctionInput | None = strawberry.field(default=None, description="(channel) The transfer function mapping this channel to color")
    blending: enums.Blending | None = strawberry.field(default=None, description="(blend) The blend mode used to composite the children")
    mode: enums.ProjectionMode | None = strawberry.field(default=None, description="(projection) The 3D projection / rendering mode applied over the z-axis")
    children: Optional[list[Annotated["LayerNodeInput", strawberry.lazy(__name__)]]] = strawberry.field(default=None, description="(blend/projection) The child nodes composited or projected by this node")


@pydantic.input(LayerRenderGraphInputModel, description="The composable render recipe inside a single layer, rooted at a blend node")
class LayerRenderGraphInput:
    root: LayerNodeInput = strawberry.field(description="The root blend node of the layer's render graph")
