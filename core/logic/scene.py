"""Creating scenes, lenses, and the bootstrap that makes a fresh dataset render.

The single copies of "make a scene and its world system" and "make a lens and its
edge home" live here, called by the mutations and by :func:`bootstrap_scene` --
which is the ingest hotpath: one call that takes a dataset to something a client
can actually draw. It composes only facts that already exist elsewhere (the
calibration, the axis types, the anchors' channel labels) into ordinary rows: an
ordinary scene, an ordinary lens, an ordinary image layer. There is deliberately
no schema for it -- no ``Scene.dataset`` column, no "default scene" flag -- because
"which scenes show this dataset" is already answerable through the graph, and a
second stored copy of that fact would be free to disagree with it.
"""

import datetime
from collections.abc import Callable

from django.db import transaction

from core import enums, models
from core.creation import CreationContext
from core.inputs.coords import CalibratedAxisInputModel, ScenePolicyInputModel
from core.logic import coords as coords_logic
from core.logic import graph as graph_logic
from core.render.layer import models as layer_models

# The scene's world space, when the caller does not author one. A scene is
# spatio-temporal by default: microscopy data is a timelapse more often than not, and
# a world with nowhere to put time forces every temporal dataset to either drop its t
# axis at the registration or invent a scene-specific convention for it.
#
# Time first, then z/y/x in array order: the RFC-5 type ordering
# (:func:`assert_axis_type_order`) requires it, and array order means the world
# composes with a dataset's intrinsic axes without a permutation.
#
# Seconds, not a frame index: world is a *calibrated* space, and `t` here is a
# duration from the space's origin. The world system's `epoch` anchors that origin to
# wall-clock when it is known.
DEFAULT_WORLD_AXES = [
    CalibratedAxisInputModel(name="t", type=enums.AxisType.TIME, unit="second"),
    CalibratedAxisInputModel(name="z", type=enums.AxisType.SPACE, unit="micrometer"),
    CalibratedAxisInputModel(name="y", type=enums.AxisType.SPACE, unit="micrometer"),
    CalibratedAxisInputModel(name="x", type=enums.AxisType.SPACE, unit="micrometer"),
]

#: The axis types a world has a slider for. A CHANNEL axis is something a layer
#: *samples* (each position its own render node), and a MICROTIME or SPECTRUM axis is
#: something a render node *reduces* -- neither is a place, so neither belongs to a
#: shared space two datasets are registered into.
_NAVIGABLE_TYPES = (enums.AxisTypeChoices.TIME.value, enums.AxisTypeChoices.SPACE.value)

#: The unit a bootstrapped world assumes for an uncalibrated axis. The same claim the
#: assumed identity registration has always made -- one pixel, one micrometre -- now
#: stated where it is visible instead of implied by a default world.
_DEFAULT_UNIT_BY_TYPE = {
    enums.AxisTypeChoices.TIME.value: "second",
    enums.AxisTypeChoices.SPACE.value: "micrometer",
}

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

#: How the bootstrapped layer composites over the layers below it, per recipe. The same
#: choices the dedicated layer mutations make: fluorescence sums, an RGB photograph and
#: a label overlay sit *over* whatever is beneath them.
_LAYER_BLENDING = {
    enums.BootstrapLayerKind.RGB: enums.Blending.NORMAL,
    enums.BootstrapLayerKind.INTENSITY: enums.Blending.ADDITIVE,
    enums.BootstrapLayerKind.VOLUME: enums.Blending.ADDITIVE,
    enums.BootstrapLayerKind.LABEL: enums.Blending.NORMAL,
}


def create_scene(
    *,
    name: str,
    ctx: CreationContext,
    axes: list | None = None,
    blending: "enums.Blending | None" = None,
    epoch: datetime.datetime | None = None,
    world: "models.CoordinateSystem | None" = None,
) -> "models.Scene":
    """Create a scene over a world: an adopted existing hub, or one minted for it.

    Adopting composes over the space as it is -- many scenes can share it, and it
    outlives each of them. Only an ownerless hub qualifies: an owned system (another
    scene's minted world included) cascades with its container, and a scene must
    never have its world deleted out from under it.
    """
    if world is not None:
        if axes is not None or epoch is not None:
            raise ValueError("A scene adopting an existing coordinate system takes its axes and epoch from it; do not pass `axes` or `epoch` alongside `coordinateSystem`.")
        if not world.is_hub:
            raise ValueError(f"Coordinate system {world.pk} ({world.kind.value}) is owned by a container, not an ownerless hub. Only a hub can be adopted as a scene's world.")
        if not world.axes.filter(type__in=_NAVIGABLE_TYPES).exists():
            raise ValueError(f"Hub '{world.name}' has no navigable (time/space) axes, so nothing could be placed in a scene over it.")
        return models.Scene.objects.create(
            name=name,
            world=world,
            organization=ctx.organization,
            blending=blending or enums.Blending.ADDITIVE,
        )

    axes = axes or DEFAULT_WORLD_AXES
    axis_specs = [coords_logic.AxisSpec(name=axis.name, type=axis.type.value) for axis in axes]
    coords_logic.assert_axis_type_order(axis_specs)

    # World first, claimed after: Scene.world is non-null, and the ownership FK
    # (CoordinateSystem.scene) needs the scene's pk. The transaction hides the moment
    # the fresh world is ownerless. The epoch lands on the world system, not the
    # scene: it is the origin of the *space's* time axis, and two compositions over
    # one space cannot disagree about it.
    with transaction.atomic():
        minted = models.CoordinateSystem.objects.create(
            name=f"{name}/world",
            epoch=epoch,
            creator=ctx.user,
            organization=ctx.organization,
        )
        graph_logic.create_calibrated_axes(minted, axes)
        scene = models.Scene.objects.create(
            name=name,
            world=minted,
            organization=ctx.organization,
            blending=blending or enums.Blending.ADDITIVE,
        )
        minted.scene = scene
        minted.save(update_fields=["scene"])
    return scene


def create_lens(
    dataset: "models.ADataset",
    slices: list,
    ctx: CreationContext,
) -> "models.Lens":
    """Create a lens -- and, only if it slices, its coordinate system and the edge recording the shift.

    The lens' shape and axes are not written: they follow from the dataset and the
    slices, and a second copy could only drift from the first. The same rule decides
    whether it gets a coordinate system at all: an unsliced lens selects everything,
    so its space is the dataset's intrinsic space *by definition* -- materializing a
    second node for it, joined by an identity edge, would store nothing. Lenses are
    immutable, so the decision is final at creation.
    """
    intrinsic = dataset.intrinsic_coordinate_system
    if intrinsic is None:
        raise ValueError(f"Dataset {dataset.pk} has no intrinsic coordinate system")

    if dataset.data_arrays.order_by("level").first() is None:
        raise ValueError(f"Dataset {dataset.pk} has no level-0 data array to place the lens against")

    lens = models.Lens.objects.create(
        dataset=dataset,
        slices=[slice.model_dump() for slice in slices],
    )

    if not lens.slices_list:
        return lens

    lens_system = models.CoordinateSystem.objects.create(
        name=f"{dataset.name}/lens/{lens.pk}",
        lens=lens,
        creator=ctx.user,
        organization=ctx.organization,
    )
    # A lens sees the same axes as the array it slices; only the extent changes.
    graph_logic.create_pixel_axes(lens_system, dataset.axes)

    # Without this edge, slicing shifts voxel coordinates and nothing records the
    # shift: an ROI drawn on a cropped lens has no defined path back to its dataset.
    # The parent is the intrinsic system: it IS the level-0 voxel space.
    graph_logic.create_lens_edge(
        lens_system=lens_system,
        parent_system=intrinsic,
        dataset_axis_names=dataset.axis_names,
        slices=lens.slices_list,
        ctx=ctx,
    )

    return lens


def bootstrap_scene(
    dataset: "models.ADataset",
    ctx: CreationContext,
    *,
    name: str | None = None,
    kind: "enums.BootstrapLayerKind | None" = None,
) -> "models.Scene":
    """Bootstrap a renderable scene for a dataset: world, placement, lens, layer -- one call.

    The world's axes mirror the dataset's calibration when it has one, so the mirror edge
    from the PHYSICAL system is an identity and the data renders at physical scale for
    free; without a calibration they mirror the dataset's own time/space axes under
    default units, which is the very claim the identity registration then makes.

    Exactly one registration is authored, always, for the staged dataset itself -- the
    only edge-writing sugar left anywhere: layer mutations fabricate nothing and reject
    an unplaced source instead. It is honest here because the world was *built* to be
    this dataset's own space, derived or not -- an UNMAPPABLE derivation denies
    correspondence with the parent's space, not with a world minted to mirror its own
    axes. The one thing to know: this mirror edge is one hop from world, so registering
    the dataset's lineage into this same scene later will be outranked by it in the
    shortest-path search. A shared scene composed from lineage registrations should be
    created bare and registered explicitly, not bootstrapped.

    Everything created is ordinary: delete the scene and the dataset, its calibration and
    its lens edge are untouched; run it twice and there are simply two scenes.
    """
    with transaction.atomic():
        world_axes, calibration = _world_axes_for(dataset)
        scene = create_scene(name=name or dataset.name, axes=world_axes, ctx=ctx)

        # The one edge that makes the render reach world: anchor -> world, identity on
        # the (shared, navigable) axis names. From the calibration when there is one --
        # the world mirrors its units, so the identity is exact by construction
        # (VALIDATED) -- else from the intrinsic pixels under default units, which is an
        # assumed interpretation and wears UNKNOWN as its badge.
        anchor = calibration or dataset.intrinsic_coordinate_system
        if anchor is None:
            raise ValueError(f"Dataset {dataset.pk} has no coordinate system to register into the scene.")
        edge = graph_logic.create_identity_registration(
            input_system=anchor,
            world=scene.world,
            shared=[axis.name for axis in world_axes],
            name=(f"{dataset.name} -> {scene.name} (mirror)" if calibration is not None else f"{dataset.name} -> {scene.name} (assumed)"),
            validity=(enums.PlacementValidityChoices.VALIDATED.value if calibration is not None else enums.PlacementValidityChoices.UNKNOWN.value),
            ctx=ctx,
        )
        scene.coordinate_transformations.add(edge)

        _bootstrap_image_layer(dataset, scene, ctx, kind=kind)

    return scene


def _is_renderable(dataset: "models.ADataset") -> bool:
    """Whether a dataset has an x and a y axis with more than one pixel -- the minimum to draw.

    The same condition :func:`_bootstrap_image_layer` raises on, factored out so the scene
    builder can *skip* a non-renderable source (like a table with too few coordinate columns)
    instead of aborting the whole batch, while the single-dataset bootstrap still refuses one.
    """
    render = coords_logic.resolve_render_axes(dataset.axis_specs)
    axis_names, shape = dataset.axis_names, dataset.shape_list

    def size(axis: str | None) -> int:
        return shape[axis_names.index(axis)] if axis is not None and axis in axis_names else 0

    return size(render.x) > 1 and size(render.y) > 1


def _bootstrap_image_layer(
    dataset: "models.ADataset",
    scene: "models.Scene",
    ctx: CreationContext,
    *,
    kind: "enums.BootstrapLayerKind | None" = None,
) -> "models.Layer":
    """Create the default IMAGE layer for a dataset in a scene: a full lens and its render graph.

    The image half of the bootstrap, shared by :func:`bootstrap_scene` (one dataset) and
    :func:`bootstrap_scene_from_system` (many). It writes no placement edge -- the caller
    must already have made the dataset placeable in the scene -- so it is pure layer
    materialization over the graph, and rejects a dataset too small to render.
    """
    render = coords_logic.resolve_render_axes(dataset.axis_specs)
    axis_names, shape = dataset.axis_names, dataset.shape_list

    def size(axis: str | None) -> int:
        return shape[axis_names.index(axis)] if axis is not None and axis in axis_names else 0

    if size(render.x) <= 1 or size(render.y) <= 1:
        raise ValueError(f"Dataset {dataset.pk} is not renderable: its x axis '{render.x}' ({size(render.x)} px) and y axis '{render.y}' ({size(render.y)} px) must both have more than one pixel")

    resolved_kind = kind or _infer_kind(render, size)
    root = _render_root(dataset, render, size, resolved_kind)

    lens = create_lens(dataset, [], ctx)

    return models.Layer.objects.create(
        kind=enums.LayerKind.IMAGE,
        lens=lens,
        scene=scene,
        blending=_LAYER_BLENDING[resolved_kind],
        render_graph=layer_models.LayerRenderGraphModel(root=root).model_dump(mode="json"),
    )


def bootstrap_scene_from_system(
    system: "models.CoordinateSystem",
    policy: "ScenePolicyInputModel",
    ctx: CreationContext,
    *,
    name: str | None = None,
) -> "models.Scene":
    """Materialize a renderable scene over a hub coordinate system and the sources registered into it.

    The scene *adopts* the hub as its world -- no fresh world is minted and no edge is
    authored, because a node for the same space joined by an identity edge would store
    nothing. Each source already registered one hop into the hub becomes a layer, in
    registration order, up to ``policy.nchildren``, and its registration edge joins the
    scene's composition: that membership is what places it, so each source's path to
    world is exactly the one edge ``createCoordinateSystem`` authored. Rerunning shares
    the hub -- two scenes, one space -- and the hub outlives every scene over it.
    """
    # An ownership assertion, not a label check: an owned system -- another scene's
    # minted world included -- cascades with its container and was never built to be
    # a hub. The navigable-axes check lives in create_scene's adopt path.
    if not system.is_hub:
        raise ValueError(f"Coordinate system {system.pk} ({system.kind.value}) is owned by a container, not an ownerless hub. Only a hub built to be registered into can seed a scene this way.")

    with transaction.atomic():
        scene = create_scene(name=name or system.name, world=system, ctx=ctx)

        # The candidate set: the sources registered one hop into the hub, in the order the
        # registrations were authored (pk). Bounded and predictable against nchildren -- a
        # multi-hop reachable closure would be a larger, less obvious set.
        edges = (
            models.Transformation.objects.filter(output=system, parent__isnull=True)
            .select_related("input", "input__intrinsic_of", "input__dataset", "input__table_dataset", "input__mesh_collection")
            .order_by("pk")
        )

        made = 0
        for edge in edges:
            if made >= policy.nchildren:
                break
            if edge.input is None:
                continue
            # Membership first: an edge into a shared space places only by the scene's
            # say-so, and _materialize_layer asserts placeability before creating anything.
            scene.coordinate_transformations.add(edge)
            layer = _materialize_layer(edge.input, scene, ctx, policy)
            if layer is None:
                # A skipped source claims nothing: leaving its registration a member
                # would compose an edge into the scene for a layer that does not exist.
                scene.coordinate_transformations.remove(edge)
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

    A dataset's system (its intrinsic pixels or a PHYSICAL calibration) becomes an image
    layer; a table dataset a point or track layer (behind ``policy.transform_tables``); a
    mesh collection a mesh layer (behind ``policy.include_meshes``). A bare, ownerless system
    is skipped -- there is no data to draw. Placeability is asserted first, the same gate the
    layer mutations apply, so this can never compose a layer the graph does not already place.
    """
    if source.intrinsic_of_id or source.dataset_id:
        dataset = graph_logic.system_dataset(source)
        if dataset is None or not _is_renderable(dataset):
            # Skip, don't raise: a dataset too small to render is not layerable, exactly like
            # a table with too few coordinate columns. Letting _bootstrap_image_layer raise
            # here would abort the whole atomic build over one bad source.
            return None
        graph_logic.assert_placeable_in_scene(scene, source)
        return _bootstrap_image_layer(dataset, scene, ctx)

    if source.table_dataset_id:
        if not policy.transform_tables:
            return None
        return _materialize_table_layer(source.table_dataset, scene)

    if source.mesh_collection_id:
        if not policy.include_meshes:
            return None
        graph_logic.assert_placeable_in_scene(scene, source)
        return models.Layer.objects.create(
            kind=enums.LayerKind.MESH,
            scene=scene,
            mesh_collection=source.mesh_collection,
            material_color=[255, 255, 255, 255],
            wireframe=False,
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

    graph_logic.assert_placeable_in_scene(scene, system)

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


def _world_axes_for(dataset: "models.ADataset") -> tuple[list[CalibratedAxisInputModel], "models.CoordinateSystem | None"]:
    """The axes a bootstrapped world gets, and the calibration they mirror (if any).

    Mirroring -- same names, same types, same units -- is what makes the anchor edge an
    identity: the world *is* the calibration's navigable subspace, extended to nothing it
    does not need. Only TIME and SPACE axes cross over; a channel is sampled per layer and
    a phasor axis is reduced per render node, so neither is a coordinate of a shared space.
    """
    calibration = dataset.calibrations.order_by("pk").first()
    source_axes = list(calibration.axes.all()) if calibration is not None else dataset.axes

    world_axes = [
        CalibratedAxisInputModel(
            name=axis.name,
            type=enums.AxisType(axis.type),
            unit=axis.unit or _DEFAULT_UNIT_BY_TYPE.get(axis.type, "a.u."),
            long_name=axis.long_name,
            description=axis.description,
        )
        for axis in source_axes
        if axis.type in _NAVIGABLE_TYPES
    ]
    return world_axes, calibration


def _infer_kind(render: coords_logic.RenderAxes, size: Callable[[str | None], int]) -> "enums.BootstrapLayerKind":
    """The default recipe, from structure alone.

    z with depth wins over everything (a 3-channel confocal stack is a volume, not a
    photograph); exactly three channels on flat data reads as RGB; everything else is
    intensity. LABEL is never inferred: nothing structural distinguishes a label map
    from an image, so it stays an explicit override.
    """
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
    the bootstrapped layer says "DAPI" where the acquisition did, not "channel 0".
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
    """The render graph a bootstrapped layer carries, per recipe.

    The same shapes the dedicated layer mutations build, so a bootstrapped layer is
    indistinguishable from one a client authored -- and every later edit is an ordinary
    ``updateLayer``.
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

    if kind == enums.BootstrapLayerKind.LABEL:
        child = layer_models.ChannelSourceModel(
            intensity_axis=render.intensity,
            intensity_index=0,
            label="labels",
            transfer=layer_models.TransferFunctionModel(categorical=True),
        )
        return layer_models.BlendNodeModel(blending=enums.Blending.NORMAL, children=[child], label="labels")

    return layer_models.BlendNodeModel(blending=enums.Blending.ADDITIVE, children=_channel_sources(dataset, render, size), label="intensity")
