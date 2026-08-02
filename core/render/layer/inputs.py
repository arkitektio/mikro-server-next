"""GraphQL input types for the in-layer render graph.

GraphQL has no input unions, so — exactly like ``core/render/inputs/types.py`` —
a single recursive "fat" node input carries the fields of every node kind and is
discriminated at runtime by ``kind``. The mutation lowers this into the strict
tagged-union storage model (``core.render.layer.models``).
"""

from pydantic import BaseModel, field_validator, model_validator
from typing import Annotated, Optional

import strawberry
from strawberry.experimental import pydantic

from kanne_server import quantities
from kanne_server import scalars as kanne_scalars

from core import enums
from core.input_unions import prose_errors
from core.inputs.validators import assert_alpha, assert_contrast_limits, assert_positive, assert_rgba


class TransferFunctionInputModel(BaseModel):
    clim_min: float | None = None
    clim_max: float | None = None
    colormap: enums.ColorMap | None = None
    color: list[int] | None = None
    gamma: float | None = None
    opacity: float | None = None
    invert: bool | None = None
    categorical: bool | None = None

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
@pydantic.input(TransferFunctionInputModel, description="Transfer-function settings for a channel source in a layer render graph")
class TransferFunctionInput:
    clim_min: float | None = strawberry.field(default=None, description="Lower contrast limit, in the data's own intensity units -- not a normalized fraction")
    clim_max: float | None = strawberry.field(default=None, description="Upper contrast limit, in the data's own intensity units -- not a normalized fraction")
    colormap: enums.ColorMap | None = strawberry.field(default=None, description="The colormap (transfer function LUT) applied to the channel")
    color: list[int] | None = strawberry.field(default=None, description="A solid RGBA color to tint the channel with, instead of a colormap: four components, each 0..255")
    gamma: float | None = strawberry.field(default=None, description="Gamma correction applied to the normalized intensities. The exponent of a power law, so greater than zero")
    opacity: float | None = strawberry.field(default=None, description="Per-channel opacity within the layer, from 0 (transparent) to 1 (opaque)")
    invert: bool | None = strawberry.field(default=None, description="Whether the contrast mapping is inverted")
    categorical: bool | None = strawberry.field(default=None, description="Whether values are discrete labels (e.g. a segmentation / instance map) to be rendered as distinct colors rather than a continuous colormap")


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
