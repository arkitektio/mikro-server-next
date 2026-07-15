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
    """The pk of the dataset a coordinate system belongs to, read off preloaded FKs.

    A collection's system has no dataset FK to read -- it is anchored to one by an *edge*
    -- so this returns None for it, and :meth:`SceneGraph._dataset_id_of` resolves it from
    the anchor edges the graph fetched up front. Following the edge here instead would be
    a query per system, which is the N+1 this whole module exists to prevent.
    """
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

    An UNMAPPABLE derivation lands in another dataset and still yields nothing here: this
    closure exists to pull a source's edges into the search, and no search can cross that
    edge to use them. Following it would widen the adjacency with edges the BFS can never
    reach, for a path that does not exist.
    """
    if not graph_logic.is_traversable(edge):
        return None
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

        # A collection (meshes, features) owns its coordinate system rather than borrowing
        # its dataset's, so nothing on that system says which dataset it came from -- the
        # derivation edge does. Fetch them all in one query, before anything asks: resolving
        # them one system at a time is a query per layer, and this graph exists to make the
        # placement API flat in its layer count.
        self._collection_edges = self._fetch_collection_edges()
        self._collection_source = {system_id: _system_dataset_id(edge.output) for system_id, edge in self._collection_edges.items()}

        # Every dataset any layer draws from -- and then every dataset those were *derived
        # from*, transitively. A derived dataset's placement is not its own fact: it sits
        # where the data it was computed from sits, and the walk to world runs through its
        # source's lens, array and intrinsic systems. Those edges live in the source's
        # bucket, so without closing over the lineage the search dead-ends the moment it
        # crosses the derivation edge.
        self._dataset_ids = {dataset_id for dataset_id in (self._layer_dataset_id(layer) for layer in self.layers) if dataset_id is not None}
        self._dataset_edges: dict[int, list[models.Transformation]] = {}
        # Every parent, not just one: a fusion derives from several datasets, and a path
        # to world through any of them is a real placement.
        self._derived_from: dict[int, set[int]] = {}

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
                        self._derived_from.setdefault(dataset_id, set()).add(source)

            # The ancestors we have just discovered and not yet fetched. A cycle would be
            # nonsense, but it must not hang the request, so already-seen ids never re-enter.
            pending = {source for sources in self._derived_from.values() for source in sources if source not in self._dataset_edges}
            self._dataset_ids |= pending

        # A collection's derivation edge leaves the collection's own system, which no
        # dataset owns, so `_fetch_dataset_edges` (which filters on the input system's
        # dataset FKs) never sees it. File it with the dataset it lands in, or a mesh
        # layer's search starts on a system with no edges at all and can go nowhere.
        for system_id, edge in self._collection_edges.items():
            dataset_id = self._collection_source.get(system_id)
            if dataset_id in self._dataset_edges:
                self._dataset_edges[dataset_id].append(edge)

        self._adjacency_cache: dict[int | None, dict] = {}
        self._levels: dict[int, list[models.DataArray]] | None = None

    def _fetch_collection_edges(self) -> dict[int, "models.Transformation"]:
        """The derivation edge out of each collection system the scene's layers draw from, keyed by system.

        Optional per collection: a mesh in some absolute space is derived from no dataset
        and simply has none.
        """
        system_ids = set()
        for layer in self.layers:
            source = graph_logic.layer_source_system(layer)
            if source is not None and (source.mesh_collection_id or source.feature_collection_id):
                system_ids.add(source.pk)

        if not system_ids:
            return {}

        edges = (
            models.Transformation.objects.filter(input_id__in=system_ids, parent__isnull=True)
            .select_related("input", "output", "output__lens", "output__data_array")
            .prefetch_related("children", *EDGE_AXIS_PREFETCH)
            .order_by("pk")
        )

        collection_edges: dict[int, models.Transformation] = {}
        for edge in edges:
            collection_edges.setdefault(edge.input_id, edge)
        return collection_edges

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
        """A dataset and every dataset it was derived from, transitively, nearest first.

        Breadth-first over every parent: a fusion's path to world may run through any of
        its sources, so all of their edges belong in the search universe.
        """
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

    # --- the edge universe ---------------------------------------------------

    def _dataset_id_of(self, system: "models.CoordinateSystem | None") -> int | None:
        """The dataset a system belongs to, by FK or -- for a collection's own system -- by derivation edge."""
        if system is None:
            return None
        owned = _system_dataset_id(system)
        if owned is not None:
            return owned
        return self._collection_source.get(system.pk)

    def _layer_dataset_id(self, layer: "models.Layer") -> int | None:
        """The dataset a layer's source system belongs to, without touching the database."""
        return self._dataset_id_of(graph_logic.layer_source_system(layer))

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

        adjacency = graph_logic.adjacency_of(edges)
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

    def placement_validity(self, layer: "models.Layer") -> str:
        """How much this layer's placement is actually known: the weakest edge on its path.

        Derived, never stored -- validity is a fact about a *registration*, and the
        registration is a scene-level edge. When it was a layer column, two layers over
        one dataset carried two copies of how-known one edge is, and nothing ever wrote
        either. An unplaced layer is UNKNOWN (there is nothing to know the validity of);
        a layer whose source already is the world has an exact placement.
        """
        steps = self.placement_path(layer)
        if steps is None:
            return enums.PlacementValidityChoices.UNKNOWN.value
        if not steps:
            return enums.PlacementValidityChoices.VALIDATED.value

        rank = {
            enums.PlacementValidityChoices.UNKNOWN.value: 0,
            enums.PlacementValidityChoices.INFERRED.value: 1,
            enums.PlacementValidityChoices.MANUAL.value: 2,
            enums.PlacementValidityChoices.VALIDATED.value: 3,
        }
        return min((edge.validity for edge, _ in steps), key=lambda validity: rank.get(validity, 0))

    def placement_state(self, layer: "models.Layer") -> str:
        """Whether this layer has a place in the world, and if not, why not.

        ``pathToWorld`` being null means two very different things, and a client cannot
        tell them apart from the null alone: either nobody has registered this data yet --
        a gap, and authoring the edge closes it -- or its data reaches the world only
        across an UNMAPPABLE edge, in which case there is nothing to find and looking for
        the missing registration is a waste of a person's afternoon.

        Derived from what the graph already holds, and stored nowhere: a second copy of
        this fact could disagree with the edges, and the edges would be right.
        """
        if self.placement_path(layer) is not None:
            return enums.PlacementState.PLACED.value

        source = graph_logic.layer_source_system(layer)
        if source is not None:
            # A collection's data (a feature table) is unmappable when its derivation edge
            # says so; a dataset's is when the derivation it came out of does.
            derivation = self._collection_edges.get(source.pk)
            if derivation is not None and not graph_logic.is_traversable(derivation):
                return enums.PlacementState.UNMAPPABLE.value

        dataset_id = self._layer_dataset_id(layer)
        if dataset_id is not None:
            if any(not graph_logic.is_traversable(edge) for edge in self._dataset_edges.get(dataset_id, [])):
                return enums.PlacementState.UNMAPPABLE.value

        return enums.PlacementState.UNREGISTERED.value

    def level_placements(self, layer: "models.Layer") -> list[tuple["models.DataArray", list[tuple["models.Transformation", bool]] | None]]:
        """Per pyramid level, the path from that level's voxel grid to this scene's world system."""
        if layer.kind != enums.LayerKindChoices.IMAGE.value or not layer.lens_id:
            return []

        dataset_id = layer.lens.dataset_id
        arrays = self._data_arrays(dataset_id)
        if self.world is None:
            return [(array, None) for array in arrays]

        adjacency = self.adjacency(dataset_id)
        # Level 0 owns no system -- its voxel space IS the dataset's intrinsic system, which
        # rides along on the layer's prefetched lens, so the fallback costs no query.
        intrinsic = layer.lens.dataset.intrinsic_coordinate_system
        placements = []
        for array in arrays:
            system = getattr(array, "coordinate_system", None) or (intrinsic if array.level == 0 else None)
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
