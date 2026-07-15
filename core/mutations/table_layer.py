from kante.types import Info
import strawberry

from core import types, models, enums
import kante
from pydantic import BaseModel
from core.logic import graph as graph_logic
from core.scoping import get_for_org


def _resolve_table_source(info: Info, model) -> tuple["models.Table | None", "models.TableDataset | None", "models.CoordinateSystem | None"]:
    """Resolve exactly one of the two table sources, and the coordinate system the layer sits in.

    A ``table_dataset`` layer draws its space and its column roles from the dataset, so
    the legacy ``coordinate_system`` and ``*_column`` inputs are forbidden: a second copy
    could disagree with the schema the dataset already declares. A legacy ``table`` layer
    binds its columns by name against a coordinate system, which is required: a table
    without one has no defined space, and a layer without a space has no place in any
    scene.
    """
    if bool(model.table) == bool(model.table_dataset):
        raise ValueError("Provide exactly one of `table` (a legacy table) or `tableDataset`.")

    if model.table_dataset:
        forbidden = [name for name in ("coordinate_system", "x_column", "y_column", "z_column", "t_column") if getattr(model, name, None)]
        if forbidden:
            raise ValueError(f"A tableDataset layer takes its space and column roles from the dataset, so it does not accept {', '.join(forbidden)}. Declare those on the table dataset's columns instead.")
        dataset = get_for_org(models.TableDataset, info, id=model.table_dataset)
        spatial = [col for col in dataset.columns_by_role(enums.TableColumnRoleChoices.COORDINATE.value) if col.axis_type == enums.AxisTypeChoices.SPACE.value]
        if len(spatial) < 2:
            raise ValueError(f"A point/track layer needs a table dataset with at least two SPACE coordinate columns, but '{dataset.name}' has {len(spatial)}.")
        return None, dataset, None

    if not model.coordinate_system:
        raise ValueError("A legacy `table` layer requires `coordinateSystem`: the columns are bare numbers until a space says what they are coordinates in.")
    table = get_for_org(models.Table, info, id=model.table)
    coordinate_system = get_for_org(models.CoordinateSystem, info, id=model.coordinate_system)
    return table, None, coordinate_system


class CreatePointLayerInputModel(BaseModel):
    scene: str
    table: str | None = None
    table_dataset: str | None = None
    coordinate_system: str | None = None
    x_column: str | None = None
    y_column: str | None = None
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


@kante.pydantic_input(CreatePointLayerInputModel, description="Create a layer that renders a point cloud (e.g. SMLM localisations, centroids) from a table dataset or a legacy table")
class CreatePointLayerInput:
    scene: strawberry.ID = strawberry.field(description="The ID of the scene to place the layer in")
    table: strawberry.ID | None = strawberry.field(default=None, description="(legacy) The ID of the legacy table whose columns provide the point coordinates. Provide this OR tableDataset, not both")
    table_dataset: strawberry.ID | None = strawberry.field(default=None, description="The ID of the table dataset whose declared coordinate columns provide the points. Its own coordinate system is the space, so no coordinate_system or column mappings are needed")
    coordinate_system: strawberry.ID | None = strawberry.field(
        default=None,
        description="(legacy table only) The coordinate system the legacy table's coordinate columns are expressed in. Required with `table` -- a table without a space has no place in any scene -- and not accepted with tableDataset",
    )
    x_column: str | None = strawberry.field(default=None, description="(legacy table only) The column mapped to the x coordinate")
    y_column: str | None = strawberry.field(default=None, description="(legacy table only) The column mapped to the y coordinate")
    z_column: str | None = strawberry.field(default=None, description="(legacy table only) The column mapped to the z coordinate (for 3D points)")
    t_column: str | None = strawberry.field(default=None, description="(legacy table only) The column mapped to the time coordinate")
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
    table, table_dataset, coordinate_system = _resolve_table_source(info, model)

    graph_logic.assert_placeable_in_scene(scene, table_dataset.coordinate_system_or_none if table_dataset is not None else coordinate_system)

    return models.Layer.objects.create(
        kind=enums.LayerKind.POINT,
        scene=scene,
        table=table,
        table_dataset=table_dataset,
        coordinate_system=coordinate_system,
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
    table: str | None = None
    table_dataset: str | None = None
    coordinate_system: str | None = None
    track_id_column: str | None = None
    x_column: str | None = None
    y_column: str | None = None
    z_column: str | None = None
    t_column: str | None = None
    color_by_column: str | None = None
    line_width: float | None = None
    colormap: enums.ColorMap | None = None
    blending: enums.Blending | None = None
    opacity: float | None = None
    visible: bool | None = None
    order: int | None = None


@kante.pydantic_input(CreateTrackLayerInputModel, description="Create a layer that renders trajectories (e.g. particle/cell tracks) from a table dataset or a legacy table, grouped by a track id")
class CreateTrackLayerInput:
    scene: strawberry.ID = strawberry.field(description="The ID of the scene to place the layer in")
    table: strawberry.ID | None = strawberry.field(default=None, description="(legacy) The ID of the legacy table whose columns provide the track coordinates. Provide this OR tableDataset, not both")
    table_dataset: strawberry.ID | None = strawberry.field(default=None, description="The ID of the table dataset whose declared coordinate + TRACK_ID columns provide the tracks")
    coordinate_system: strawberry.ID | None = strawberry.field(
        default=None,
        description="(legacy table only) The coordinate system the legacy table's coordinate columns are expressed in. Required with `table` -- a table without a space has no place in any scene -- and not accepted with tableDataset",
    )
    track_id_column: str | None = strawberry.field(default=None, description="(legacy table only) The column that groups rows into tracks")
    x_column: str | None = strawberry.field(default=None, description="(legacy table only) The column mapped to the x coordinate")
    y_column: str | None = strawberry.field(default=None, description="(legacy table only) The column mapped to the y coordinate")
    z_column: str | None = strawberry.field(default=None, description="(legacy table only) The column mapped to the z coordinate (for 3D tracks)")
    t_column: str | None = strawberry.field(default=None, description="(legacy table only) The column mapped to the time coordinate")
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
    table, table_dataset, coordinate_system = _resolve_table_source(info, model)

    if table_dataset is not None:
        if model.track_id_column:
            raise ValueError("A tableDataset track layer takes its track id from the dataset's TRACK_ID column; do not pass track_id_column.")
        if not table_dataset.columns_by_role(enums.TableColumnRoleChoices.TRACK_ID.value):
            raise ValueError(f"Table dataset '{table_dataset.name}' has no TRACK_ID column, so it cannot be rendered as tracks.")

    graph_logic.assert_placeable_in_scene(scene, table_dataset.coordinate_system_or_none if table_dataset is not None else coordinate_system)

    return models.Layer.objects.create(
        kind=enums.LayerKind.TRACK,
        scene=scene,
        table=table,
        table_dataset=table_dataset,
        coordinate_system=coordinate_system,
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
