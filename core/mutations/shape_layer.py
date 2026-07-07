from kante.types import Info
import strawberry

from core import types, models, enums
import kante
from pydantic import BaseModel
from core.scoping import get_for_org


class CreateShapeLayerInputModel(BaseModel):
    scene: str
    data_roi: str
    affine_matrix: list[list[float]] | None = None
    blending: enums.Blending | None = None
    opacity: float | None = None
    visible: bool | None = None
    order: int | None = None
    stroke_color: list[int] | None = None
    fill_color: list[int] | None = None
    stroke_width: float | None = None
    filled: bool | None = None


@kante.pydantic_input(CreateShapeLayerInputModel, description="Create a layer that renders the vector geometry of a data ROI in a scene")
class CreateShapeLayerInput:
    scene: strawberry.ID = strawberry.field(description="The ID of the scene to place the layer in")
    data_roi: strawberry.ID = strawberry.field(description="The ID of the data ROI whose vectors this layer renders")
    affine_matrix: list[list[float]] | None = strawberry.field(default=None, description="Optional 4x4 affine mapping the ROI's local coordinates to stage micrometers")
    blending: enums.Blending | None = strawberry.field(default=None, description="Layer-level blend mode (default 'normal', i.e. alpha-over)")
    opacity: float | None = strawberry.field(default=None, description="Layer alpha for alpha-over compositing (default 1.0)")
    visible: bool | None = strawberry.field(default=None, description="Whether the layer participates in compositing (default true)")
    order: int | None = strawberry.field(default=None, description="Explicit z-index for back-to-front compositing (default 0)")
    stroke_color: list[int] | None = strawberry.field(default=None, description="Stroke (outline) color of the geometry, as RGBA (default white)")
    fill_color: list[int] | None = strawberry.field(default=None, description="Fill color of the geometry, as RGBA, or null for no fill")
    stroke_width: float | None = strawberry.field(default=None, description="Stroke width in scene units (default 1.0)")
    filled: bool | None = strawberry.field(default=None, description="Whether the geometry is filled with fill_color (default false)")


def create_shape_layer(info: Info, input: CreateShapeLayerInput) -> types.ShapeLayer:
    model = input.to_pydantic()

    scene = get_for_org(models.Scene, info, id=model.scene)
    data_roi = get_for_org(models.DataRoi, info, id=model.data_roi)

    layer = models.Layer.objects.create(
        kind=enums.LayerKind.SHAPE,
        scene=scene,
        data_roi=data_roi,
        affine_matrix=model.affine_matrix,
        blending=model.blending or enums.Blending.NORMAL,
        opacity=model.opacity if model.opacity is not None else 1.0,
        visible=model.visible if model.visible is not None else True,
        order=model.order or 0,
        stroke_color=model.stroke_color if model.stroke_color is not None else [255, 255, 255, 255],
        fill_color=model.fill_color,
        stroke_width=model.stroke_width if model.stroke_width is not None else 1.0,
        filled=model.filled if model.filled is not None else False,
    )

    return layer
