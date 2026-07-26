"""One scene's slice of the coordinate graph, fetched once and searched in memory.

Every placement question a scene can be asked -- where does this layer sit in world,
where does each pyramid level sit, which systems does the scene reach, which ROIs are
drawn in them -- is a search over the *same* edge universe: the registrations into the
scene's world plus the scene-independent facts of the datasets its layers draw from. That
universe was being rebuilt from the database for every layer and again for every field,
which made a scene's cost quadratic in its layers for an answer that does not change
between them.

So it is built once, per scene, per request (see :func:`for_request`), in a fixed number
of queries no matter how many layers ask.

The adjacency stays **partitioned per dataset**, with one exception. Only the fetch is
batched: an unrelated dataset's edges never enter another's search -- a bucket is the
scope of a search, and merging them would let a BFS return a path through a co-tenant
that is shorter than the truth.

Edges into a **shared space** (a world) are *claims*, and one truth per space
(RFC-6) makes them unique per data-tree: the world's registrations are a property of the
space itself, shared by every scene over it, so the search simply includes them -- there
is no membership to consult and nothing to choose. The dataset buckets carry a dataset's
own spatial facts -- its levels, lenses, calibrations and its *primary* derivation -- and
never any claim; a rival placement is not a rival edge but a claim into a different
space, which this scene's search never sees.

The exception is **lineage**. A derived dataset -- a deconvolution, a projection, a
resample -- does not sit anywhere on its own account: it sits where its primary parent
sits, and the walk to world runs through that parent's lens, array and intrinsic
systems. Those edges live in the parent's bucket, so the search closes over the primary
chain above a layer's dataset. A primary parent is not an unrelated dataset; it is where
the pixels came from.
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


def _system_dataset_id(system: "models.CoordinateSystem | None", residence: dict[int, int]) -> int | None:
    """The pk of the dataset whose data lives in this space, read from a prebuilt map.

    The map is the point. Ownership put the answer in a column on the space; residence puts
    it on the *data*, so it is gathered once for a whole batch by
    :func:`core.logic.graph.residence_map` and read here for free. Doing it per system would
    be a query each, which is the N+1 this whole module exists to prevent.

    None for a collection's space -- a mesh or table is related to a dataset by an *edge*,
    not by living in its grid -- and :meth:`SceneGraph._dataset_id_of` resolves that from the
    anchor edges the graph fetched up front.
    """
    return residence.get(system.pk) if system is not None else None


def _edge_dataset_id(edge: "models.Transformation", residence: dict[int, int]) -> int | None:
    """The pk of the dataset whose data lives in an edge's input space.

    The in-memory mirror of the ``Q(input__datasets=…) | Q(input__lenses__dataset=…) |
    Q(input__data_arrays__dataset=…)`` filter this replaces. A space several datasets share
    resolves to one of them deterministically, so an edge still lands in one bucket.
    """
    return _system_dataset_id(edge.input, residence)


def _derivation_target(edge: "models.Transformation", residence: dict[int, int]) -> int | None:
    """The dataset this edge derives *from*, if it is a derivation edge; else None.

    A derivation edge leaves its dataset and lands in another one: a deconvolution, a
    projection, a resample stating where its pixels came from. An edge into a scene's
    world system leaves the dataset too, but it lands nowhere -- a world belongs to no
    dataset -- so a registration is not mistaken for a lineage.

    An UNMAPPABLE derivation lands in another dataset and still yields nothing here: this
    closure exists to pull a source's edges into the search, and no search can cross that
    edge to use them. Following it would widen the adjacency with edges the BFS can never
    reach, for a path that does not exist.
    """
    if not graph_logic.is_traversable(edge):
        return None
    source = _system_dataset_id(edge.output, residence)
    if source is None:
        return None
    return source if source != _edge_dataset_id(edge, residence) else None


def fetch_dataset_edges(dataset_ids: set[int]) -> list["models.Transformation"]:
    """Every top-level edge whose input system is owned by one of these datasets."""
    edges = models.Transformation.objects.filter(parent__isnull=True).filter(
        Q(input__datasets__in=dataset_ids)
        | Q(input__lenses__dataset__in=dataset_ids)
        | Q(input__data_arrays__dataset__in=dataset_ids)
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


def dataset_buckets(seed_ids: set[int]) -> tuple[dict[int, list["models.Transformation"]], dict[int, set[int]], set[int]]:
    """Every seeded dataset's own fact edges, closed over its primary-parent lineage.

    Returns ``(edges by dataset, parents by dataset, every dataset id reached)``.

    A derived dataset's placement is not its own fact: it sits where the data it was
    computed from sits, and the walk to a space runs through its source's lens, array and
    intrinsic systems. Those edges live in the source's bucket, so without closing over the
    lineage a search dead-ends the moment it crosses the derivation edge.

    One query per lineage *generation*, not per dataset, which is what keeps a graph flat in
    its source count.

    Module-level because a second root needed the same buckets from different seeds: a scene
    seeds them from its layers (:class:`SceneGraph`), a shared space from its registrations
    (:mod:`core.logic.space_graph`). The seeding differs; the bucketing must not.
    """
    dataset_ids = set(seed_ids)
    dataset_edges: dict[int, list[models.Transformation]] = {}
    # Every parent, not just one: a fusion derives from several datasets, and a path
    # through any of them is a real placement.
    derived_from: dict[int, set[int]] = {}

    pending = set(dataset_ids)
    while pending:
        for dataset_id in pending:
            dataset_edges.setdefault(dataset_id, [])

        # One residence map for the whole generation, then every bucketing decision below is
        # a dict read. There is no fact/claim filter to apply any more (RFC-9): a bucket
        # carries every edge leaving a space its dataset's data lives in, and which of
        # several routes a placement takes is settled later, by `best_path`.
        batch_edges = fetch_dataset_edges(pending)
        residence = graph_logic.residence_map({edge.input_id for edge in batch_edges if edge.input_id} | {edge.output_id for edge in batch_edges if edge.output_id})

        for edge in batch_edges:
            dataset_id = _edge_dataset_id(edge, residence)
            if dataset_id in dataset_edges:
                dataset_edges[dataset_id].append(edge)
                source = _derivation_target(edge, residence)
                if source is not None:
                    derived_from.setdefault(dataset_id, set()).add(source)

        # The ancestors just discovered and not yet fetched. A cycle would be nonsense, but
        # it must not hang the request, so already-seen ids never re-enter.
        pending = {source for sources in derived_from.values() for source in sources if source not in dataset_edges}
        dataset_ids |= pending

    return dataset_edges, derived_from, dataset_ids


class SceneGraph:
    """The edges, layers and pyramid levels of one scene, fetched up front."""

    def __init__(self, scene: "models.Scene") -> None:
        """Fetch the scene's layers, its membership edges and its datasets' edges and levels."""
        self.scene = scene

        self.world = scene.world

        # The layers, with every relation the placement logic walks in Python. The
        # optimizer cannot infer these: it prefetches what the *selection set* names, and
        # a client asking only for `pathToWorld` never names `lens`.
        self.layers = list(scene.layers.select_related(*LAYER_PLACEMENT_RELATIONS))

        # The world's own edges: a property of the space, not of this scene (one truth
        # per space, RFC-6) -- every scene over the same world searches the same set.
        # Both directions, matching `graph_logic._placement_universe`: a registration
        # authored backwards (world -> intrinsic) still touches the world, and must
        # degrade to an inverted step rather than an unreachable world. Top-level only:
        # a wrapper's children are steps *within* an edge.
        self._world_edges = (
            list(
                models.Transformation.objects.filter(Q(output=self.world) | Q(input=self.world), parent__isnull=True)
                .select_related("input", "input__lens", "input__data_array", "output")
                .prefetch_related("children", *EDGE_AXIS_PREFETCH)
            )
            if self.world
            else []
        )

        # A collection (meshes, features) owns its coordinate system rather than borrowing
        # its dataset's, so nothing on that system says which dataset it came from -- the
        # derivation edge does. Fetch them all in one query, before anything asks: resolving
        # them one system at a time is a query per layer, and this graph exists to make the
        # placement API flat in its layer count.
        self._collection_edges = self._fetch_collection_edges()
        collection_outputs = {edge.output_id for edge in self._collection_edges.values() if edge.output_id}
        collection_residence = graph_logic.residence_map(collection_outputs)
        self._collection_source = {system_id: _system_dataset_id(edge.output, collection_residence) for system_id, edge in self._collection_edges.items()}

        # Every dataset any layer draws from -- and then every dataset those were *derived
        # from*, transitively. A derived dataset's placement is not its own fact: it sits
        # where the data it was computed from sits, and the walk to world runs through its
        # source's lens, array and intrinsic systems. Those edges live in the source's
        # bucket, so without closing over the lineage the search dead-ends the moment it
        # crosses the derivation edge.
        seeds = {dataset_id for dataset_id in (self._layer_dataset_id(layer) for layer in self.layers) if dataset_id is not None}
        self._dataset_edges, self._derived_from, self._dataset_ids = dataset_buckets(seeds)

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
        self._residence: dict[int, int] | None = None

    def _fetch_collection_edges(self) -> dict[int, "models.Transformation"]:
        """The derivation edge out of each collection system the scene's layers draw from, keyed by system.

        Optional per collection: a mesh in some absolute space is derived from no dataset
        and simply has none.
        """
        system_ids = set()
        for layer in self.layers:
            source = graph_logic.layer_source_system(layer)
            if source is not None and (source.mesh_collection_id or source.table_dataset_id or source.annotation_collection_id):
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

    def _lineage(self, dataset_id: int) -> list[int]:
        """A dataset and its primary-parent chain, nearest first.

        The buckets hold only primary derivations (the fact tree's one parent link per
        dataset), so this is a chain, not a fan: a fusion sits where its primary parent
        sits, and its other parents' edges never entered the universe.
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

    @property
    def residence(self) -> dict[int, int]:
        """``{space: dataset}`` over every space this graph's edges touch, built once.

        Lazy and memoized: three queries, and only for a graph that actually asks which
        dataset a space belongs to.
        """
        if self._residence is None:
            touched = {edge.input_id for edges in self._dataset_edges.values() for edge in edges if edge.input_id}
            touched |= {edge.output_id for edges in self._dataset_edges.values() for edge in edges if edge.output_id}
            touched |= {edge.input_id for edge in self._world_edges if edge.input_id}
            touched |= {edge.output_id for edge in self._world_edges if edge.output_id}
            self._residence = graph_logic.residence_map(touched)
        return self._residence

    def _dataset_id_of(self, system: "models.CoordinateSystem | None") -> int | None:
        """The dataset whose data lives in a space, or -- for a collection's own -- by derivation edge."""
        if system is None:
            return None
        owned = _system_dataset_id(system, self.residence)
        if owned is not None:
            return owned
        return self._collection_source.get(system.pk)

    def _layer_dataset_id(self, layer: "models.Layer") -> int | None:
        """The dataset a layer's source system belongs to, without touching the database."""
        return self._dataset_id_of(graph_logic.layer_source_system(layer))

    def adjacency(self, dataset_id: int | None) -> dict[int, list[tuple["models.Transformation", bool, int]]]:
        """The searchable edge universe for one dataset: its lineage's facts plus the world's claims.

        The partition holds where it matters. An *unrelated* dataset's edges still never
        enter this search -- that is what stops a BFS wandering out through a co-tenant of
        the scene and returning a path shorter than the truth. But a dataset this one was
        derived from is not unrelated: the path to world runs straight through it. The
        result is unique by construction -- one parent edge per system, one claim per
        data-tree into this world -- so the BFS assembles a path rather than choosing one.
        """
        if dataset_id in self._adjacency_cache:
            return self._adjacency_cache[dataset_id]

        edges = list(self._world_edges)
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
        # The empty path is VALIDATED, and that now falls out of the aggregate's default
        # rather than being restated here: a space's placement in itself is exact by
        # construction, which is a property of the order, not of layers.
        return graph_logic.weakest_validity(edge.validity for edge, _ in steps)

    def placement_invariance(self, layer: "models.Layer") -> str:
        """Which geometric properties survive the whole walk from this layer's data to world.

        The min-over-path twin of :meth:`placement_validity`, and a minimum for a stronger
        reason than caution: the invariance groups nest, so a composition belongs to the
        weakest group any of its factors belongs to. An ``inverted`` step needs no handling --
        every one of these classes is closed under inversion, the inverse of an isometry
        being an isometry, of a similarity a similarity.

        The same two edge cases as validity, at the same two ends of the order. An unplaced
        layer is NONE: no path means nothing corresponds. A layer whose source already IS the
        world is ISOMETRY, which falls out of :func:`~core.logic.graph.weakest_invariance` on
        no steps rather than being restated here -- a space is isometric to itself.

        NONE conflates "nobody has registered this yet" with "declared unmappable", exactly as
        UNKNOWN does for validity; :meth:`placement_state` is the field that tells them apart.
        """
        steps = self.placement_path(layer)
        if steps is None:
            return enums.TransformInvariance.NONE.value
        return graph_logic.weakest_invariance(graph_logic.invariance_of(edge) for edge, _ in steps)

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
            # An UNMAPPABLE registration -- a declared non-correspondence with the world
            # itself -- never enters a dataset bucket (no claim does), so it is read off
            # the world's own edges, scoped to this layer's lineage: another dataset's
            # impossibility says nothing about this one.
            lineage = set(self._lineage(dataset_id))
            if any(not graph_logic.is_traversable(edge) and _edge_dataset_id(edge, self.residence) in lineage for edge in self._world_edges):
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
        world's registrations. An edge no layer and no world system can reach is not part
        of this scene's graph, even if the row exists.
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

        edges = [(edge.input_id, edge.output_id) for edge in self._world_edges if edge.input_id and edge.output_id]

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
    "scene__world",
    "lens__dataset__coordinate_system",
    "lens__coordinate_system",
    "annotation_collection__coordinate_system",
    "mesh_collection__coordinate_system",
    "table_dataset__coordinate_system",
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
