from kante.types import Info
import strawberry

from core import types, models


from core import enums
import kante
from pydantic import BaseModel, Field
from core.logic import coords as coords_logic
from core.scoping import get_for_org
from core.mutations._generic import make_delete
from core.render.layer import inputs as layer_inputs
from core.render.layer import models as layer_models


def _build_layer_node(node: layer_inputs.LayerNodeInputModel, lens) -> layer_models.LayerNodeUnion:
    """Lower a fat GraphQL render-graph node into its strict tagged-union model, validating dims."""
    if node.kind == "channel":
        index = node.intensity_index or 0
        if node.intensity_dim:
            size = lens.get_size_of_dim(node.intensity_dim)  # raises ValueError if the dim is unknown
            if index < 0 or index >= size:
                raise ValueError(f"intensity_index {index} is out of range for dim '{node.intensity_dim}' (size {size})")
        transfer = node.transfer or layer_inputs.TransferFunctionInputModel()
        return layer_models.ChannelSourceModel(
            intensity_dim=node.intensity_dim,
            intensity_index=index,
            label=node.label,
            visible=node.visible if node.visible is not None else True,
            transfer=layer_models.TransferFunctionModel(**transfer.model_dump()),
        )
    if node.kind == "blend":
        children = node.children or []
        if not children:
            raise ValueError("A 'blend' render node requires at least one child")
        return layer_models.BlendNodeModel(
            blending=node.blending or enums.Blending.ADDITIVE,
            label=node.label,
            children=[_build_layer_node(child, lens) for child in children],
        )
    if node.kind == "projection":
        children = node.children or []
        if not children:
            raise ValueError("A 'projection' render node requires at least one child")
        return layer_models.ProjectionNodeModel(
            mode=node.mode or enums.ProjectionMode.MIP,
            label=node.label,
            children=[_build_layer_node(child, lens) for child in children],
        )
    raise ValueError(f"Unknown render node kind '{node.kind}'")


def build_render_graph(graph_input: layer_inputs.LayerRenderGraphInputModel, lens) -> dict:
    """Validate a layer render-graph input against the lens and return its JSON representation."""
    root = _build_layer_node(graph_input.root, lens)
    if not isinstance(root, layer_models.BlendNodeModel):
        raise ValueError("The root of a layer render graph must be a 'blend' node")
    return layer_models.LayerRenderGraphModel(root=root).model_dump(mode="json")


def assert_renderable(lens) -> coords_logic.RenderAxes:
    """Check a lens can be drawn, and return the axes a renderer maps to screen.

    The x/y/z/t/intensity mapping is no longer stored on the layer: it follows from
    the axis types, so two layers over one lens cannot disagree about it. See
    :func:`core.logic.coords.resolve_render_axes` -- and note that the rule it
    encodes ("the *last* spatial axis is x") is the opposite of the one this
    replaces, which took the first and so silently transposed x and y.
    """
    axes = coords_logic.resolve_render_axes(lens.axis_specs)
    assert lens.get_size_of_dim(axes.x) > 1, f"The x axis '{axes.x}' must have more than one pixel for rendering"
    assert lens.get_size_of_dim(axes.y) > 1, f"The y axis '{axes.y}' must have more than one pixel for rendering"
    return axes


def default_intensity_dim(lens, intensity_dim: str | None) -> str | None:
    """The channel axis a render node samples, defaulting to the lens' first channel axis."""
    return intensity_dim or coords_logic.resolve_render_axes(lens.axis_specs).intensity


def _channel_source(lens, intensity_dim: str | None, index: int, transfer: layer_models.TransferFunctionModel, label: str | None = None) -> layer_models.ChannelSourceModel:
    """Build a validated channel source node. ``intensity_dim`` may be None for single-valued data (e.g. a label map)."""
    if intensity_dim:
        size = lens.get_size_of_dim(intensity_dim)  # raises ValueError if the dim is unknown
        if index < 0 or index >= size:
            raise ValueError(f"intensity_index {index} is out of range for dim '{intensity_dim}' (size {size})")
    return layer_models.ChannelSourceModel(intensity_dim=intensity_dim, intensity_index=index, label=label, transfer=transfer)


class SliceInputModel(BaseModel):
    dim: str
    start: int | None = None
    stop: int | None = None
    step: int | None = None


@kante.pydantic_input(SliceInputModel, description="Input type for a dimension descriptor, which specifies a key and a kind for a dimension")
class SliceInput:
    dim: str = strawberry.field(description="The key of the dimension, e.g. 'x', 'y', 'z', 'c', or 't'")
    start: int | None = strawberry.field(default=None, description="The starting index of the slice, or None to start from the beginning")
    stop: int | None = strawberry.field(default=None, description="The stopping index of the slice, or None to go to the end")
    step: int | None = strawberry.field(default=None, description="The step size of the slice, or None to use the default step")


class CreateLayerInputModel(BaseModel):
    lens: str
    scene: str
    blending: enums.Blending | None = None
    opacity: float | None = None
    visible: bool | None = None
    order: int | None = None
    render_graph: layer_inputs.LayerRenderGraphInputModel
    intensity_dim: str | None = None


@kante.pydantic_input(CreateLayerInputModel, description="Input type for creating an image from an array-like object")
class CreateLayerInput:
    scene: strawberry.ID = strawberry.field(description="The ID of an existing scene to create the layer in. If not provided, a new scene will be created for the layer")
    lens: strawberry.ID = strawberry.field(description="The ID of an existing lens to create the layer from. If not provided, a new lens will be created for the layer")
    render_graph: layer_inputs.LayerRenderGraphInput = strawberry.field(description="The composable in-layer render graph (channels + transfer functions + in-layer blend). This is the single source of truth for how the image layer is rendered. For a simple single-channel layer use the createIntensityLayer mutation, which builds the graph for you.")
    blending: enums.Blending | None = strawberry.field(description="Optional blending mode used to composite this layer over the layers below it. Defaults to 'additive'.")
    opacity: float | None = strawberry.field(description="Optional layer alpha (0..1) for alpha-over compositing. Defaults to 1.0.")
    visible: bool | None = strawberry.field(description="Optional flag controlling whether the layer participates in compositing. Defaults to true.")
    order: int | None = strawberry.field(description="Optional explicit z-index for deterministic back-to-front compositing. Defaults to 0.")
    intensity_dim: str | None = strawberry.field(description="Optional name of the dimension to use as the intensity channel for rendering the layer. If not provided, the first channel dimension will be used by default.")


def create_layer(
    info: Info,
    input: CreateLayerInput,
) -> types.ImageLayer:
    model = input.to_pydantic()

    lens = get_for_org(models.Lens, info, id=model.lens)
    scene = get_for_org(models.Scene, info, id=model.scene)

    assert_renderable(lens)

    # The render graph is the single source of truth for how the image layer is
    # rendered; it may combine several channels, and per-channel dims are validated
    # while building it.
    render_graph = build_render_graph(model.render_graph, lens)

    layer = models.Layer.objects.create(
        kind=enums.LayerKind.IMAGE,
        lens=lens,
        scene=scene,
        blending=model.blending or enums.Blending.ADDITIVE,  # Default blending mode if not provided
        opacity=model.opacity if model.opacity is not None else 1.0,
        visible=model.visible if model.visible is not None else True,
        order=model.order or 0,
        render_graph=render_graph,
    )

    return layer


class UpdateLayerInputModel(BaseModel):
    id: str
    lens: str | None = None
    scene: str | None = None
    blending: enums.Blending | None = None
    opacity: float | None = None
    visible: bool | None = None
    order: int | None = None
    render_graph: layer_inputs.LayerRenderGraphInputModel | None = None
    intensity_dim: str | None = None


@kante.pydantic_input(UpdateLayerInputModel, description="Input type for creating an image from an array-like object")
class UpdateLayerInput:
    id: strawberry.ID = strawberry.field(description="The ID of the layer to update")
    scene: strawberry.ID | None = strawberry.field(description="The ID of an existing scene to create the layer in. If not provided, a new scene will be created for the layer")
    lens: strawberry.ID | None = strawberry.field(description="The ID of an existing lens to create the layer from. If not provided, a new lens will be created for the layer")
    blending: enums.Blending | None = strawberry.field(description="Optional blending mode used to composite this layer over the layers below it.")
    opacity: float | None = strawberry.field(description="Optional layer alpha (0..1) for alpha-over compositing.")
    visible: bool | None = strawberry.field(description="Optional flag controlling whether the layer participates in compositing.")
    order: int | None = strawberry.field(description="Optional explicit z-index for deterministic back-to-front compositing.")
    render_graph: layer_inputs.LayerRenderGraphInput | None = strawberry.field(description="Optional composable in-layer render graph. When provided, it replaces the layer's render graph (the single source of truth for how the image layer is rendered).")
    intensity_dim: str | None = strawberry.field(description="Optional name of the dimension to use as the intensity channel for rendering the layer. If not provided, the first channel dimension will be used by default.")


def update_layer(
    info: Info,
    input: UpdateLayerInput,
) -> types.ImageLayer:
    model = input.to_pydantic()

    layer = get_for_org(models.Layer, info, id=model.id)
    lens = get_for_org(models.Lens, info, id=model.lens) if model.lens else layer.lens
    scene = get_for_org(models.Scene, info, id=model.scene) if model.scene else layer.scene

    assert_renderable(lens)

    render_graph = None
    if model.render_graph is not None:
        # The render graph is the single source of truth for how the image layer is
        # rendered; per-channel dims are validated while building it.
        render_graph = build_render_graph(model.render_graph, lens)

    if model.lens:
        layer.lens = lens
    if model.scene:
        layer.scene = scene
    if model.blending:
        layer.blending = model.blending
    if model.opacity is not None:
        layer.opacity = model.opacity
    if model.visible is not None:
        layer.visible = model.visible
    if model.order is not None:
        layer.order = model.order
    if render_graph is not None:
        layer.render_graph = render_graph
    if model.intensity_dim:
        layer.intensity_dim = model.intensity_dim
    layer.save()
    return layer


# ---------------------------------------------------------------------------
# Convenience layer builders
#
# These wrap ``create_layer`` for the three most common microscopy display
# recipes so clients don't have to hand-assemble a render graph:
#   * createRgbLayer       - three channels rendered as red/green/blue
#   * createIntensityLayer - one channel through a colormap (fluorescence)
#   * createLabelLayer     - an instance / segmentation map of discrete labels
# Each resolves the layer's x/y/z/t dims from the lens, builds a validated
# render graph, and creates the layer. The layer is still the alpha-blended
# unit (opacity + layer-level blending); the recipe lives inside it.
# ---------------------------------------------------------------------------


def _create_graph_layer(info: Info, *, lens_id: str, scene_id: str, root: layer_models.BlendNodeModel, blending: enums.Blending, opacity: float | None, visible: bool | None, order: int | None) -> "models.Layer":
    """Create an image layer from a prebuilt render graph. Placement is a scene-level edge, not a layer field."""
    lens = get_for_org(models.Lens, info, id=lens_id)
    scene = get_for_org(models.Scene, info, id=scene_id)
    render_graph = layer_models.LayerRenderGraphModel(root=root).model_dump(mode="json")
    return models.Layer.objects.create(
        kind=enums.LayerKind.IMAGE,
        lens=lens,
        scene=scene,
        blending=blending,
        opacity=opacity if opacity is not None else 1.0,
        visible=visible if visible is not None else True,
        order=order or 0,
        render_graph=render_graph,
    )


class CreateRgbLayerInputModel(BaseModel):
    lens: str
    scene: str
    intensity_dim: str | None = None
    red_index: int = 0
    green_index: int = 1
    blue_index: int = 2
    clim_min: float | None = None
    clim_max: float | None = None
    opacity: float | None = None
    visible: bool | None = None
    order: int | None = None


@kante.pydantic_input(CreateRgbLayerInputModel, description="Create a layer that composites three channels of a lens as red, green and blue")
class CreateRgbLayerInput:
    scene: strawberry.ID = strawberry.field(description="The ID of the scene to place the layer in")
    lens: strawberry.ID = strawberry.field(description="The ID of the lens providing the data")
    intensity_dim: str | None = strawberry.field(default=None, description="The channel dimension to index for the three colors. Defaults to the lens' first channel dimension.")
    red_index: int | None = strawberry.field(default=None, description="Channel index mapped to red (default 0)")
    green_index: int | None = strawberry.field(default=None, description="Channel index mapped to green (default 1)")
    blue_index: int | None = strawberry.field(default=None, description="Channel index mapped to blue (default 2)")
    clim_min: float | None = strawberry.field(default=None, description="Normalized (0..1) lower contrast limit applied to all three channels")
    clim_max: float | None = strawberry.field(default=None, description="Normalized (0..1) upper contrast limit applied to all three channels")
    opacity: float | None = strawberry.field(default=None, description="Layer alpha for alpha-over compositing (default 1.0)")
    visible: bool | None = strawberry.field(default=None, description="Whether the layer participates in compositing (default true)")
    order: int | None = strawberry.field(default=None, description="Explicit z-index for back-to-front compositing (default 0)")


def create_rgb_layer(info: Info, input: CreateRgbLayerInput) -> types.ImageLayer:
    model = input.to_pydantic()
    lens = get_for_org(models.Lens, info, id=model.lens)
    assert_renderable(lens)
    intensity_dim = default_intensity_dim(lens, model.intensity_dim)

    def transfer(colormap: enums.ColorMap) -> layer_models.TransferFunctionModel:
        return layer_models.TransferFunctionModel(colormap=colormap, clim_min=model.clim_min, clim_max=model.clim_max)

    children = [
        _channel_source(lens, intensity_dim, model.red_index if model.red_index is not None else 0, transfer(enums.ColorMap.RED), label="red"),
        _channel_source(lens, intensity_dim, model.green_index if model.green_index is not None else 1, transfer(enums.ColorMap.GREEN), label="green"),
        _channel_source(lens, intensity_dim, model.blue_index if model.blue_index is not None else 2, transfer(enums.ColorMap.BLUE), label="blue"),
    ]
    root = layer_models.BlendNodeModel(blending=enums.Blending.ADDITIVE, children=children, label="rgb")
    return _create_graph_layer(
        info, lens_id=model.lens, scene_id=model.scene, root=root,
        blending=enums.Blending.NORMAL, opacity=model.opacity, visible=model.visible, order=model.order,
    )


class CreateIntensityLayerInputModel(BaseModel):
    lens: str
    scene: str
    intensity_dim: str | None = None
    intensity_index: int = 0
    colormap: enums.ColorMap | None = None
    clim_min: float | None = None
    clim_max: float | None = None
    gamma: float | None = None
    blending: enums.Blending | None = None
    opacity: float | None = None
    visible: bool | None = None
    order: int | None = None


@kante.pydantic_input(CreateIntensityLayerInputModel, description="Create a single-channel intensity layer rendered through a colormap (e.g. a fluorescence channel)")
class CreateIntensityLayerInput:
    scene: strawberry.ID = strawberry.field(description="The ID of the scene to place the layer in")
    lens: strawberry.ID = strawberry.field(description="The ID of the lens providing the data")
    intensity_dim: str | None = strawberry.field(default=None, description="The channel dimension to index. Defaults to the lens' first channel dimension; may be null for single-valued data.")
    intensity_index: int | None = strawberry.field(default=None, description="The channel index to render (default 0)")
    colormap: enums.ColorMap | None = strawberry.field(default=None, description="The colormap to render the intensity through (default 'grey')")
    clim_min: float | None = strawberry.field(default=None, description="Normalized (0..1) lower contrast limit")
    clim_max: float | None = strawberry.field(default=None, description="Normalized (0..1) upper contrast limit")
    gamma: float | None = strawberry.field(default=None, description="Gamma correction (default 1.0)")
    blending: enums.Blending | None = strawberry.field(default=None, description="Layer-level blend mode (default 'additive', suitable for fluorescence)")
    opacity: float | None = strawberry.field(default=None, description="Layer alpha for alpha-over compositing (default 1.0)")
    visible: bool | None = strawberry.field(default=None, description="Whether the layer participates in compositing (default true)")
    order: int | None = strawberry.field(default=None, description="Explicit z-index for back-to-front compositing (default 0)")


def create_intensity_layer(info: Info, input: CreateIntensityLayerInput) -> types.ImageLayer:
    model = input.to_pydantic()
    lens = get_for_org(models.Lens, info, id=model.lens)
    assert_renderable(lens)
    intensity_dim = default_intensity_dim(lens, model.intensity_dim)

    transfer = layer_models.TransferFunctionModel(
        colormap=model.colormap or enums.ColorMap.GREY,
        clim_min=model.clim_min,
        clim_max=model.clim_max,
        gamma=model.gamma if model.gamma is not None else 1.0,
    )
    child = _channel_source(lens, intensity_dim, model.intensity_index or 0, transfer, label="intensity")
    root = layer_models.BlendNodeModel(blending=enums.Blending.ADDITIVE, children=[child], label="intensity")
    return _create_graph_layer(
        info, lens_id=model.lens, scene_id=model.scene, root=root,
        blending=model.blending or enums.Blending.ADDITIVE, opacity=model.opacity, visible=model.visible, order=model.order,
    )


class CreateLabelLayerInputModel(BaseModel):
    lens: str
    scene: str
    intensity_dim: str | None = None
    intensity_index: int = 0
    opacity: float | None = None
    visible: bool | None = None
    order: int | None = None


@kante.pydantic_input(CreateLabelLayerInputModel, description="Create a label layer that renders an instance / segmentation map, mapping discrete integer labels to distinct colors")
class CreateLabelLayerInput:
    scene: strawberry.ID = strawberry.field(description="The ID of the scene to place the layer in")
    lens: strawberry.ID = strawberry.field(description="The ID of the lens providing the label / instance-map data")
    intensity_dim: str | None = strawberry.field(default=None, description="The channel dimension to index, or null when the pixel value itself is the label (the common case for masks)")
    intensity_index: int | None = strawberry.field(default=None, description="The channel index to render (default 0)")
    opacity: float | None = strawberry.field(default=None, description="Layer alpha for alpha-over compositing (default 1.0)")
    visible: bool | None = strawberry.field(default=None, description="Whether the layer participates in compositing (default true)")
    order: int | None = strawberry.field(default=None, description="Explicit z-index for back-to-front compositing (default 0)")


def create_label_layer(info: Info, input: CreateLabelLayerInput) -> types.ImageLayer:
    model = input.to_pydantic()
    lens = get_for_org(models.Lens, info, id=model.lens)
    assert_renderable(lens)
    intensity_dim = default_intensity_dim(lens, model.intensity_dim)

    transfer = layer_models.TransferFunctionModel(categorical=True)
    child = _channel_source(lens, intensity_dim, model.intensity_index or 0, transfer, label="labels")
    root = layer_models.BlendNodeModel(blending=enums.Blending.NORMAL, children=[child], label="labels")
    return _create_graph_layer(
        info, lens_id=model.lens, scene_id=model.scene, root=root,
        blending=enums.Blending.NORMAL, opacity=model.opacity, visible=model.visible, order=model.order,
    )


class CreateVolumeLayerInputModel(BaseModel):
    lens: str
    scene: str
    mode: enums.ProjectionMode | None = None
    intensity_dim: str | None = None
    intensity_index: int = 0
    colormap: enums.ColorMap | None = None
    clim_min: float | None = None
    clim_max: float | None = None
    gamma: float | None = None
    blending: enums.Blending | None = None
    opacity: float | None = None
    visible: bool | None = None
    order: int | None = None


@kante.pydantic_input(CreateVolumeLayerInputModel, description="Create a single-channel layer rendered as a 3D volume projection (MIP / attenuated-MIP / volume / isosurface) over its z-axis")
class CreateVolumeLayerInput:
    scene: strawberry.ID = strawberry.field(description="The ID of the scene to place the layer in")
    lens: strawberry.ID = strawberry.field(description="The ID of the lens providing the volumetric data")
    mode: enums.ProjectionMode | None = strawberry.field(default=None, description="The 3D projection / rendering mode over the z-axis (default 'mip')")
    intensity_dim: str | None = strawberry.field(default=None, description="The channel dimension to index. Defaults to the lens' first channel dimension; may be null for single-valued data.")
    intensity_index: int | None = strawberry.field(default=None, description="The channel index to render (default 0)")
    colormap: enums.ColorMap | None = strawberry.field(default=None, description="The colormap to render the intensity through (default 'grey')")
    clim_min: float | None = strawberry.field(default=None, description="Normalized (0..1) lower contrast limit")
    clim_max: float | None = strawberry.field(default=None, description="Normalized (0..1) upper contrast limit")
    gamma: float | None = strawberry.field(default=None, description="Gamma correction (default 1.0)")
    blending: enums.Blending | None = strawberry.field(default=None, description="Layer-level blend mode (default 'additive')")
    opacity: float | None = strawberry.field(default=None, description="Layer alpha for alpha-over compositing (default 1.0)")
    visible: bool | None = strawberry.field(default=None, description="Whether the layer participates in compositing (default true)")
    order: int | None = strawberry.field(default=None, description="Explicit z-index for back-to-front compositing (default 0)")


def create_volume_layer(info: Info, input: CreateVolumeLayerInput) -> types.ImageLayer:
    model = input.to_pydantic()
    lens = get_for_org(models.Lens, info, id=model.lens)
    assert_renderable(lens)
    intensity_dim = default_intensity_dim(lens, model.intensity_dim)

    transfer = layer_models.TransferFunctionModel(
        colormap=model.colormap or enums.ColorMap.GREY,
        clim_min=model.clim_min,
        clim_max=model.clim_max,
        gamma=model.gamma if model.gamma is not None else 1.0,
    )
    child = _channel_source(lens, intensity_dim, model.intensity_index or 0, transfer, label="volume")
    projection = layer_models.ProjectionNodeModel(mode=model.mode or enums.ProjectionMode.MIP, children=[child], label="projection")
    root = layer_models.BlendNodeModel(blending=enums.Blending.ADDITIVE, children=[projection], label="volume")
    return _create_graph_layer(
        info, lens_id=model.lens, scene_id=model.scene, root=root,
        blending=model.blending or enums.Blending.ADDITIVE, opacity=model.opacity, visible=model.visible, order=model.order,
    )


class DeleteLayerInputModel(BaseModel):
    id: str = Field(description="The ID of the layer to delete")


@kante.pydantic_input(DeleteLayerInputModel, description="Input for deleting a layer by ID")
class DeleteLayerInput:
    """Input for deleting a layer by ID"""

    id: strawberry.ID = strawberry.field(description="The ID of the layer to delete")


delete_layer = make_delete(models.Layer, DeleteLayerInput)
