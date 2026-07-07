"""GraphQL output types for the in-layer render graph.

Mirrors the interface + ``pydantic.type`` pattern used by
``lightpath/objects/types.py``: a common ``LayerRenderNode`` interface with two
concrete implementations (``ChannelSourceNode`` and ``BlendNode``). Because the
interface is declared before ``BlendNode``, the recursive ``children`` field can
reference it directly without a lazy forward reference. Returning the raw
pydantic models from a resolver is enough — strawberry resolves each node to its
concrete type via the pydantic model it is bound to.
"""

import strawberry
from strawberry.experimental import pydantic

from core import enums
from core.render.layer import models


@pydantic.type(models.TransferFunctionModel, description="How a single channel's intensities are mapped to color before compositing")
class TransferFunction:
    clim_min: float | None = strawberry.field(default=None, description="Normalized (0..1) lower contrast limit")
    clim_max: float | None = strawberry.field(default=None, description="Normalized (0..1) upper contrast limit")
    colormap: enums.ColorMap | None = strawberry.field(default=None, description="The colormap (transfer function LUT) applied to the channel")
    color: list[int] | None = strawberry.field(default=None, description="A solid RGBA color to tint the channel with, instead of a colormap")
    gamma: float | None = strawberry.field(default=None, description="Gamma correction applied to the normalized intensities")
    opacity: float | None = strawberry.field(default=None, description="Per-channel opacity within the layer (0..1)")
    invert: bool | None = strawberry.field(default=None, description="Whether the contrast mapping is inverted")
    categorical: bool | None = strawberry.field(default=None, description="Whether values are discrete labels (e.g. a segmentation / instance map) to be rendered as distinct colors rather than a continuous colormap")


@strawberry.interface(description="A node in a layer's internal render graph")
class LayerRenderNode:
    kind: str = strawberry.field(description="The discriminator of the node, either 'channel' or 'blend'")
    label: str | None = strawberry.field(default=None, description="An optional human-readable label for the node")


@pydantic.type(models.ChannelSourceModel, description="A single intensity channel of the layer's lens, with its own transfer function")
class ChannelSourceNode(LayerRenderNode):
    kind: str = strawberry.field(description="Always 'channel'")
    intensity_dim: str | None = strawberry.field(default=None, description="The lens dimension carrying the intensity channels, or null when the pixel value itself is the intensity (e.g. a single-valued volume or label map)")
    intensity_index: int = strawberry.field(description="The index along the intensity dimension to render")
    visible: bool = strawberry.field(description="Whether this channel participates in the layer's composite")
    transfer: TransferFunction = strawberry.field(description="The transfer function mapping this channel to color")


@pydantic.type(models.BlendNodeModel, description="Composites its children using an in-layer blend mode")
class BlendNode(LayerRenderNode):
    kind: str = strawberry.field(description="Always 'blend'")
    blending: enums.Blending = strawberry.field(description="The blend mode used to composite the children")
    children: list[LayerRenderNode] = strawberry.field(description="The child nodes composited by this node")


@pydantic.type(models.ProjectionNodeModel, description="Projects the composite of its children through the z-axis using a 3D rendering mode")
class ProjectionNode(LayerRenderNode):
    kind: str = strawberry.field(description="Always 'projection'")
    mode: enums.ProjectionMode = strawberry.field(description="The 3D projection / rendering mode applied over the z-axis")
    children: list[LayerRenderNode] = strawberry.field(description="The child nodes whose composite is projected")


@pydantic.type(models.LayerRenderGraphModel, description="The composable render recipe inside a single layer, rooted at a blend node")
class LayerRenderGraph:
    root: BlendNode = strawberry.field(description="The root blend node of the layer's render graph")
