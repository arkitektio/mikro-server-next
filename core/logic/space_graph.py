"""One shared space's slice of the coordinate graph, fetched once and searched in memory.

The space-rooted twin of :mod:`core.logic.scene_graph`. A scene's graph is seeded by its
layers; this one is seeded by the *registrations into the space itself*, because the
question is not "where does this composition put its layers" but "what is in here at all".
A space needs no scene to answer that, and two scenes over one space must get the same
answer -- which they do, because registrations are a property of the space (RFC-6) and
nothing here consults a scene.

**Everything composes forward.** There is no matrix inverse in this codebase and there is
not going to be one here. A source is anchored at the system that actually carries its
registration, so the walk runs *with* the edges rather than against them; the rare edge
authored backwards yields a null extent with a state saying so, rather than a number nobody
computed.

**Nothing is stored.** A per-(source, space) box would be a cache that goes stale the
moment anyone refines a registration, and this repo already carries that bug once
(``Annotation.bbox_cube`` against ``created_with_transforms``, whose bulk recompute is
documented as a separate operation that does not exist). The extent is derived per request
from the shapes and the edges, which cannot disagree with themselves.

**An extent is partial, and that is the point.** Composing at one fixed rank is right
inside a dataset and wrong across a registration: a (c,y,x) dataset registered onto the
(y,x) of a (z,y,x) world is a *slab*, extended along z. The extent names the axes it
constrains and stays silent about the rest, because a number written for z would cull the
dataset out of every view it is really in.
"""

from dataclasses import dataclass

from django.db.models import Q
from kante.types import Info

from core import enums, models
from core.logic import coords as coords_logic
from core.logic import graph as graph_logic
from core.logic import scene_graph

#: Where a `SpaceGraph` memo lives on the request context, keyed by space pk.
_LOADER_KEY = "space_graphs"


@dataclass(frozen=True)
class Source:
    """One container registered into the space, and the system its registration is anchored at."""

    container: object
    system: "models.CoordinateSystem"
    dataset_id: int | None


@dataclass(frozen=True)
class Hit:
    """One source in view: where it is, how it got there, and which of its anchors are in view."""

    source: Source
    extent: dict[str, list[float]] | None
    extent_state: str
    path: list[tuple["models.Transformation", bool]]
    anchors: list["models.CoordinateAnchor"]


def _container_of(system: "models.CoordinateSystem") -> object | None:
    """The container a candidate system belongs to, off already-selected FKs.

    A bare shared space registered into this one is deliberately not a container: it has no
    data of its own to be in view.
    """
    return (
        system.intrinsic_of
        or system.mesh_collection
        or system.table_dataset
        or system.annotation_collection
        or (system.lens.dataset if system.lens_id else None)
        or (system.data_array.dataset if system.data_array_id else None)
        or system.dataset
    )


def _system_box(system: "models.CoordinateSystem", shapes: dict[int, list[int]]) -> tuple[list[float], list[float]] | None:
    """A system's own extent in its own frame, half-open around the voxel centre.

    A shape ``S`` spans ``[-0.5, S - 0.5]``, the convention :func:`coords.vectors_bbox`
    encodes and that :func:`coords.pyramid_transform`'s half-voxel translation exists to
    keep true across levels: level 1's ``[-0.5, 31.5]`` maps onto level 0's
    ``[-0.5, 63.5]``, the same box, which it would not if the origin were the voxel corner.

    None where the server holds no geometry: a calibrated space has no shape, and a mesh
    collection's vertices and a table's rows are in Parquet it never opens.
    """
    if system.lens_id:
        shape = system.lens.shape_list
    elif system.data_array_id:
        shape = system.data_array.shape
    elif system.intrinsic_of_id:
        shape = shapes.get(system.intrinsic_of_id) or []
    else:
        return None

    if not shape:
        return None
    return [-0.5] * len(shape), [float(size) - 0.5 for size in shape]


class SpaceGraph:
    """Every source registered into one space, with the edges that place them, fetched up front."""

    def __init__(self, space: "models.CoordinateSystem", *, organization) -> None:
        """Fetch the space's edges, its registered systems, and those systems' fact trees."""
        self.space = space
        self.organization = organization

        # Both directions, exactly as `SceneGraph._world_edges` does and for the same reason:
        # a registration authored space -> source must degrade to an inverted step, not to an
        # unreachable space. Organization-scoped because this returns whole containers, and a
        # shared space can have co-tenants whose data this request may not see.
        self._space_edges = list(
            models.Transformation.objects.filter(Q(output=space) | Q(input=space), parent__isnull=True, organization=organization)
            .select_related("input", "input__lens", "input__data_array", "output")
            .prefetch_related("children", *scene_graph.EDGE_AXIS_PREFETCH)
        )

        # The space itself stays a candidate. When it is *owned* -- a scene rooted directly
        # on a dataset's pixel grid or a collection's space -- that container is in view of
        # itself by construction, with an empty path. `_container_of` drops it again when it
        # is a bare shared space, which owns no data and is nothing to see.
        candidate_ids = graph_logic.placeable_system_ids_in(space)
        self._candidates = (
            list(
                models.CoordinateSystem.objects.filter(pk__in=candidate_ids, organization=organization)
                .select_related("intrinsic_of", "dataset", "lens__dataset", "data_array__dataset", "mesh_collection", "table_dataset", "annotation_collection")
                .prefetch_related("axes")
            )
            if candidate_ids
            else []
        )

        dataset_ids = {dataset_id for system in self._candidates if (dataset_id := graph_logic._fk_dataset_id(system)) is not None}
        self._dataset_edges, self._derived_from, self._dataset_ids = scene_graph.dataset_buckets(dataset_ids)

        self._collection_edges = self._fetch_collection_edges()
        for system_id, edge in self._collection_edges.items():
            source_dataset = scene_graph._system_dataset_id(edge.output)
            if source_dataset in self._dataset_edges:
                self._dataset_edges[source_dataset].append(edge)

        self._shapes: dict[int, list[int]] | None = None
        self._anchors: dict[int, list[models.CoordinateAnchor]] | None = None
        self._adjacency_cache: dict[int | None, dict] = {}
        self._sources: list[Source] | None = None

    def _fetch_collection_edges(self) -> dict[int, "models.Transformation"]:
        """The derivation edge out of each candidate collection system, keyed by system."""
        system_ids = {system.pk for system in self._candidates if system.mesh_collection_id or system.table_dataset_id or system.annotation_collection_id}
        if not system_ids:
            return {}

        edges = (
            models.Transformation.objects.filter(input_id__in=system_ids, parent__isnull=True)
            .select_related("input", "output", "output__lens", "output__data_array")
            .prefetch_related("children", *scene_graph.EDGE_AXIS_PREFETCH)
            .order_by("pk")
        )
        collection_edges: dict[int, models.Transformation] = {}
        for edge in edges:
            collection_edges.setdefault(edge.input_id, edge)
        return collection_edges

    def shapes(self) -> dict[int, list[int]]:
        """Every reachable dataset's level-0 shape, in one query.

        Batched rather than read off ``ADataset.shape_list``, which is a query per dataset
        and would make the cost of this whole graph grow with its source count.
        """
        if self._shapes is None:
            rows = models.DataArray.objects.filter(dataset_id__in=self._dataset_ids, level=0).values_list("dataset_id", "shape") if self._dataset_ids else []
            self._shapes = {dataset_id: shape for dataset_id, shape in rows}
        return self._shapes

    def _anchors_of(self, dataset_id: int) -> list["models.CoordinateAnchor"]:
        """Every reachable dataset's anchors, in one query, and only once anyone asks.

        Lazy on purpose: a 1000-timepoint four-channel dataset has thousands of anchor rows,
        and a client asking only for extents should not pay for them.
        """
        if self._anchors is None:
            self._anchors = {}
            if self._dataset_ids:
                for anchor in models.CoordinateAnchor.objects.filter(dataset_id__in=self._dataset_ids):
                    self._anchors.setdefault(anchor.dataset_id, []).append(anchor)
        return self._anchors.get(dataset_id, [])

    def _lineage(self, dataset_id: int) -> list[int]:
        """A dataset and its primary-parent chain, nearest first."""
        chain = [dataset_id]
        seen = {dataset_id}
        frontier = [dataset_id]
        while frontier:
            next_frontier: list[int] = []
            for current in frontier:
                for source in sorted(self._derived_from.get(current, ())):
                    if source in seen:
                        continue
                    seen.add(source)
                    chain.append(source)
                    next_frontier.append(source)
            frontier = next_frontier
        return chain

    def adjacency(self, dataset_id: int | None) -> dict:
        """The searchable universe for one dataset: its lineage's facts plus this space's claims.

        Partitioned per dataset, exactly as :meth:`SceneGraph.adjacency` is and for the same
        reason: merging buckets lets a BFS wander out through a co-tenant of the space and
        come back with a path shorter than the truth.
        """
        if dataset_id in self._adjacency_cache:
            return self._adjacency_cache[dataset_id]

        edges = list(self._space_edges)
        if dataset_id is not None:
            for ancestor_id in self._lineage(dataset_id):
                edges += self._dataset_edges.get(ancestor_id, [])

        adjacency = graph_logic.adjacency_of(edges)
        self._adjacency_cache[dataset_id] = adjacency
        return adjacency

    def sources(self) -> list[Source]:
        """Every container registered into the space, anchored at the system that carries its claim.

        The anchor system matters and is not always intrinsic. A dataset registered through a
        *sliced lens* anchors at the lens' system, whose shape is an exact box that composes
        forward; anchoring it at intrinsic instead would force the walk backwards across the
        lens edge and give no extent at all. ``_assert_one_claim_per_space`` guarantees the
        choice is never ambiguous -- there is at most one claim per fact tree per space.
        """
        if self._sources is not None:
            return self._sources

        claimed = {edge.input_id for edge in self._space_edges if edge.output_id == self.space.pk and edge.input_id is not None}

        by_container: dict[tuple, Source] = {}
        for system in self._candidates:
            container = _container_of(system)
            if container is None:
                continue
            key = graph_logic._container_key(system)
            dataset_id = graph_logic._fk_dataset_id(system)
            if dataset_id is None:
                dataset_id = scene_graph._system_dataset_id((edge := self._collection_edges.get(system.pk)) and edge.output)
            candidate = Source(container=container, system=system, dataset_id=dataset_id)
            # The claim-carrying system wins; otherwise the first candidate holds the slot,
            # so a container with no claim of its own (a derived dataset placed through its
            # parent) still gets one.
            if key not in by_container or system.pk in claimed:
                by_container[key] = candidate

        self._sources = sorted(by_container.values(), key=lambda source: source.system.pk)
        return self._sources

    def path(self, source: Source) -> list[tuple["models.Transformation", bool]] | None:
        """The path of edges from a source's system into the space, or None when there is none."""
        return graph_logic._bfs_path(self.adjacency(source.dataset_id), source.system.pk, self.space.pk)

    def _forms(self, source: Source, path: list[tuple["models.Transformation", bool]]) -> dict[str, coords_logic.AxedForm] | None:
        """The composed functionals from a source's frame into the space, or None when there are none."""
        if any(inverted for _, inverted in path):
            return None
        steps = [graph_logic._edge_step(edge) for edge, _ in path]
        source_axes = [axis.name for axis in source.system.axes.all()]
        return coords_logic.compose_forms(steps, source_axes)

    def placement(self, source: Source, region: dict[str, list[float]]) -> Hit | None:
        """One source's placement in the space, or None when it is not in view.

        The states are ordered, and the order is a precedence: a source whose geometry the
        server cannot read is UNREADABLE whatever its path looks like, and only then does the
        path's own shape get a say.

        A source is never culled for being unbounded. Refusing to bound something is not the
        same as knowing it is out of view, and a client that has been handed a null extent
        with a reason can fetch the geometry and cull it locally.
        """
        path = self.path(source)
        if path is None:
            return None

        box = _system_box(source.system, self.shapes())
        if box is None:
            return Hit(source=source, extent=None, extent_state=enums.ExtentState.UNREADABLE.value, path=path, anchors=[])

        forms = self._forms(source, path)
        if forms is None:
            return Hit(source=source, extent=None, extent_state=enums.ExtentState.INVERTED.value, path=path, anchors=[])

        try:
            extent = coords_logic.axed_bbox(box[0], box[1], forms)
        except coords_logic.NonAffineTransformError:
            return Hit(source=source, extent=None, extent_state=enums.ExtentState.NON_AFFINE.value, path=path, anchors=[])

        if not coords_logic.boxes_overlap(extent, region):
            return None

        return Hit(source=source, extent=extent, extent_state=enums.ExtentState.KNOWN.value, path=path, anchors=[])

    def anchors_in(self, source: Source, region: dict[str, list[float]]) -> list["models.CoordinateAnchor"]:
        """The source's anchors whose slab overlaps the region.

        An anchor is already a slab rather than a point: ``coordinates`` pins some axes to
        discrete level-0 indices and is **global along every axis it omits**. So a pinned axis
        is one voxel wide and an omitted one spans the container's whole extent, and the slab
        then composes and intersects exactly like any other box -- no separate treatment of
        discrete versus spatial axes. This is the geometric generalization of
        :attr:`Lens.active_anchors`' "does not contradict" rule, which can stay a ``Q`` only
        because a lens and its anchors share one frame.

        Anchor coordinates are always level-0 *intrinsic* indices, so the slab is pushed from
        the dataset's intrinsic system -- not from the source's anchor system, which may be a
        lens or a level whose indices are its own. The two frames look alike, which is exactly
        how a half-voxel goes missing.
        """
        if source.dataset_id is None:
            return []
        anchors = self._anchors_of(source.dataset_id)
        if not anchors:
            return []

        dataset = source.container if isinstance(source.container, models.ADataset) else None
        intrinsic = dataset.intrinsic_coordinate_system if dataset is not None else None
        if intrinsic is None:
            return []

        shape = self.shapes().get(source.dataset_id) or []
        if not shape:
            return []

        path = graph_logic._bfs_path(self.adjacency(source.dataset_id), intrinsic.pk, self.space.pk)
        if path is None or any(inverted for _, inverted in path):
            return []

        axis_names = [axis.name for axis in intrinsic.axes.all()]
        try:
            forms = coords_logic.compose_forms([graph_logic._edge_step(edge) for edge, _ in path], axis_names)
        except coords_logic.NonAffineTransformError:
            return []

        in_view: list[models.CoordinateAnchor] = []
        for anchor in anchors:
            coordinates = anchor.coordinates or {}
            mins: list[float] = []
            maxs: list[float] = []
            for index, name in enumerate(axis_names):
                if name in coordinates:
                    value = float(coordinates[name])
                    mins.append(value - 0.5)
                    maxs.append(value + 0.5)
                else:
                    mins.append(-0.5)
                    maxs.append(float(shape[index]) - 0.5 if index < len(shape) else 0.5)
            if coords_logic.boxes_overlap(coords_logic.axed_bbox(mins, maxs, forms), region):
                in_view.append(anchor)
        return in_view

    def in_view(self, region: dict[str, list[float]], *, with_anchors: bool) -> list[Hit]:
        """Every source whose extent meets the region, each with its in-view anchors."""
        hits: list[Hit] = []
        for source in self.sources():
            hit = self.placement(source, region)
            if hit is None:
                continue
            if with_anchors:
                hit = Hit(source=hit.source, extent=hit.extent, extent_state=hit.extent_state, path=hit.path, anchors=self.anchors_in(source, region))
            hits.append(hit)
        return hits


def region_from_bounds(space: "models.CoordinateSystem", mins: list[float], maxs: list[float]) -> dict[str, list[float]]:
    """A positional region keyed against the space's axes, as a leading prefix.

    A region shorter than the system constrains only its leading axes and says nothing about
    the rest. Deliberately *not* the zero-fill Postgres ``cube`` gives
    ``AnnotationFilter.intersects``: zero-filling a viewport's missing axes pins them to
    ``[0, 0]`` and culls away everything off the first plane.
    """
    if len(mins) != len(maxs):
        raise ValueError(f"A region's `min` and `max` must have the same number of entries, got {len(mins)} and {len(maxs)}")

    axis_names = [axis.name for axis in space.axes.all()]
    if len(mins) > len(axis_names):
        raise ValueError(f"A region of {len(mins)} axes was asked of '{space.name}', whose axes are {axis_names}. A region names a leading prefix of the system's axes; it cannot name more than it has.")

    return {name: [float(low), float(high)] for name, low, high in zip(axis_names, mins, maxs)}


def for_request(info: "Info", space: "models.CoordinateSystem") -> SpaceGraph:
    """This space's graph, built once per request and memoized on the context's loader store."""
    context = info.context
    organization = context.request.organization
    loaders = getattr(context, "_loaders", None)
    if loaders is None:
        return SpaceGraph(space, organization=organization)

    graphs = loaders.setdefault(_LOADER_KEY, {})
    if space.pk not in graphs:
        graphs[space.pk] = SpaceGraph(space, organization=organization)
    return graphs[space.pk]
