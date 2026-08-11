"""Creating scenes and layers over spaces that already exist.

:func:`bootstrap_scene_from_system` is the way data gets staged: point it at a coordinate
system and it materializes the layers for what lives in or is registered into that space.
It composes only facts that already exist elsewhere (the space, the axis types, the anchors'
channel labels) into ordinary rows -- an ordinary scene, an ordinary lens, ordinary layers --
and **authors no edges**. Nothing here fabricates a placement.

There used to be a second entry point that took a *dataset*: it minted a world whose axes
copied the dataset's physical space and authored an identity edge into it. That world was a
copy of a space the dataset was already in, and the edge existed only to justify the copy.
Both are gone. A dataset already has coordinate systems -- its pixel grid, and any physical
space it is registered into -- and staging it means picking one of those.

There is deliberately no schema tying a scene to a dataset -- no ``Scene.dataset`` column, no
"default scene" flag -- because "which scenes show this dataset" is already answerable through
the graph, and a second stored copy of that fact would be free to disagree with it.

**This module makes compositions, not spaces.** Minting a world and creating a lens' own
coordinate system are facts about spaces, answerable with no scene in sight, and they live in
:mod:`core.logic.coordinate_system`. What is left here takes a scene or makes one.
"""

import datetime
from collections.abc import Callable

from django.db import transaction

from core import enums, models
from core.creation import CreationContext
from core.inputs.coords import ScenePolicyInputModel
from core.logic import coordinate_system as coordinate_system_logic
from core.logic import coords as coords_logic
from core.logic import graph as graph_logic
from core.render.layer import label as label_models
from core.render.layer import models as layer_models

#: Distinguishable single-hue colormaps for "one source per channel", cycled. Green and
#: magenta first: they are the standard two-channel pairing that survives red-green
#: color blindness.
_CHANNEL_COLORMAPS = [
    enums.ColorMap.GREEN,
    enums.ColorMap.MAGENTA,
    enums.ColorMap.CYAN,
    enums.ColorMap.YELLOW,
    enums.ColorMap.RED,
    enums.ColorMap.BLUE,
    enums.ColorMap.ORANGE,
    enums.ColorMap.WHITE,
]

#: How a materialized layer composites over the layers below it, per recipe. The same
#: choices the dedicated layer mutations make: fluorescence sums, an RGB photograph and
#: a label overlay sit *over* whatever is beneath them.
_LAYER_BLENDING = {
    enums.BootstrapLayerKind.RGB: enums.Blending.NORMAL,
    enums.BootstrapLayerKind.INTENSITY: enums.Blending.ADDITIVE,
    enums.BootstrapLayerKind.VOLUME: enums.Blending.ADDITIVE,
    enums.BootstrapLayerKind.LABEL: enums.Blending.NORMAL,
}


def _viewer_preferences(preferred_view: "enums.PreferredView | None", background_color: list[float] | None) -> dict:
    """The viewer preferences to stamp on a new scene, omitting the ones nobody stated.

    Omitted rather than defaulted here: the columns already carry their defaults, and
    passing an explicit None for `preferred_view` would write null over AUTO.
    """
    preferences: dict = {}
    if preferred_view is not None:
        preferences["preferred_view"] = preferred_view.value
    if background_color is not None:
        preferences["background_color"] = background_color
    return preferences


def create_scene(
    *,
    name: str,
    ctx: CreationContext,
    axes: list | None = None,
    blending: "enums.Blending | None" = None,
    preferred_view: "enums.PreferredView | None" = None,
    background_color: list[float] | None = None,
    epoch: datetime.datetime | None = None,
    world: "models.CoordinateSystem | None" = None,
) -> "models.Scene":
    """Create a scene over a world: an adopted existing system, or one created for convenience.

    Adopting composes over the space as it is -- many scenes can share it, and its axes and
    epoch are already its own. **Every space is adoptable** (RFC-9): under residence a
    pyramid level's grid is a space like any other, related to everything else by edges, so
    the old refusal of an ARRAY system had nothing left to stand on. Composing in one is
    unusual rather than wrong.

    Without ``world``, an ordinary ownerless SHARED space is created first and
    adopted -- pure convenience, nothing scene-owned: the space can be adopted by
    other scenes, outlives every scene over it, and is deleted only explicitly
    (``deleteCoordinateSystem``), never by a scene going away.
    """
    if world is not None:
        if axes is not None or epoch is not None:
            raise ValueError("A scene adopting an existing coordinate system takes its axes and epoch from it; do not pass `axes` or `epoch` alongside `coordinateSystem`.")
        if not world.axes.filter(type__in=coordinate_system_logic.NAVIGABLE_TYPES).exists():
            raise ValueError(f"World '{world.name}' has no navigable (time/space) axes, so nothing could be placed in a scene over it.")
        return models.Scene.objects.create(
            name=name,
            world=world,
            organization=ctx.organization,
            blending=blending or enums.Blending.ADDITIVE,
            **_viewer_preferences(preferred_view, background_color),
        )

    # Minting the space is not this module's work -- it makes scenes and layers -- so the
    # convenience path calls the space module and then adopts what it gets back, which is
    # exactly the shape of the two-call version a client can write itself.
    with transaction.atomic():
        world = coordinate_system_logic.create_world_space(name=f"{name}/world", axes=axes, epoch=epoch, ctx=ctx)
        scene = models.Scene.objects.create(
            name=name,
            world=world,
            organization=ctx.organization,
            blending=blending or enums.Blending.ADDITIVE,
            **_viewer_preferences(preferred_view, background_color),
        )
    return scene


def _is_renderable(dataset: "models.ADataset") -> bool:
    """Whether a dataset has an x and a y axis with more than one pixel -- the minimum to draw.

    The same condition :func:`_bootstrap_image_layer` raises on, factored out so the scene
    builder can *skip* a non-renderable source (like a table with too few coordinate columns)
    instead of aborting the whole batch over one bad one. The condition itself now lives in
    :func:`core.logic.coords.is_renderable`, shared with the `placeableIn` filter's `asLayer`
    gate so a picker cannot offer what this would skip -- and it swallows the too-few-spatial-axes
    ValueError this used to let through, which is what "skip instead of abort" meant all along.
    """
    return coords_logic.is_renderable(dataset.axis_specs, dataset.axis_names, dataset.shape_list)


def _bootstrap_image_layer(
    dataset: "models.ADataset",
    scene: "models.Scene",
    ctx: CreationContext,
    *,
    kind: "enums.BootstrapLayerKind | None" = None,
) -> "models.Layer":
    """Create the default array layer for a dataset in a scene: a full lens and its render recipe.

    The array half of :func:`bootstrap_scene_from_system`. It writes no placement edge -- the
    caller must already have made the dataset placeable in the scene -- so it is pure layer
    materialization over the graph, and rejects a dataset too small to render.

    ``kind`` overrides the recipe :func:`_infer_kind` would pick, and arrives from
    ``ScenePolicyInput.kind``. Worth having for LABEL alone: nothing structural distinguishes
    a label map from an image, so a mask whose derivation was never declared CATEGORIZED is
    unreachable by inference.

    Three of the four recipes make an IMAGE layer carrying a render graph; LABEL makes a
    LABEL layer carrying a label recipe, because its values are ids and none of the graph's
    vocabulary applies to them. Either way the layer must come out indistinguishable from
    one the matching mutation would have authored -- ``createLabelLayer`` here, ``createLayer``
    there -- so that every later edit is an ordinary update.
    """
    render = coords_logic.resolve_render_axes(dataset.axis_specs)
    axis_names, shape = dataset.axis_names, dataset.shape_list

    def size(axis: str | None) -> int:
        return shape[axis_names.index(axis)] if axis is not None and axis in axis_names else 0

    if size(render.x) <= 1 or size(render.y) <= 1:
        raise ValueError(f"Dataset {dataset.pk} is not renderable: its x axis '{render.x}' ({size(render.x)} px) and y axis '{render.y}' ({size(render.y)} px) must both have more than one pixel")

    resolved_kind = kind or _infer_kind(dataset, render, size)
    lens = coordinate_system_logic.create_lens(dataset, [], ctx)

    if resolved_kind == enums.BootstrapLayerKind.LABEL:
        return models.Layer.objects.create(
            kind=enums.LayerKind.LABEL,
            lens=lens,
            scene=scene,
            blending=_LAYER_BLENDING[resolved_kind],
            label_render=label_models.LabelRenderModel(intensity_axis=render.intensity).model_dump(mode="json"),
        )

    return models.Layer.objects.create(
        kind=enums.LayerKind.IMAGE,
        lens=lens,
        scene=scene,
        blending=_LAYER_BLENDING[resolved_kind],
        render_graph=layer_models.LayerRenderGraphModel(root=_render_root(dataset, render, size, resolved_kind)).model_dump(mode="json"),
    )


def bootstrap_scene_from_system(
    system: "models.CoordinateSystem",
    policy: "ScenePolicyInputModel",
    ctx: CreationContext,
    *,
    name: str | None = None,
) -> "models.Scene":
    """Materialize a renderable scene over an existing coordinate system and what lives in it.

    The scene *adopts* the system as its world -- no fresh world is created and no edge
    is authored, because a node for the same space joined by an identity edge would store
    nothing. What becomes a layer depends on what the space is. Over a **shared space**,
    each source already registered one hop into it becomes a layer, in registration
    order, up to ``policy.nchildren`` -- the registration alone places it, so each source's
    path to world is exactly the one edge
    ``createCoordinateSystem`` authored. Over an **owned** system (a dataset's intrinsic
    pixels, a physical space, a collection's space), the container's own data becomes the
    layer: it fact-reaches its own space by construction, no registration exists or is
    needed, and nothing foreign can be claimed into an owned space. Rerunning shares the
    space -- two scenes, one space -- and the space outlives every scene over it
    (Scene.world is RESTRICT).
    """
    # There is no adoptability rule left to assert -- RFC-9 made every space adoptable, and
    # the ARRAY refusal went with it. `create_scene`'s adopt path checks one thing: that the
    # space has navigable axes, without which nothing could be placed in a scene over it.
    with transaction.atomic():
        scene = create_scene(name=name or system.name, world=system, ctx=ctx)

        if graph_logic.residents_exist(system):
            # Data lives right here, so it is the layer: it is in its own space by
            # definition, and there is no registration to iterate for it.
            _materialize_layer(system, scene, ctx, policy)
            return scene

        # The candidate set: the sources registered one hop into the shared space, in the
        # order the registrations were authored (pk). Bounded and predictable against
        # nchildren -- a multi-hop reachable closure would be a larger, less obvious set.
        edges = (
            models.Transformation.objects.filter(output=system, parent__isnull=True)
            .select_related("input").prefetch_related("input__datasets", "input__table_datasets", "input__mesh_collections", "input__annotation_collections")
            .order_by("pk")
        )

        made = 0
        for edge in edges:
            if made >= policy.nchildren:
                break
            if edge.input is None:
                continue
            # The registration into the shared space already places: materializing a layer
            # composes over it, and skipping a source leaves the claim untouched -- it is a
            # fact about the space, not about this scene.
            layer = _materialize_layer(edge.input, scene, ctx, policy)
            if layer is None:
                continue
            made += 1

    return scene


def _materialize_layer(
    source: "models.CoordinateSystem",
    scene: "models.Scene",
    ctx: CreationContext,
    policy: "ScenePolicyInputModel",
) -> "models.Layer | None":
    """Turn one registered source into the layer its kind implies, or None to skip it.

    A dataset's system (its intrinsic pixels or a physical space) becomes an image
    layer, drawn by ``policy.kind`` or by inference; a table dataset a point or track layer
    (behind ``policy.transform_tables``); a mesh collection a mesh layer (behind
    ``policy.include_meshes``). A bare, ownerless system is skipped -- there is no data to
    draw. Placeability is asserted first, the same gate the layer mutations apply, so this can
    never compose a layer the graph does not already place.
    """
    table = next(iter(source.table_datasets.all()[:1]), None)
    if table is not None:
        if not policy.transform_tables:
            return None
        return _materialize_table_layer(table, scene)

    mesh = next(iter(source.mesh_collections.all()[:1]), None)
    if mesh is not None:
        if not policy.include_meshes:
            return None
        graph_logic.assert_placeable_in(scene.world, source, destination=f"the world of scene '{scene.name}'")
        return models.Layer.objects.create(
            kind=enums.LayerKind.MESH,
            scene=scene,
            mesh_collection=mesh,
            material_color=[255, 255, 255, 255],
            wireframe=False,
            blending=enums.Blending.NORMAL,
            opacity=1.0,
            visible=True,
            order=0,
        )

    # The collections are asked *first*, and the array case last, because `dataset_behind`
    # deliberately follows an edge back: for a collection's space that edge leads to the
    # image the meshes were extracted from, and answering with it would draw the image
    # wherever a mesh was registered -- straight past `include_meshes`.
    dataset = graph_logic.dataset_behind(source)
    if dataset is not None and not source.mesh_collections.exists() and not source.table_datasets.exists() and not source.annotation_collections.exists():
        if not _is_renderable(dataset):
            # Skip, don't raise: a dataset too small to render is not layerable, exactly like
            # a table with too few coordinate columns. Letting _bootstrap_image_layer raise
            # here would abort the whole atomic build over one bad source.
            return None
        graph_logic.assert_placeable_in(scene.world, source, destination=f"the world of scene '{scene.name}'")
        # `policy.kind` reaches the render graph only here. It is deliberately not asked of
        # the mesh/table/annotation branches above: those have no recipe to choose.
        return _bootstrap_image_layer(dataset, scene, ctx, kind=policy.kind)

    annotations = next(iter(source.annotation_collections.all()[:1]), None)
    if annotations is not None:
        graph_logic.assert_placeable_in(scene.world, source, destination=f"the world of scene '{scene.name}'")
        return models.Layer.objects.create(
            kind=enums.LayerKind.ANNOTATION,
            scene=scene,
            annotation_collection=annotations,
            blending=enums.Blending.NORMAL,
            opacity=1.0,
            visible=True,
            order=0,
        )

    return None


def _materialize_table_layer(table_dataset: "models.TableDataset", scene: "models.Scene") -> "models.Layer | None":
    """A registered table dataset as a track layer when it declares tracks, else a point layer.

    Only a table with at least two SPACE coordinate columns has a place in a scene; one
    without (a per-object measurement) is skipped rather than forced into an undefined space
    -- the same minimum the point/track layer mutations require.
    """
    system = table_dataset.coordinate_system_or_none
    spatial = [col for col in table_dataset.columns_by_role(enums.TableColumnRoleChoices.COORDINATE.value) if col.axis_type == enums.AxisTypeChoices.SPACE.value]
    if system is None or len(spatial) < 2:
        return None

    graph_logic.assert_placeable_in(scene.world, system, destination=f"the world of scene '{scene.name}'")

    is_track = bool(table_dataset.columns_by_role(enums.TableColumnRoleChoices.TRACK_ID.value))
    return models.Layer.objects.create(
        kind=enums.LayerKind.TRACK if is_track else enums.LayerKind.POINT,
        scene=scene,
        table_dataset=table_dataset,
        point_size=None if is_track else 3.0,
        line_width=1.0 if is_track else None,
        colormap=enums.ColorMap.VIRIDIS,
        blending=enums.Blending.NORMAL,
        opacity=1.0,
        visible=True,
        order=0,
    )


def _infer_kind(dataset: "models.ADataset", render: coords_logic.RenderAxes, size: Callable[[str | None], int]) -> "enums.BootstrapLayerKind":
    """The default recipe: a stated categorization first, then structure.

    A CATEGORIZED primary derivation says the values became labels -- the one
    structural signal that distinguishes a label map from an image, stated where the
    derivation is stated. Absent that: z with depth wins over everything (a 3-channel
    confocal stack is a volume, not a photograph); exactly three channels on flat data
    reads as RGB; everything else is intensity. LABEL is still never inferred from
    array structure alone, and an explicit ``kind`` always overrides.
    """
    primary = graph_logic.primary_derivation_edge(dataset)
    if primary is not None and primary.value_relation == enums.ValueRelationChoices.CATEGORIZED.value:
        return enums.BootstrapLayerKind.LABEL
    if render.z is not None and size(render.z) > 1:
        return enums.BootstrapLayerKind.VOLUME
    if render.intensity is not None and size(render.intensity) == 3:
        return enums.BootstrapLayerKind.RGB
    return enums.BootstrapLayerKind.INTENSITY


def _channel_labels(dataset: "models.ADataset", axis: str) -> dict[int, str]:
    """The per-channel labels ingest recorded, keyed by channel index."""
    labels: dict[int, str] = {}
    spokes = models.ChannelLabel.objects.filter(anchor__dataset=dataset, anchor__coordinates__has_key=axis).select_related("anchor").order_by("pk")
    for spoke in spokes:
        index = spoke.anchor.coordinates.get(axis)
        if isinstance(index, int) and index not in labels and spoke.label:
            labels[index] = spoke.label
    return labels


def _channel_sources(dataset: "models.ADataset", render: coords_logic.RenderAxes, size: Callable[[str | None], int]) -> list:
    """One source node per channel, in distinguishable hues -- grey when there is only one.

    The labels come from the dataset's ChannelLabel spokes when ingest recorded them, so
    a materialized layer says "DAPI" where the acquisition did, not "channel 0".
    """
    axis = render.intensity
    channels = size(axis) if axis is not None else 0

    if channels <= 1:
        transfer = layer_models.TransferFunctionModel(colormap=enums.ColorMap.GREY)
        return [layer_models.ChannelSourceModel(intensity_axis=axis if channels == 1 else None, intensity_index=0, label=None, transfer=transfer)]

    labels = _channel_labels(dataset, axis)
    return [
        layer_models.ChannelSourceModel(
            intensity_axis=axis,
            intensity_index=index,
            label=labels.get(index),
            transfer=layer_models.TransferFunctionModel(colormap=_CHANNEL_COLORMAPS[index % len(_CHANNEL_COLORMAPS)]),
        )
        for index in range(channels)
    ]


def _render_root(dataset: "models.ADataset", render: coords_logic.RenderAxes, size: Callable[[str | None], int], kind: "enums.BootstrapLayerKind") -> layer_models.BlendNodeModel:
    """The render graph a bootstrapped IMAGE layer carries, per recipe.

    The same shapes the dedicated layer mutations build, so a bootstrapped layer is
    indistinguishable from one a client authored -- and every later edit is an ordinary
    ``updateLayer``. LABEL never reaches here: it is a different layer kind with a
    different recipe, handled in :func:`_bootstrap_image_layer`.
    """
    if kind == enums.BootstrapLayerKind.RGB:
        if render.intensity is None or size(render.intensity) < 3:
            raise ValueError(f"An RGB recipe needs a channel axis with at least three positions, but '{render.intensity}' has {size(render.intensity)}. Pass a different kind, or none to infer one.")
        children = [
            layer_models.ChannelSourceModel(intensity_axis=render.intensity, intensity_index=index, label=label, transfer=layer_models.TransferFunctionModel(colormap=colormap))
            for index, (label, colormap) in enumerate([("red", enums.ColorMap.RED), ("green", enums.ColorMap.GREEN), ("blue", enums.ColorMap.BLUE)])
        ]
        return layer_models.BlendNodeModel(blending=enums.Blending.ADDITIVE, children=children, label="rgb")

    if kind == enums.BootstrapLayerKind.VOLUME:
        if render.z is None:
            raise ValueError("A VOLUME recipe projects over a z axis, and this dataset has none. Pass a different kind, or none to infer one.")
        projection = layer_models.ProjectionNodeModel(mode=enums.ProjectionMode.MIP, children=_channel_sources(dataset, render, size), label="projection")
        return layer_models.BlendNodeModel(blending=enums.Blending.ADDITIVE, children=[projection], label="volume")

    # No LABEL branch: a label map is its own layer kind and carries no render graph at
    # all. `_bootstrap_image_layer` returns before it gets here.
    return layer_models.BlendNodeModel(blending=enums.Blending.ADDITIVE, children=_channel_sources(dataset, render, size), label="intensity")
