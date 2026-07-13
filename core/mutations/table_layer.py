from kante.types import Info
import strawberry

from core import types, models, enums
import kante
from pydantic import BaseModel
from core.scoping import get_for_org


class CreatePointLayerInputModel(BaseModel):
    scene: str
    table: str
    x_column: str
    y_column: str
    z_column: str | None = None
    t_column: str | None = None
    size_column: str | None = None
    color_column: str | None = None
    id_column: str | None = None
    point_size: float | None = None
    colormap: enums.ColorMap | None = None
    blending: enums.Blending | None = None
    opacity: float | None = None
    visible: bool | None = None
    order: int | None = None


@kante.pydantic_input(CreatePointLayerInputModel, description="Create a layer that renders a point cloud (e.g. SMLM localisations, centroids) from columns of a table")
class CreatePointLayerInput:
    scene: strawberry.ID = strawberry.field(description="The ID of the scene to place the layer in")
    table: strawberry.ID = strawberry.field(description="The ID of the table whose columns provide the point coordinates")
    x_column: str = strawberry.field(description="The table column mapped to the x coordinate")
    y_column: str = strawberry.field(description="The table column mapped to the y coordinate")
    z_column: str | None = strawberry.field(default=None, description="The table column mapped to the z coordinate (for 3D points)")
    t_column: str | None = strawberry.field(default=None, description="The table column mapped to the time coordinate")
    size_column: str | None = strawberry.field(default=None, description="The table column mapped to per-point size")
    color_column: str | None = strawberry.field(default=None, description="The table column mapped to per-point color/intensity (used with colormap)")
    id_column: str | None = strawberry.field(default=None, description="The table column identifying each point")
    point_size: float | None = strawberry.field(default=None, description="The default point size in scene units (default 3.0)")
    colormap: enums.ColorMap | None = strawberry.field(default=None, description="The colormap used to color points by their color_column (default 'viridis')")
    blending: enums.Blending | None = strawberry.field(default=None, description="Layer-level blend mode (default 'normal', i.e. alpha-over)")
    opacity: float | None = strawberry.field(default=None, description="Layer alpha for alpha-over compositing (default 1.0)")
    visible: bool | None = strawberry.field(default=None, description="Whether the layer participates in compositing (default true)")
    order: int | None = strawberry.field(default=None, description="Explicit z-index for back-to-front compositing (default 0)")


def create_point_layer(info: Info, input: CreatePointLayerInput) -> types.PointLayer:
    model = input.to_pydantic()

    scene = get_for_org(models.Scene, info, id=model.scene)
    table = get_for_org(models.Table, info, id=model.table)

    return models.Layer.objects.create(
        kind=enums.LayerKind.POINT,
        scene=scene,
        table=table,
        x_column=model.x_column,
        y_column=model.y_column,
        z_column=model.z_column,
        t_column=model.t_column,
        size_column=model.size_column,
        color_column=model.color_column,
        id_column=model.id_column,
        point_size=model.point_size if model.point_size is not None else 3.0,
        colormap=model.colormap or enums.ColorMap.VIRIDIS,
        blending=model.blending or enums.Blending.NORMAL,
        opacity=model.opacity if model.opacity is not None else 1.0,
        visible=model.visible if model.visible is not None else True,
        order=model.order or 0,
    )


class CreateTrackLayerInputModel(BaseModel):
    scene: str
    table: str
    track_id_column: str
    x_column: str
    y_column: str
    z_column: str | None = None
    t_column: str | None = None
    color_by_column: str | None = None
    line_width: float | None = None
    colormap: enums.ColorMap | None = None
    blending: enums.Blending | None = None
    opacity: float | None = None
    visible: bool | None = None
    order: int | None = None


@kante.pydantic_input(CreateTrackLayerInputModel, description="Create a layer that renders trajectories (e.g. particle/cell tracks) from columns of a table, grouped by a track id")
class CreateTrackLayerInput:
    scene: strawberry.ID = strawberry.field(description="The ID of the scene to place the layer in")
    table: strawberry.ID = strawberry.field(description="The ID of the table whose columns provide the track coordinates")
    track_id_column: str = strawberry.field(description="The table column that groups rows into tracks")
    x_column: str = strawberry.field(description="The table column mapped to the x coordinate")
    y_column: str = strawberry.field(description="The table column mapped to the y coordinate")
    z_column: str | None = strawberry.field(default=None, description="The table column mapped to the z coordinate (for 3D tracks)")
    t_column: str | None = strawberry.field(default=None, description="The table column mapped to the time coordinate")
    color_by_column: str | None = strawberry.field(default=None, description="The table column used to color tracks (used with colormap)")
    line_width: float | None = strawberry.field(default=None, description="The width of the track lines in scene units (default 1.0)")
    colormap: enums.ColorMap | None = strawberry.field(default=None, description="The colormap used to color tracks by their color_by_column (default 'viridis')")
    blending: enums.Blending | None = strawberry.field(default=None, description="Layer-level blend mode (default 'normal', i.e. alpha-over)")
    opacity: float | None = strawberry.field(default=None, description="Layer alpha for alpha-over compositing (default 1.0)")
    visible: bool | None = strawberry.field(default=None, description="Whether the layer participates in compositing (default true)")
    order: int | None = strawberry.field(default=None, description="Explicit z-index for back-to-front compositing (default 0)")


def create_track_layer(info: Info, input: CreateTrackLayerInput) -> types.TrackLayer:
    model = input.to_pydantic()

    scene = get_for_org(models.Scene, info, id=model.scene)
    table = get_for_org(models.Table, info, id=model.table)

    return models.Layer.objects.create(
        kind=enums.LayerKind.TRACK,
        scene=scene,
        table=table,
        track_id_column=model.track_id_column,
        x_column=model.x_column,
        y_column=model.y_column,
        z_column=model.z_column,
        t_column=model.t_column,
        color_by_column=model.color_by_column,
        line_width=model.line_width if model.line_width is not None else 1.0,
        colormap=model.colormap or enums.ColorMap.VIRIDIS,
        blending=model.blending or enums.Blending.NORMAL,
        opacity=model.opacity if model.opacity is not None else 1.0,
        visible=model.visible if model.visible is not None else True,
        order=model.order or 0,
    )
