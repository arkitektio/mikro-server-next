from kante.types import Info
import strawberry

from core import types, models, enums
import kante
from pydantic import BaseModel
from core.logic import graph as graph_logic
from core.scoping import get_for_org


def _resolve_table_dataset(info: Info, table_dataset_id: str) -> "models.TableDataset":
    """The table dataset a point/track layer draws from, checked for a place to draw it.

    The dataset is the whole mapping: its declared coordinate columns are the
    coordinates, its own coordinate system is the space, its column roles are the
    identities. Nothing is bound per layer -- a per-layer copy of any of it could
    disagree with the schema the dataset already declares.
    """
    dataset = get_for_org(models.TableDataset, info, id=table_dataset_id)
    spatial = [col for col in dataset.columns_by_role(enums.TableColumnRoleChoices.COORDINATE.value) if col.axis_type == enums.AxisTypeChoices.SPACE.value]
    if len(spatial) < 2:
        raise ValueError(f"A point/track layer needs a table dataset with at least two SPACE coordinate columns, but '{dataset.name}' has {len(spatial)}.")
    return dataset


class CreatePointLayerInputModel(BaseModel):
    scene: str
    table_dataset: str
    size_column: str | None = None
    color_column: str | None = None
    point_size: float | None = None
    colormap: enums.ColorMap | None = None
    blending: enums.Blending | None = None
    opacity: float | None = None
    visible: bool | None = None
    order: int | None = None


@kante.pydantic_input(CreatePointLayerInputModel, description="Create a layer that renders a point cloud (e.g. SMLM localisations, centroids) from a table dataset")
class CreatePointLayerInput:
    scene: strawberry.ID = strawberry.field(description="The ID of the scene to place the layer in")
    table_dataset: strawberry.ID = strawberry.field(description="The ID of the table dataset whose declared coordinate columns provide the points. Its own coordinate system is the space and its column roles are the mapping -- no per-layer column binding exists")
    size_column: str | None = strawberry.field(default=None, description="The measure column mapped to per-point size -- a per-layer display choice among the dataset's columns")
    color_column: str | None = strawberry.field(default=None, description="The measure column mapped to per-point color/intensity (used with colormap)")
    point_size: float | None = strawberry.field(default=None, description="The default point size in scene units (default 3.0). A scene unit is the world's spatial-axis unit, and is a well-defined length only where the layer's `placementInvariance` is SIMILARITY or better")
    colormap: enums.ColorMap | None = strawberry.field(default=None, description="The colormap used to color points by their color_column (default 'viridis')")
    blending: enums.Blending | None = strawberry.field(default=None, description="Layer-level blend mode (default 'normal', i.e. alpha-over)")
    opacity: float | None = strawberry.field(default=None, description="Layer alpha for alpha-over compositing (default 1.0)")
    visible: bool | None = strawberry.field(default=None, description="Whether the layer participates in compositing (default true)")
    order: int | None = strawberry.field(default=None, description="Explicit z-index for back-to-front compositing (default 0)")


def create_point_layer(info: Info, input: CreatePointLayerInput) -> types.PointLayer:
    """Create a point layer over a table dataset, refusing one the graph does not place."""
    model = input.to_pydantic()

    scene = get_for_org(models.Scene, info, id=model.scene)
    table_dataset = _resolve_table_dataset(info, model.table_dataset)

    graph_logic.assert_placeable_in(scene.world, table_dataset.coordinate_system_or_none, destination=f"the world of scene '{scene.name}'")

    return models.Layer.objects.create(
        kind=enums.LayerKind.POINT,
        scene=scene,
        table_dataset=table_dataset,
        size_column=model.size_column,
        color_column=model.color_column,
        point_size=model.point_size if model.point_size is not None else 3.0,
        colormap=model.colormap or enums.ColorMap.VIRIDIS,
        blending=model.blending or enums.Blending.NORMAL,
        opacity=model.opacity if model.opacity is not None else 1.0,
        visible=model.visible if model.visible is not None else True,
        order=model.order or 0,
    )


class CreateTrackLayerInputModel(BaseModel):
    scene: str
    table_dataset: str
    color_by_column: str | None = None
    line_width: float | None = None
    colormap: enums.ColorMap | None = None
    blending: enums.Blending | None = None
    opacity: float | None = None
    visible: bool | None = None
    order: int | None = None


@kante.pydantic_input(CreateTrackLayerInputModel, description="Create a layer that renders trajectories (e.g. particle/cell tracks) from a table dataset, grouped by its TRACK_ID column")
class CreateTrackLayerInput:
    scene: strawberry.ID = strawberry.field(description="The ID of the scene to place the layer in")
    table_dataset: strawberry.ID = strawberry.field(description="The ID of the table dataset whose declared coordinate + TRACK_ID columns provide the tracks")
    color_by_column: str | None = strawberry.field(default=None, description="The measure column used to color tracks (used with colormap) -- a per-layer display choice among the dataset's columns")
    line_width: float | None = strawberry.field(default=None, description="The width of the track lines in scene units (default 1.0). A scene unit is the world's spatial-axis unit, and is a well-defined length only where the layer's `placementInvariance` is SIMILARITY or better")
    colormap: enums.ColorMap | None = strawberry.field(default=None, description="The colormap used to color tracks by their color_by_column (default 'viridis')")
    blending: enums.Blending | None = strawberry.field(default=None, description="Layer-level blend mode (default 'normal', i.e. alpha-over)")
    opacity: float | None = strawberry.field(default=None, description="Layer alpha for alpha-over compositing (default 1.0)")
    visible: bool | None = strawberry.field(default=None, description="Whether the layer participates in compositing (default true)")
    order: int | None = strawberry.field(default=None, description="Explicit z-index for back-to-front compositing (default 0)")


def create_track_layer(info: Info, input: CreateTrackLayerInput) -> types.TrackLayer:
    """Create a track layer over a table dataset, refusing one without tracks or a place."""
    model = input.to_pydantic()

    scene = get_for_org(models.Scene, info, id=model.scene)
    table_dataset = _resolve_table_dataset(info, model.table_dataset)

    if not table_dataset.columns_by_role(enums.TableColumnRoleChoices.TRACK_ID.value):
        raise ValueError(f"Table dataset '{table_dataset.name}' has no TRACK_ID column, so it cannot be rendered as tracks.")

    graph_logic.assert_placeable_in(scene.world, table_dataset.coordinate_system_or_none, destination=f"the world of scene '{scene.name}'")

    return models.Layer.objects.create(
        kind=enums.LayerKind.TRACK,
        scene=scene,
        table_dataset=table_dataset,
        color_by_column=model.color_by_column,
        line_width=model.line_width if model.line_width is not None else 1.0,
        colormap=model.colormap or enums.ColorMap.VIRIDIS,
        blending=model.blending or enums.Blending.NORMAL,
        opacity=model.opacity if model.opacity is not None else 1.0,
        visible=model.visible if model.visible is not None else True,
        order=model.order or 0,
    )
