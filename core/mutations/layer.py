from kante.types import Info
import strawberry

from core import types, models, scalars
from datalayer.datalayer import get_current_datalayer
import json


from core import enums
from django.conf import settings
from django.contrib.auth import get_user_model
from core.managers import auto_create_views
import kante
from pydantic import BaseModel, Field
from core.scoping import get_for_org


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
    affine_matrix: list[list[float]] | None = None
    colormap: enums.ColorMap | None = None
    color: list[int] | None = None
    clim_min: float | None = None
    clim_max: float | None = None
    blending: enums.Blending | None = None
    x_dim: str | None = None
    y_dim: str | None = None
    z_dim: str | None = None
    t_dim: str | None = None
    intensity_dim: str | None = None


@kante.pydantic_input(CreateLayerInputModel, description="Input type for creating an image from an array-like object")
class CreateLayerInput:
    scene: strawberry.ID = strawberry.field(description="The ID of an existing scene to create the layer in. If not provided, a new scene will be created for the layer")
    lens: strawberry.ID = strawberry.field(description="The ID of an existing lens to create the layer from. If not provided, a new lens will be created for the layer")
    affine_matrix: list[list[float]] | None = strawberry.field(
        description="Optional 4x4 affine transformation matrix to apply to the layer, mapping local pixel coordinates to stage micrometers. Should be provided as a list of 4 lists, each containing 4 floats, representing the rows of the matrix. If not provided, the identity matrix will be used."
    )
    colormap: enums.ColorMap | None = strawberry.field(description="Optional colormap to apply to the layer, e.g. 'viridis', 'gray', etc. If not provided, a default colormap will be used.")
    color: list[int] | None = strawberry.field(description="Optional solid color to apply to the layer, specified as a hex string like '#ff0000' for red. If not provided, no solid color will be applied.")
    clim_min: float | None = strawberry.field(description="Optional NORMALIZED minimum intensity value for colormap scaling. This should be a float from 0 to 1")
    clim_max: float | None = strawberry.field(description="Optional NORMALIZED maximum intensity value for colormap scaling. This should be a float from 0 to 1")
    x_dim: str | None = strawberry.field(description="Optional name of the dimension to use as the x-axis for rendering the layer. If not provided, the first spatial dimension will be used by default.")
    y_dim: str | None = strawberry.field(description="Optional name of the dimension to use as the y-axis for rendering the layer. If not provided, the second spatial dimension will be used by default.")
    z_dim: str | None = strawberry.field(description="Optional name of the dimension to use as the z-axis for rendering the layer (for 3D data). If not provided, the third spatial dimension will be used by default.")
    t_dim: str | None = strawberry.field(description="Optional name of the dimension to use as the time axis for rendering the layer (for time series data). If not provided, the first time dimension will be used by default.")
    intensity_dim: str | None = strawberry.field(description="Optional name of the dimension to use as the intensity channel for rendering the layer. If not provided, the first channel dimension will be used by default.")


def create_layer(
    info: Info,
    input: CreateLayerInput,
) -> types.Layer:
    model = input.to_pydantic()

    lens = get_for_org(models.Lens, info, id=model.lens)
    scene = get_for_org(models.Scene, info, id=model.scene)

    spatial_dims = [desc for desc in lens.dim_descriptors_list if desc.kind == "space"]
    channel_dims = [desc for desc in lens.dim_descriptors_list if desc.kind == "channel"]
    t_dims = [desc for desc in lens.dim_descriptors_list if desc.kind == "time"]

    x_dim = model.x_dim or spatial_dims[0].key
    y_dim = model.y_dim or spatial_dims[1].key
    z_dim = model.z_dim or (spatial_dims[2].key if len(spatial_dims) > 2 else None)
    t_dim = model.t_dim or (t_dims[0].key if t_dims else None)
    intensity_dim = model.intensity_dim or channel_dims[0].key if channel_dims else None

    assert lens.get_size_of_dim(x_dim) > 1, f"Selected x_dim '{x_dim}' must have more than one pixel for rendering"
    assert lens.get_size_of_dim(y_dim) > 1, f"Selected y_dim '{y_dim}' must have more than one pixel for rendering"
    if intensity_dim:
        assert lens.get_size_of_dim(intensity_dim) == 1, f"Selected intensity_dim '{intensity_dim}' must have exactly one pixel for rendering as a single intensity channel. Each layer can only render on channel, decompose your data into separate layers if you want to render multiple channels."

    layer = models.Layer.objects.create(
        lens=lens,
        scene=scene,
        affine_matrix=model.affine_matrix,
        colormap=model.colormap or enums.ColorMap.VIRIDIS,  # Default colormap if not provided
        color=model.color,
        clim_min=model.clim_min,
        clim_max=model.clim_max,
        blending=model.blending or enums.Blending.ADDITIVE,  # Default blending mode if not provided
        x_dim=x_dim,
        y_dim=y_dim,
        z_dim=z_dim,
        t_dim=t_dim,
        intensity_dim=intensity_dim,
    )

    return layer


class UpdateLayerInputModel(BaseModel):
    id: str
    lens: str | None = None
    scene: str | None = None
    affine_matrix: list[list[float]] | None = None
    colormap: enums.ColorMap | None = None
    color: list[int] | None = None
    clim_min: float | None = None
    clim_max: float | None = None
    blending: enums.Blending | None = None
    x_dim: str | None = None
    y_dim: str | None = None
    z_dim: str | None = None
    t_dim: str | None = None
    intensity_dim: str | None = None


@kante.pydantic_input(UpdateLayerInputModel, description="Input type for creating an image from an array-like object")
class UpdateLayerInput:
    id: strawberry.ID = strawberry.field(description="The ID of the layer to update")
    scene: strawberry.ID | None = strawberry.field(description="The ID of an existing scene to create the layer in. If not provided, a new scene will be created for the layer")
    lens: strawberry.ID | None = strawberry.field(description="The ID of an existing lens to create the layer from. If not provided, a new lens will be created for the layer")
    affine_matrix: list[list[float]] | None = strawberry.field(
        description="Optional 4x4 affine transformation matrix to apply to the layer, mapping local pixel coordinates to stage micrometers. Should be provided as a list of 4 lists, each containing 4 floats, representing the rows of the matrix. If not provided, the identity matrix will be used."
    )
    colormap: enums.ColorMap | None = strawberry.field(description="Optional colormap to apply to the layer, e.g. 'viridis', 'gray', etc. If not provided, a default colormap will be used.")
    color: list[int] | None = strawberry.field(description="Optional solid color to apply to the layer, specified as a hex string like '#ff0000' for red. If not provided, no solid color will be applied.")
    clim_min: float | None = strawberry.field(description="Optional NORMALIZED minimum intensity value for colormap scaling. This should be a float from 0 to 1")
    clim_max: float | None = strawberry.field(description="Optional NORMALIZED maximum intensity value for colormap scaling. This should be a float from 0 to 1")
    x_dim: str | None = strawberry.field(description="Optional name of the dimension to use as the x-axis for rendering the layer. If not provided, the first spatial dimension will be used by default.")
    y_dim: str | None = strawberry.field(description="Optional name of the dimension to use as the y-axis for rendering the layer. If not provided, the second spatial dimension will be used by default.")
    z_dim: str | None = strawberry.field(description="Optional name of the dimension to use as the z-axis for rendering the layer (for 3D data). If not provided, the third spatial dimension will be used by default.")
    t_dim: str | None = strawberry.field(description="Optional name of the dimension to use as the time axis for rendering the layer (for time series data). If not provided, the first time dimension will be used by default.")
    intensity_dim: str | None = strawberry.field(description="Optional name of the dimension to use as the intensity channel for rendering the layer. If not provided, the first channel dimension will be used by default.")


def update_layer(
    info: Info,
    input: UpdateLayerInput,
) -> types.Layer:
    model = input.to_pydantic()

    layer = get_for_org(models.Layer, info, id=model.id)
    lens = get_for_org(models.Lens, info, id=model.lens) if model.lens else layer.lens
    scene = get_for_org(models.Scene, info, id=model.scene) if model.scene else layer.scene

    spatial_dims = [desc for desc in lens.dim_descriptors_list if desc.kind == "space"]
    channel_dims = [desc for desc in lens.dim_descriptors_list if desc.kind == "channel"]
    t_dims = [desc for desc in lens.dim_descriptors_list if desc.kind == "time"]

    x_dim = model.x_dim or spatial_dims[0].key
    y_dim = model.y_dim or spatial_dims[1].key
    z_dim = model.z_dim or (spatial_dims[2].key if len(spatial_dims) > 2 else None)
    t_dim = model.t_dim or (t_dims[0].key if t_dims else None)
    intensity_dim = model.intensity_dim or channel_dims[0].key if channel_dims else None

    assert lens.get_size_of_dim(x_dim) > 1, f"Selected x_dim '{x_dim}' must have more than one pixel for rendering"
    assert lens.get_size_of_dim(y_dim) > 1, f"Selected y_dim '{y_dim}' must have more than one pixel for rendering"
    if intensity_dim:
        assert lens.get_size_of_dim(intensity_dim) == 1, f"Selected intensity_dim '{intensity_dim}' must have exactly one pixel for rendering as a single intensity channel. Each layer can only render on channel, decompose your data into separate layers if you want to render multiple channels."

    if model.lens:
        layer.lens = lens
    if model.scene:
        layer.scene = scene
    if model.affine_matrix:
        layer.affine_matrix = model.affine_matrix
    if model.colormap:
        layer.colormap = model.colormap
    if model.color:
        layer.color = model.color
    if model.clim_min is not None:
        layer.clim_min = model.clim_min
    if model.clim_max is not None:
        layer.clim_max = model.clim_max
    if model.blending:
        layer.blending = model.blending
    if model.x_dim:
        layer.x_dim = model.x_dim
    if model.y_dim:
        layer.y_dim = model.y_dim
    if model.z_dim:
        layer.z_dim = model.z_dim
    if model.t_dim:
        layer.t_dim = model.t_dim
    if model.intensity_dim:
        layer.intensity_dim = model.intensity_dim
    layer.save()
    return layer
