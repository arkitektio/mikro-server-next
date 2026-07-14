"""One scene's slice of the coordinate graph, fetched once and searched in memory.

Every placement question a scene can be asked -- where does this layer sit in world,
where does each pyramid level sit, which systems does the scene reach, which ROIs are
drawn in them -- is a search over the *same* edge universe: the scene's membership set
plus the scene-independent facts of the datasets its layers draw from. That universe was
being rebuilt from the database for every layer and again for every field, which made a
scene's cost quadratic in its layers for an answer that does not change between them.

So it is built once, per scene, per request (see :func:`for_request`), in a fixed number
of queries no matter how many layers ask.

The adjacency stays **partitioned per dataset**, with one exception. Only the fetch is
batched: an unrelated dataset's edges never enter another's search, because the searchable
universe is exactly what fixes which registration applies -- merging them could let a BFS
walk out through a co-tenant of the scene and return a path that is shorter than the truth.

The exception is **lineage**. A derived dataset -- a deconvolution, a projection, a
resample -- does not sit anywhere on its own account: it sits where the data it was
computed from sits, and the walk to world runs through its source's lens, array and
intrinsic systems. Those edges live in the source's bucket, so the search closes over the
datasets a layer's dataset was derived from, transitively. A source is not an unrelated
dataset; it is where the pixels came from.
"""

from django.db.models import Q
from kante.types import Info

from core import enums, models
from core.logic import graph as graph_logic

#: Where a `SceneGraph` memo lives on the request context, keyed by scene pk.
_LOADER_KEY = "scene_graphs"

#: Every edge on a placement path states its own axis order (`Transformation.inputAxes` /
#: `outputAxes`, derived by :func:`core.logic.graph.edge_axis_names`), so the axes of both
#: endpoints ride along with the edges the graph already fetches. Without this the
#: placement query goes back to one query per edge per side.
EDGE_AXIS_PREFETCH = ("input__axes", "output__axes")


def _system_dataset_id(system: "models.CoordinateSystem | None") -> int | None:
    """The pk of the dataset a coordinate system belongs to, read off preloaded FKs."""
    if system is None:
        return None
    if system.intrinsic_of_id:
        return system.intrinsic_of_id
    if system.dataset_id:
        return system.dataset_id
    if system.lens_id:
        return system.lens.dataset_id
    if system.data_array_id:
        return system.data_array.dataset_id
    return None


def _edge_dataset_id(edge: "models.Transformation") -> int | None:
    """The pk of the dataset an edge's input system belongs to, read off preloaded FKs.

    The in-memory mirror of the ``Q(input__intrinsic_of=…) | Q(input__dataset=…) |
    Q(input__lens__dataset=…) | Q(input__data_array__dataset=…)`` filter this replaces.
    A system has at most one owner, so an edge lands in at most one dataset's adjacency.
    """
    return _system_dataset_id(edge.input)


def _derivation_target(edge: "models.Transformation") -> int | None:
    """The dataset this edge derives *from*, if it is a derivation edge; else None.

    A derivation edge leaves its dataset and lands in another one: a deconvolution, a
    projection, a resample stating where its pixels came from. An edge into a scene's
    WORLD system leaves the dataset too, but it lands nowhere -- a world belongs to no
    dataset -- so a registration is not mistaken for a lineage.
    """
    source = _system_dataset_id(edge.output)
    if source is None:
        return None
    return source if source != _edge_dataset_id(edge) else None


class SceneGraph:
    """The edges, layers and pyramid levels of one scene, fetched up front."""

    def __init__(self, scene: "models.Scene") -> None:
        """Fetch the scene's layers, its membership edges and its datasets' edges and levels."""
        self.scene = scene
        self.world = getattr(scene, "world_coordinate_system", None)

        # The layers, with every relation the placement logic walks in Python. The
        # optimizer cannot infer these: it prefetches what the *selection set* names, and
        # a client asking only for `pathToWorld` never names `lens`.
        self.layers = list(scene.layers.select_related(*LAYER_PLACEMENT_RELATIONS))

        # The scene's membership set. Fetched whole and split in Python rather than
        # queried twice: the closure wants every member, the search only the top-level
        # edges (a wrapper's children are steps *within* an edge, not edges of the graph).
        self._member_edges = list(scene.coordinate_transformations.all().select_related("input", "output").prefetch_related("children", *EDGE_AXIS_PREFETCH))
        self._scene_edges = [edge for edge in self._member_edges if edge.parent_id is None]

        # Every dataset any layer draws from -- and then every dataset those were *derived
        # from*, transitively. A derived dataset's placement is not its own fact: it sits
        # where the data it was computed from sits, and the walk to world runs through its
        # source's lens, array and intrinsic systems. Those edges live in the source's
        # bucket, so without closing over the lineage the search dead-ends the moment it
        # crosses the derivation edge.
        self._dataset_ids = {dataset_id for dataset_id in (self._layer_dataset_id(layer) for layer in self.layers) if dataset_id is not None}
        self._dataset_edges: dict[int, list[models.Transformation]] = {}
        self._derived_from: dict[int, int] = {}

        pending = set(self._dataset_ids)
        while pending:
            for dataset_id in pending:
                self._dataset_edges.setdefault(dataset_id, [])

            for edge in self._fetch_dataset_edges(pending):
                dataset_id = _edge_dataset_id(edge)
                if dataset_id in self._dataset_edges:
                    self._dataset_edges[dataset_id].append(edge)
                    source = _derivation_target(edge)
                    if source is not None:
                        self._derived_from[dataset_id] = source

            # The ancestors we have just discovered and not yet fetched. A cycle would be
            # nonsense, but it must not hang the request, so already-seen ids never re-enter.
            pending = {source for source in self._derived_from.values() if source not in self._dataset_edges}
            self._dataset_ids |= pending

        self._adjacency_cache: dict[int | None, dict] = {}
        self._levels: dict[int, list[models.DataArray]] | None = None

    def _fetch_dataset_edges(self, dataset_ids: set[int]) -> list["models.Transformation"]:
        """Every top-level edge whose input system is owned by one of these datasets."""
        edges = models.Transformation.objects.filter(parent__isnull=True).filter(
            Q(input__intrinsic_of__in=dataset_ids)
            | Q(input__dataset__in=dataset_ids)
            | Q(input__lens__dataset__in=dataset_ids)
            | Q(input__data_array__dataset__in=dataset_ids)
        )
        return list(
            edges.select_related(
                "input",
                "output",
                "input__lens",
                "input__data_array",
                "output__lens",
                "output__data_array",
            ).prefetch_related("children", *EDGE_AXIS_PREFETCH)
        )

    def _lineage(self, dataset_id: int) -> list[int]:
        """A dataset and every dataset it was derived from, nearest first."""
        chain = [dataset_id]
        seen = {dataset_id}
        current = dataset_id
        while (source := self._derived_from.get(current)) is not None and source not in seen:
            chain.append(source)
            seen.add(source)
            current = source
        return chain

    # --- the edge universe ---------------------------------------------------

    def _layer_dataset_id(self, layer: "models.Layer") -> int | None:
        """The dataset a layer's source system belongs to, without touching the database."""
        source = graph_logic.layer_source_system(layer)
        if source is None:
            return None
        dataset = graph_logic.system_dataset(source)
        return dataset.pk if dataset else None

    def adjacency(self, dataset_id: int | None) -> dict[int, list[tuple["models.Transformation", bool, int]]]:
        """The searchable edge universe for one dataset: its lineage's edges plus the scene's.

        The partition holds where it matters. An *unrelated* dataset's edges still never
        enter this search -- that is what stops a BFS wandering out through a co-tenant of
        the scene and returning a path shorter than the truth. But a dataset this one was
        derived from is not unrelated: the path to world runs straight through it.
        """
        if dataset_id in self._adjacency_cache:
            return self._adjacency_cache[dataset_id]

        edges = list(self._scene_edges)
        if dataset_id is not None:
            for ancestor_id in self._lineage(dataset_id):
                edges += self._dataset_edges.get(ancestor_id, [])

        adjacency: dict[int, list[tuple[models.Transformation, bool, int]]] = {}
        seen: set[int] = set()
        for edge in edges:
            if edge.pk in seen or not edge.input_id or not edge.output_id:
                continue
            seen.add(edge.pk)
            adjacency.setdefault(edge.input_id, []).append((edge, False, edge.output_id))
            # Backwards only if the edge has an inverse to offer. A rank-changing edge
            # does not, and an `inverted: true` step over one asks the client to invert a
            # matrix that is not square.
            if graph_logic.is_reverse_traversable(edge):
                adjacency.setdefault(edge.output_id, []).append((edge, True, edge.input_id))

        self._adjacency_cache[dataset_id] = adjacency
        return adjacency

    def _data_arrays(self, dataset_id: int) -> list["models.DataArray"]:
        """The pyramid levels of one dataset, from a single query covering every dataset in the scene."""
        if self._levels is None:
            self._levels = {dataset_id: [] for dataset_id in self._dataset_ids}
            if self._dataset_ids:
                arrays = models.DataArray.objects.filter(dataset__in=self._dataset_ids).order_by("level").select_related("coordinate_system")
                for array in arrays:
                    self._levels.setdefault(array.dataset_id, []).append(array)
        return self._levels.get(dataset_id, [])

    # --- the questions -------------------------------------------------------

    def placement_path(self, layer: "models.Layer") -> list[tuple["models.Transformation", bool]] | None:
        """The path of edges from a layer's source system to this scene's world system.

        ``None`` when the layer has no source system or no path; ``[]`` when the source
        already is the world system. See :func:`core.logic.graph.path_in_scene`.
        """
        source = graph_logic.layer_source_system(layer)
        if source is None or self.world is None:
            return None
        return graph_logic._bfs_path(self.adjacency(self._layer_dataset_id(layer)), source.pk, self.world.pk)

    def level_placements(self, layer: "models.Layer") -> list[tuple["models.DataArray", list[tuple["models.Transformation", bool]] | None]]:
        """Per pyramid level, the path from that level's voxel grid to this scene's world system."""
        if layer.kind != enums.LayerKindChoices.IMAGE.value or not layer.lens_id:
            return []

        dataset_id = layer.lens.dataset_id
        arrays = self._data_arrays(dataset_id)
        if self.world is None:
            return [(array, None) for array in arrays]

        adjacency = self.adjacency(dataset_id)
        placements = []
        for array in arrays:
            system = getattr(array, "coordinate_system", None)
            placements.append((array, graph_logic._bfs_path(adjacency, system.pk, self.world.pk) if system else None))
        return placements

    def reachable_system_ids(self) -> set[int]:
        """The ids of the coordinate systems this scene touches, directly or through its edges.

        Seeded from the world system and each layer's data source, then closed over the
        membership edges. An edge no layer and no world system can reach is not part of
        this scene's graph, even if the row exists.
        """
        seeds: set[int] = set()
        if self.world:
            seeds.add(self.world.pk)

        for layer in self.layers:
            lens = layer.lens if layer.lens_id else None
            if not lens:
                continue
            lens_system = getattr(lens, "coordinate_system", None)
            if lens_system:
                seeds.add(lens_system.pk)
            intrinsic = lens.dataset.intrinsic_coordinate_system
            if intrinsic:
                seeds.add(intrinsic.pk)

        edges = [(edge.input_id, edge.output_id) for edge in self._member_edges if edge.input_id and edge.output_id]

        # Undirected closure: an edge joins two systems, and a client may traverse it in
        # either direction (it inverts the matrix itself).
        reachable = set(seeds)
        changed = True
        while changed:
            changed = False
            for source, target in edges:
                if source in reachable and target not in reachable:
                    reachable.add(target)
                    changed = True
                elif target in reachable and source not in reachable:
                    reachable.add(source)
                    changed = True

        return reachable

    def reachable_systems(self) -> list["models.CoordinateSystem"]:
        """The coordinate systems this scene can reach, as rows."""
        return list(models.CoordinateSystem.objects.filter(pk__in=self.reachable_system_ids()))


#: The relations the placement logic reads off a layer in Python. `Layer` is one table
#: discriminated by `kind`, so a single select_related covers every layer kind.
LAYER_PLACEMENT_RELATIONS = (
    "scene__world_coordinate_system",
    "lens__dataset__intrinsic_system",
    "lens__coordinate_system",
    "data_roi__coordinate_system",
    "mesh_collection__coordinate_system",
    "coordinate_system",
)


def for_request(info: "Info", scene: "models.Scene") -> SceneGraph:
    """This scene's graph, built once per request.

    Memoized on the context's ``_loaders`` -- the per-request store kante already carries
    for exactly this (``kante.context.HttpContext``). Without it, every layer of a scene
    would rebuild the scene's whole edge universe to ask its one question about it.
    """
    context = info.context
    loaders = getattr(context, "_loaders", None)
    if loaders is None:
        return SceneGraph(scene)

    graphs = loaders.setdefault(_LOADER_KEY, {})
    if scene.pk not in graphs:
        graphs[scene.pk] = SceneGraph(scene)
    return graphs[scene.pk]
