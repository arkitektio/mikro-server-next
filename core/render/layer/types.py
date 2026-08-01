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

from kanne_server import scalars as kanne_scalars

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
    kind: str = strawberry.field(description="The discriminator of the node: 'channel', 'phasor', 'blend' or 'projection'")
    label: str | None = strawberry.field(default=None, description="An optional human-readable label for the node")


@pydantic.type(models.ChannelSourceModel, description="A single intensity channel of the layer's lens, with its own transfer function")
class ChannelSourceNode(LayerRenderNode):
    kind: str = strawberry.field(description="Always 'channel'")
    intensity_axis: str | None = strawberry.field(default=None, description="The lens axis carrying the intensity channels, or null when the pixel value itself is the intensity (e.g. a single-valued volume or label map)")
    intensity_index: int = strawberry.field(description="The index along the intensity axis to render")
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


@pydantic.type(models.PhasorCursorModel, description="A region of phasor space, and the color the pixels falling inside it are painted")
class PhasorCursor:
    kind: enums.PhasorCursorKind = strawberry.field(description="The shape of the region")
    g: float | None = strawberry.field(default=None, description="(circle) The g coordinate of the centre")
    s: float | None = strawberry.field(default=None, description="(circle) The s coordinate of the centre")
    radius: float | None = strawberry.field(default=None, description="(circle) The radius of the disc, in phasor units")
    points: list[list[float]] | None = strawberry.field(default=None, description="(polygon) The (g, s) vertices of the region, at least three")
    color: list[int] | None = strawberry.field(default=None, description="The RGBA color the pixels inside this region take, overriding the colormap")
    label: str | None = strawberry.field(default=None, description="An optional human-readable label, e.g. the species this region selects")
    visible: bool = strawberry.field(description="Whether this cursor colors the image")


@pydantic.type(models.PhasorTransferModel, description="How a phasor becomes the pixel's color. The transfer function of a phasor source: it maps the reduction's output -- a (g, s) pair plus a photon count -- rather than a sampled scalar, which is why it is not a TransferFunction")
class PhasorTransfer:
    mode: enums.PhasorColorMode = strawberry.field(description="What the hue is derived from: the phasor's phase, its modulus, or the mean of both")
    min: kanne_scalars.GenericQuantity | None = strawberry.field(default=None, description="The lower bound of the derived value, in its own dimension: a duration ('0.5 ns') over a microtime axis, a wavelength ('480 nm') over a spectrum axis")
    max: kanne_scalars.GenericQuantity | None = strawberry.field(default=None, description="The upper bound of the derived value, in its own dimension")
    colormap: enums.ColorMap = strawberry.field(description="The colormap the derived value is mapped through")
    weight_by_intensity: bool = strawberry.field(description="Whether the photon count modulates the brightness, so that hue carries the phasor and brightness the signal")
    intensity: TransferFunction = strawberry.field(description="The transfer function applied to that photon count: contrast limits, gamma, opacity")
    cursors: list[PhasorCursor] = strawberry.field(description="Regions of phasor space whose pixels take a fixed color, overriding the colormap")


@pydantic.type(
    models.PhasorNodeModel,
    description="Reduces one axis of the lens to a phasor -- the DFT of each pixel's profile along it, at a harmonic -- and colors the pixel by the result. Over a microtime axis the phase reads as a fluorescence lifetime; over a spectrum axis, as a spectral centre of mass. Its output is a raster that composites into the scene like any other leaf, not a scatter plot",
)
class PhasorNode(LayerRenderNode):
    kind: str = strawberry.field(description="Always 'phasor'")
    visible: bool = strawberry.field(description="Whether this node participates in the layer's composite")
    phasor_axis: str = strawberry.field(description="The lens axis the phasor is taken over. Must be a MICROTIME or SPECTRUM axis -- the continuous ones a DFT means anything over")
    intensity_axis: str | None = strawberry.field(default=None, description="The lens axis carrying the detection channels, or null when the cube has none")
    intensity_index: int = strawberry.field(description="The index along the intensity axis to reduce")
    harmonic: int = strawberry.field(description="The harmonic of the transform. 1 is the fundamental; 2 resolves multi-exponential decays a first harmonic cannot separate")
    transfer: PhasorTransfer = strawberry.field(description="How the resulting phasor becomes the pixel's color")


@pydantic.type(models.LayerRenderGraphModel, description="The composable render recipe inside a single layer, rooted at a blend node")
class LayerRenderGraph:
    root: BlendNode = strawberry.field(description="The root blend node of the layer's render graph")
