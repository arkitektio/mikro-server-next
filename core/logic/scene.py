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
import dataclasses
from collections.abc import Callable

from django.db import transaction

from core import enums, models
from core.creation import CreationContext
from core.inputs.coords import ScenePolicyInputModel
from core.logic import coordinate_system as coordinate_system_logic
from core.logic import coords as coords_logic
from core.logic import graph as graph_logic
from core.render.layer import label as label_models

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


def _is_renderable(dataset: "models.ArrayDataset") -> bool:
    """Whether a dataset has an x and a y axis with more than one pixel -- the minimum to draw.

    The same condition :func:`_bootstrap_image_layers` raises on, factored out so the scene
    builder can *skip* a non-renderable source (like a table with too few coordinate columns)
    instead of aborting the whole batch over one bad one. The condition itself now lives in
    :func:`core.logic.coords.is_renderable`, shared with the `placeableIn` filter's `asLayer`
    gate so a picker cannot offer what this would skip -- and it swallows the too-few-spatial-axes
    ValueError this used to let through, which is what "skip instead of abort" meant all along.
    """
    return coords_logic.is_renderable(dataset.axis_specs, dataset.axis_names, dataset.shape_list)


def _bootstrap_image_layers(
    dataset: "models.ArrayDataset",
    scene: "models.Scene",
    ctx: CreationContext,
    *,
    kind: "enums.BootstrapLayerKind | None" = None,
    order: int = 0,
) -> "list[models.Layer]":
    """Create the default array layers for a dataset in a scene: a lens, and one layer per channel.

    The array half of :func:`bootstrap_scene_from_system`. It writes no placement edge -- the
    caller must already have made the dataset placeable in the scene -- so it is pure layer
    materialization over the graph, and rejects a dataset too small to render.

    **One channel, one layer.** A multi-channel acquisition is several independent signals that
    happen to share a grid, and a viewer's unit of control -- visibility, opacity, the blend into
    the scene, deletion -- is the layer. Packing every channel into one layer's render graph made
    those per-channel choices unreachable, so the channels are peeled apart here: each gets its
    own layer over the *same* lens (``Layer.lens`` is many-to-one for exactly this), carrying a
    one-child render graph for its index, its own hue, and its own ``order`` so the stack is
    deterministic. They composite additively, which is what the single layer's in-layer blend
    did, so the picture is unchanged -- only now each channel can be touched on its own.

    RGB is the one exception, and stays one layer: there the three "channels" are the colour
    components of one photograph rather than three signals, and splitting them would offer a
    viewer three toggles that only mean something together. It is never *inferred* though --
    a flat three-channel image is fluorescence far more often than it is a photograph, and
    guessing wrong fused three signals into one layer. A caller who has a photograph says so
    with ``policy.kind = RGB``.

    ``kind`` overrides the recipe :func:`_infer_kind` would pick, and arrives from
    ``ScenePolicyInput.kind``. Worth having for LABEL alone: nothing structural distinguishes
    a label map from an image, so a mask whose derivation was never declared CATEGORIZED is
    unreachable by inference. LABEL makes a single LABEL layer carrying a label recipe -- its
    values are ids, so it has no channels to peel apart and none of the graph's vocabulary
    applies to them.

    Either way each layer must come out indistinguishable from one the matching mutation would
    have authored -- ``createLabelLayer`` here, ``createLayer`` there -- so that every later
    edit is an ordinary update.
    """
    render = coords_logic.resolve_render_axes(dataset.axis_specs)
    axis_names, shape = dataset.axis_names, dataset.shape_list

    def size(axis: str | None) -> int:
        return shape[axis_names.index(axis)] if axis is not None and axis in axis_names else 0

    if size(render.x) <= 1 or size(render.y) <= 1:
        raise ValueError(f"Dataset {dataset.pk} is not renderable: its x axis '{render.x}' ({size(render.x)} px) and y axis '{render.y}' ({size(render.y)} px) must both have more than one pixel")

    resolved_kind = kind or _infer_kind(dataset, render, size)
    # One lens for the whole dataset, whatever it becomes: a lens is a selection over an array,
    # and every channel layer selects the same thing. Minting one per channel would write a row
    # per layer saying exactly what its siblings say -- and a *sliced* one would mint a
    # coordinate system and an edge, which this module does not do.
    lens = coordinate_system_logic.create_lens(dataset, [], ctx)
    blending = _LAYER_BLENDING[resolved_kind]

    if resolved_kind == enums.BootstrapLayerKind.LABEL:
        return [
            models.Layer.objects.create(
                kind=enums.LayerKind.LABEL,
                lens=lens,
                scene=scene,
                blending=blending,
                order=order,
                label_render=label_models.LabelRenderModel(intensity_axis=render.intensity).model_dump(mode="json"),
            )
        ]

    if resolved_kind == enums.BootstrapLayerKind.RGB:
        _assert_rgb_capacity(render, size)
        return [
            models.Layer.objects.create(
                kind=enums.LayerKind.RGB,
                lens=lens,
                scene=scene,
                blending=blending,
                order=order,
                intensity_axis=render.intensity,
                red_index=0,
                green_index=1,
                blue_index=2,
            )
        ]

    projection_mode = _projection_mode(render, resolved_kind)
    return [
        models.Layer.objects.create(
            kind=enums.LayerKind.INTENSITY,
            lens=lens,
            scene=scene,
            name=channel.name,
            blending=blending,
            order=order + offset,
            intensity_axis=channel.intensity_axis,
            intensity_index=channel.intensity_index,
            colormap=channel.colormap,
            gamma=1.0,
            projection_mode=projection_mode,
        )
        for offset, channel in enumerate(_channel_sources(dataset, render, size))
    ]


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
    each source already registered one hop into it becomes one or more layers, in
    registration order, up to ``policy.nchildren`` **sources** -- the registration alone
    places it, so each source's path to world is exactly the one edge
    ``createCoordinateSystem`` authored. The cap counts sources and not layers because a
    multi-channel dataset materializes one layer per channel: truncating mid-dataset would
    hand back half an acquisition, which is worse than overshooting the cap. Over an **owned** system (a dataset's intrinsic
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
            _materialize_layers(system, scene, ctx, policy, order=0)
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
        # One counter across the whole build, never restarting per source: `order` is the
        # scene's back-to-front stack, so two datasets' channels numbered from zero apiece
        # would collide and leave the compositing order to the database.
        order = 0
        for edge in edges:
            if made >= policy.nchildren:
                break
            if edge.input is None:
                continue
            # The registration into the shared space already places: materializing a layer
            # composes over it, and skipping a source leaves the claim untouched -- it is a
            # fact about the space, not about this scene.
            layers = _materialize_layers(edge.input, scene, ctx, policy, order=order)
            if not layers:
                continue
            order += len(layers)
            made += 1

    return scene


def _materialize_layers(
    source: "models.CoordinateSystem",
    scene: "models.Scene",
    ctx: CreationContext,
    policy: "ScenePolicyInputModel",
    *,
    order: int = 0,
) -> "list[models.Layer]":
    """Turn one registered source into the layers its kind implies, or an empty list to skip it.

    A dataset's system (its intrinsic pixels or a physical space) becomes an image
    layer **per channel**, drawn by ``policy.kind`` or by inference; a table dataset a point
    or track layer (behind ``policy.transform_tables``); a mesh collection a mesh layer
    (behind ``policy.include_meshes``). A bare, ownerless system is skipped -- there is no
    data to draw. Placeability is asserted first, the same gate the layer mutations apply, so
    this can never compose a layer the graph does not already place.

    A list rather than one layer because only the array branch can produce several, and a
    caller that had to know which branch it hit to know how many layers came back would be
    the same conditional written twice. ``order`` is where this source's layers start in the
    scene's stack; the caller advances it by however many come back.
    """
    table = next(iter(source.table_datasets.all()[:1]), None)
    if table is not None:
        if not policy.transform_tables:
            return []
        layer = _materialize_table_layer(table, scene, order=order)
        return [layer] if layer is not None else []

    mesh = next(iter(source.mesh_collections.all()[:1]), None)
    if mesh is not None:
        if not policy.include_meshes:
            return []
        graph_logic.assert_placeable_in(scene.world, source, destination=f"the world of scene '{scene.name}'")
        return [
            models.Layer.objects.create(
                kind=enums.LayerKind.MESH,
                scene=scene,
                mesh_collection=mesh,
                material_color=[255, 255, 255, 255],
                wireframe=False,
                blending=enums.Blending.NORMAL,
                opacity=1.0,
                visible=True,
                order=order,
            )
        ]

    # The collections are asked *first*, and the array case last, because `dataset_behind`
    # deliberately follows an edge back: for a collection's space that edge leads to the
    # image the meshes were extracted from, and answering with it would draw the image
    # wherever a mesh was registered -- straight past `include_meshes`.
    dataset = graph_logic.dataset_behind(source)
    if dataset is not None and not source.mesh_collections.exists() and not source.table_datasets.exists() and not source.annotation_collections.exists():
        if not _is_renderable(dataset):
            # Skip, don't raise: a dataset too small to render is not layerable, exactly like
            # a table with too few coordinate columns. Letting _bootstrap_image_layers raise
            # here would abort the whole atomic build over one bad source.
            return []
        graph_logic.assert_placeable_in(scene.world, source, destination=f"the world of scene '{scene.name}'")
        # `policy.kind` reaches the render graph only here. It is deliberately not asked of
        # the mesh/table/annotation branches above: those have no recipe to choose.
        return _bootstrap_image_layers(dataset, scene, ctx, kind=policy.kind, order=order)

    annotations = next(iter(source.annotation_collections.all()[:1]), None)
    if annotations is not None:
        graph_logic.assert_placeable_in(scene.world, source, destination=f"the world of scene '{scene.name}'")
        return [
            models.Layer.objects.create(
                kind=enums.LayerKind.ANNOTATION,
                scene=scene,
                annotation_collection=annotations,
                blending=enums.Blending.NORMAL,
                opacity=1.0,
                visible=True,
                order=order,
            )
        ]

    return []


def _materialize_table_layer(table_dataset: "models.TableDataset", scene: "models.Scene", *, order: int = 0) -> "models.Layer | None":
    """A registered table dataset as a track layer when it declares tracks, else a point layer.

    Only a table with at least two SPACE coordinate columns has a place in a scene; one
    without (a per-object measurement) is skipped rather than forced into an undefined space
    -- the same minimum the point/track layer mutations require.
    """
    system = table_dataset.coordinate_system_or_none
    spatial = [col for col in table_dataset.columns_by_role(enums.ColumnRoleChoices.COORDINATE.value) if col.axis_type == enums.AxisTypeChoices.SPACE.value]
    if system is None or len(spatial) < 2:
        return None

    graph_logic.assert_placeable_in(scene.world, system, destination=f"the world of scene '{scene.name}'")

    is_track = bool(table_dataset.columns_by_role(enums.ColumnRoleChoices.TRACK_ID.value))
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
        order=order,
    )


def _infer_kind(dataset: "models.ArrayDataset", render: coords_logic.RenderAxes, size: Callable[[str | None], int]) -> "enums.BootstrapLayerKind":
    """The default recipe: a stated categorization first, then structure.

    A CATEGORIZED primary derivation says the values became labels -- the one
    structural signal that distinguishes a label map from an image, stated where the
    derivation is stated. Absent that: z with depth wins (a confocal stack is a volume),
    and everything else is intensity -- one layer per channel. LABEL is still never
    inferred from array structure alone, and an explicit ``kind`` always overrides.

    **RGB is no longer inferred.** It used to be, for flat data with exactly three
    channels, and that guess was wrong far more often than it was right: on a microscopy
    server a three-channel 2D image is a three-marker fluorescence acquisition, not a
    photograph, and the two are indistinguishable by shape. The cost of the guess was
    not a colormap -- it fused three independent signals into one layer, where none of
    them could be hidden, dimmed or reordered on its own, which is exactly what a layer
    per channel exists to allow. So RGB is now chosen, never guessed: a caller with an
    actual photograph passes ``policy.kind = RGB`` and gets the composite back.
    """
    primary = graph_logic.primary_derivation_edge(dataset)
    if primary is not None and primary.value_relation == enums.ValueRelationChoices.CATEGORIZED.value:
        return enums.BootstrapLayerKind.LABEL
    if render.z is not None and size(render.z) > 1:
        return enums.BootstrapLayerKind.VOLUME
    return enums.BootstrapLayerKind.INTENSITY


def _channel_labels(dataset: "models.ArrayDataset", axis: str) -> dict[int, str]:
    """The per-channel labels ingest recorded, keyed by channel index."""
    labels: dict[int, str] = {}
    spokes = models.ChannelLabel.objects.filter(anchor__dataset=dataset, anchor__coordinates__has_key=axis).select_related("anchor").order_by("pk")
    for spoke in spokes:
        index = spoke.anchor.coordinates.get(axis)
        if isinstance(index, int) and index not in labels and spoke.label:
            labels[index] = spoke.label
    return labels


@dataclasses.dataclass(frozen=True)
class _BootstrapChannel:
    """One channel of a dataset, and how a bootstrapped layer should draw it."""

    intensity_axis: str | None
    intensity_index: int
    colormap: "enums.ColorMap"
    #: What the layer is called. From the dataset's ChannelLabel spokes when ingest recorded
    #: them, so a materialized layer says "DAPI" where the acquisition did.
    name: str | None


def _channel_sources(dataset: "models.ArrayDataset", render: coords_logic.RenderAxes, size: Callable[[str | None], int]) -> "list[_BootstrapChannel]":
    """One channel per layer, in distinguishable hues -- grey when there is only one.

    Each of these becomes an INTENSITY layer of its own (:func:`_bootstrap_image_layers`), so
    the list is the scene's channel stack rather than one layer's children.

    The names come from the dataset's ChannelLabel spokes when ingest recorded them. Where it
    did not, the index is spelled out rather than left null: a stack of unnamed siblings is
    exactly the confusion splitting them was meant to end. A lone channel keeps its null --
    there is nothing to tell it apart from.

    The name goes on ``Layer.name``. It used to go on the render graph root node's ``label``,
    because the layer had no name column and that was the only string on the row; the flat
    kinds have no graph root, so the workaround has nowhere left to stand and the field it
    was standing in for exists.
    """
    axis = render.intensity
    channels = size(axis) if axis is not None else 0

    if channels <= 1:
        return [_BootstrapChannel(intensity_axis=axis if channels == 1 else None, intensity_index=0, colormap=enums.ColorMap.GREY, name=None)]

    labels = _channel_labels(dataset, axis)
    return [
        _BootstrapChannel(
            intensity_axis=axis,
            intensity_index=index,
            colormap=_CHANNEL_COLORMAPS[index % len(_CHANNEL_COLORMAPS)],
            name=labels.get(index, f"channel {index}"),
        )
        for index in range(channels)
    ]


def _assert_rgb_capacity(render: coords_logic.RenderAxes, size: Callable[[str | None], int]) -> None:
    """Refuse an RGB recipe over an axis with no three channels to be red, green and blue.

    The same refusal :func:`core.mutations.layer.create_rgb_layer` makes for the identical
    condition -- one rule, stated at each of the two places data enters, and it should read
    the same in both.
    """
    if render.intensity is None or size(render.intensity) < 3:
        raise ValueError(f"An RGB recipe needs a channel axis with at least three positions, but '{render.intensity}' has {size(render.intensity)}. Pass a different kind, or none for the default: one layer per channel.")


def _projection_mode(render: coords_logic.RenderAxes, kind: "enums.BootstrapLayerKind") -> "enums.ProjectionMode | None":
    """The projection a bootstrapped intensity layer carries. None -- draw the plane -- unless the recipe is VOLUME.

    VOLUME is the one :class:`~core.enums.BootstrapLayerKind` with no ``LayerKind`` of its
    own, and this is why: it names a *setting* on an intensity layer rather than a different
    sort of layer. A projection collapses z; it does not composite anything, which is the
    thing that would need a graph.
    """
    if kind != enums.BootstrapLayerKind.VOLUME:
        return None
    if render.z is None:
        raise ValueError("A VOLUME recipe projects over a z axis, and this dataset has none. Pass a different kind, or none to infer one.")
    return enums.ProjectionMode.MIP
