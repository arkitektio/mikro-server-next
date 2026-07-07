"""Pydantic node graph describing the composable rendering *inside* a single layer.

A layer is the unit that gets alpha-blended into a scene. Its internal render
recipe is a small tagged-union graph: ``channel`` leaf nodes each carry one
intensity channel of the layer's lens together with its own transfer function,
and a ``blend`` node composites its children with an in-layer blend mode. This
mirrors the tagged-union pattern in ``core/render/objects/models.py`` and lets a
single layer combine multiple channels (neuroglancer-style) while the layer as a
whole is still alpha-composited over the layers beneath it.

The union is structurally a tree (a ``blend`` may contain another ``blend``) so
that future nesting is non-breaking, but the canonical graph is one blend level
deep: a single ``blend`` root whose children are ``channel`` sources.
"""

from pydantic import BaseModel, Field
from typing import Literal, Union

from core import enums


class TransferFunctionModel(BaseModel):
    """How a single channel's intensities are mapped to color before compositing."""

    clim_min: float | None = None
    clim_max: float | None = None
    colormap: enums.ColorMap | None = None
    color: list[int] | None = None
    gamma: float | None = 1.0
    opacity: float | None = 1.0
    invert: bool | None = False
    categorical: bool | None = False


class ChannelSourceModel(BaseModel):
    """A single intensity channel of the layer's lens, with its own transfer function."""

    kind: Literal["channel"] = "channel"
    intensity_dim: str | None = None
    intensity_index: int = 0
    label: str | None = None
    visible: bool = True
    transfer: TransferFunctionModel = Field(default_factory=TransferFunctionModel)


class BlendNodeModel(BaseModel):
    """Composites its children using an in-layer blend mode."""

    kind: Literal["blend"] = "blend"
    blending: enums.Blending = enums.Blending.ADDITIVE
    children: list["LayerNodeUnion"]
    label: str | None = None


class ProjectionNodeModel(BaseModel):
    """Projects the composite of its children through the z-axis using a 3D rendering mode."""

    kind: Literal["projection"] = "projection"
    mode: enums.ProjectionMode = enums.ProjectionMode.MIP
    children: list["LayerNodeUnion"]
    label: str | None = None


LayerNodeUnion = Union[ChannelSourceModel, BlendNodeModel, ProjectionNodeModel]


class LayerRenderGraphModel(BaseModel):
    """The full in-layer render recipe, rooted at a single blend node."""

    root: BlendNodeModel


BlendNodeModel.update_forward_refs()
ProjectionNodeModel.update_forward_refs()
LayerRenderGraphModel.update_forward_refs()
