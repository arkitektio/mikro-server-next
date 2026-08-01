"""The searchable edges rooted at one space, shared by both roots that search them.

A scene and a shared space ask different questions -- "where does this layer sit in world"
versus "what is in here at all" -- but both are a BFS over the same structure: the edges
touching one space, plus the scene-independent facts of the datasets seeded into it, closed
over their derivation lineage.

That structure belongs to the *space and its seeds*, not to whoever is asking, so it lives
here once and :class:`core.logic.scene_graph.SceneGraph` and
:class:`core.logic.space_graph.SpaceGraph` both compose it. What stays with them is what
genuinely differs: a scene answers per layer and returns edges, a space answers per resident
and composes geometry. Before this module the two carried character-identical copies of the
lineage walk, the adjacency assembly and the collection-edge handling.

The adjacency stays **partitioned per dataset**, with one exception. Only the fetch is
batched: an unrelated dataset's edges never enter another's search -- a bucket is the scope
of a search, and merging them would let a BFS return a path through a co-tenant that is
shorter than the truth.

Edges into a shared space are *claims*, a property of the space itself and shared by every
scene over it, so a search simply includes them -- there is no membership to consult. The
dataset buckets carry a dataset's own spatial facts: its levels, lenses, physical spaces
and its derivations.

The exception is **lineage**. A derived dataset -- a deconvolution, a projection, a resample
-- does not sit anywhere on its own account: it sits where the data it was computed from
sits, and the walk to a space runs through that parent's lens, array and intrinsic systems.
Those edges live in the parent's bucket, so the search closes over the chain above a seeded
dataset. A parent is not an unrelated dataset; it is where the pixels came from.
"""

from typing import Iterable

from django.db.models import Q

from core import models
from core.logic import graph as graph_logic

#: Where the per-request root-edge memo lives on the context's loader store.
_ROOT_EDGE_KEY = "space_root_edges"

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
    not by living in its grid -- and :meth:`EdgeUniverse.dataset_id_of` resolves that from
    the anchor edges the universe fetched up front.
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
    projection, a resample stating where its pixels came from. An edge into a shared space
    leaves the dataset too, but it lands nowhere -- a world belongs to no dataset -- so a
    registration is not mistaken for a lineage.

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
        edges.select_related("input", "output").prefetch_related("children", *EDGE_AXIS_PREFETCH)
    )


def dataset_buckets(seed_ids: set[int]) -> tuple[dict[int, list["models.Transformation"]], dict[int, set[int]], set[int]]:
    """Every seeded dataset's own fact edges, closed over its derivation lineage.

    Returns ``(edges by dataset, parents by dataset, every dataset id reached)``.

    A derived dataset's placement is not its own fact: it sits where the data it was
    computed from sits, and the walk to a space runs through its source's lens, array and
    intrinsic systems. Those edges live in the source's bucket, so without closing over the
    lineage a search dead-ends the moment it crosses the derivation edge.

    One query per lineage *generation*, not per dataset, which is what keeps a universe flat
    in its source count.

    **A bucket is not a function of its dataset**, which is why nothing caches these across
    universes. An edge is filed under `_edge_dataset_id` and then dropped unless *that*
    dataset is in the current batch, so a space co-tenanted by A and B files an edge out of
    it under A -- and seeding with B alone drops that edge entirely. Sharing a bucket
    between two differently-seeded universes would silently widen one of their searches.
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


def _fetch_collection_edges(system_ids: set[int]) -> dict[int, "models.Transformation"]:
    """The derivation edge out of each collection system, keyed by system.

    Optional per collection: a mesh in some absolute space is derived from no dataset and
    simply has none. One query for the whole set, before anything asks -- resolving them a
    system at a time is a query per layer, and flatness in the source count is the point.
    """
    if not system_ids:
        return {}

    edges = (
        models.Transformation.objects.filter(input_id__in=system_ids, parent__isnull=True)
        .select_related("input", "output")
        .prefetch_related("children", *EDGE_AXIS_PREFETCH)
        .order_by("pk")
    )

    collection_edges: dict[int, models.Transformation] = {}
    for edge in edges:
        collection_edges.setdefault(edge.input_id, edge)
    return collection_edges


def root_edges_of(space: "models.CoordinateSystem | None", *, organization=None, loaders: dict | None = None) -> list["models.Transformation"]:
    """Every top-level edge touching this space, in both directions.

    Both directions because a registration authored backwards (space -> source) must degrade
    to an inverted step rather than to an unreachable space; top-level only because a
    wrapper's children are steps *within* an edge, not edges of the graph.

    ``organization=None`` means the space's own truth, and that is the answer a scene wants:
    ``CoordinateSystem.registrations`` returns exactly these rows unscoped, so filtering here
    would make ``Layer.pathToWorld`` search a *narrower* set than the field documented as its
    universe. An organization is passed only by a caller that hands whole *containers* back
    to a client and so must not surface a co-tenant's -- see
    :class:`core.logic.space_graph.SpaceGraph`. Both of those are deliberate; neither is the
    other one's bug.

    The memo carries the organization in its key for the same reason: two callers scoping
    differently are not fetching the same rows and must not share one.
    """
    if space is None:
        return []

    key = (space.pk, organization.pk if organization is not None else None)
    memo = loaders.setdefault(_ROOT_EDGE_KEY, {}) if loaders is not None else None
    if memo is not None and key in memo:
        return memo[key]

    query = models.Transformation.objects.filter(Q(output=space) | Q(input=space), parent__isnull=True)
    if organization is not None:
        query = query.filter(organization=organization)
    edges = list(query.select_related("input", "output").prefetch_related("children", *EDGE_AXIS_PREFETCH))

    if memo is not None:
        memo[key] = edges
    return edges


class EdgeUniverse:
    """The edges a search rooted at one space may cross: the space's own, plus its seeds' facts.

    **The seed set is a parameter, and it stays one.** A scene seeds from its two layers; a
    shared space seeds from every resident of every space placeable in it, which can be
    hundreds. Unifying the seeding would make a two-layer scene pay for a hundred-tile stage.

    **Two seed forms, and both are needed.** ``seed_systems`` is for a caller that knows the
    *spaces* it cares about and must be told which datasets live in them; ``seed_datasets``
    is for one that already has the dataset ids off rows in hand. They are not
    interchangeable: :func:`core.logic.graph.residence_map` maps a space to one resident, so
    a hundred tiles sharing one stage space seed a hundred datasets through ``seed_datasets``
    and exactly one through ``seed_systems``.
    """

    def __init__(
        self,
        space: "models.CoordinateSystem | None",
        *,
        organization=None,
        seed_systems: Iterable[int] = (),
        seed_datasets: Iterable[int] = (),
        collection_systems: Iterable[int] = (),
        loaders: dict | None = None,
    ) -> None:
        self.space = space
        self.organization = organization
        # Sets, not the caller's iterables: `seed_systems` is read twice below, and an empty
        # generator is truthy -- which would turn the collection-edge guard into an `IN ()`.
        seed_systems = set(seed_systems)
        collection_systems = set(collection_systems)

        self.root_edges = root_edges_of(space, organization=organization, loaders=loaders)

        # Empty until the seeds resolve, and that order is load-bearing rather than tidy:
        # `residence` widens over the buckets, and the seeds are read *through* `residence`.
        self.dataset_edges: dict[int, list[models.Transformation]] = {}
        self.derived_from: dict[int, set[int]] = {}
        self.dataset_ids: set[int] = set()

        self._residence: dict[int, int] = graph_logic.residence_map(seed_systems) if seed_systems else {}
        self._residence_covers: set[int] = set(seed_systems)

        # A collection (meshes, features, tables) owns its coordinate system rather than
        # borrowing its dataset's, so nothing on that system says which dataset it came from
        # -- the derivation edge does. Fetched before the seeds, because a collection seed
        # resolves to its dataset only through this edge.
        self.collection_edges = _fetch_collection_edges(collection_systems)
        collection_residence = graph_logic.residence_map({edge.output_id for edge in self.collection_edges.values() if edge.output_id})
        self.collection_source = {system_id: _system_dataset_id(edge.output, collection_residence) for system_id, edge in self.collection_edges.items()}

        seeds = set(seed_datasets)
        seeds |= {dataset_id for system_id in seed_systems if (dataset_id := self.dataset_id_of(system_id)) is not None}
        self.dataset_edges, self.derived_from, self.dataset_ids = dataset_buckets(seeds)

        # A collection's derivation edge leaves the collection's own system, which no dataset
        # owns, so `fetch_dataset_edges` (which filters on the input system's dataset FKs)
        # never sees it. File it with the dataset it lands in, or a mesh search starts on a
        # system with no edges at all and can go nowhere.
        for system_id, edge in self.collection_edges.items():
            dataset_id = self.collection_source.get(system_id)
            if dataset_id in self.dataset_edges:
                self.dataset_edges[dataset_id].append(edge)

        self._adjacency_cache: dict[int | None, dict] = {}

    @property
    def residence(self) -> dict[int, int]:
        """``{space: dataset}`` over the spaces this universe's searchable edges touch.

        Widened once, the first time anyone asks about a space the seed map did not cover --
        three queries for the whole remainder, never one per space. Moving the widening
        inside a per-system loop is exactly how this becomes a query per layer again;
        ``_residence_covers`` is what forbids it.

        Over the root edges and the buckets, and deliberately not ``collection_edges``: a
        collection's own system is tied to a dataset by an *edge*, not by anything living in
        it, so :meth:`dataset_id_of` must fall through to ``collection_source`` for it.
        """
        touched = {edge.input_id for edges in self.dataset_edges.values() for edge in edges if edge.input_id}
        touched |= {edge.output_id for edges in self.dataset_edges.values() for edge in edges if edge.output_id}
        touched |= {edge.input_id for edge in self.root_edges if edge.input_id}
        touched |= {edge.output_id for edge in self.root_edges if edge.output_id}

        missing = touched - self._residence_covers
        if missing:
            self._residence.update(graph_logic.residence_map(missing))
            self._residence_covers |= missing
        return self._residence

    def dataset_id_of(self, system_id: int | None) -> int | None:
        """The dataset whose data lives in a space, or -- for a collection's own -- by derivation edge."""
        if system_id is None:
            return None
        owned = self.residence.get(system_id)
        if owned is not None:
            return owned
        return self.collection_source.get(system_id)

    def lineage(self, dataset_id: int) -> list[int]:
        """A dataset and every dataset it was derived from, transitively, nearest first.

        A fan, not a chain: ``derived_from`` records every parent, because a fusion derives
        from several datasets and places through whichever of them is registered. ``sorted``
        makes the order deterministic, and ``seen`` makes a cycle -- nonsense, but it must not
        hang the request -- terminate.
        """
        chain = [dataset_id]
        seen = {dataset_id}
        frontier = [dataset_id]
        while frontier:
            next_frontier: list[int] = []
            for current in frontier:
                for source in sorted(self.derived_from.get(current, ())):
                    if source in seen:
                        continue
                    seen.add(source)
                    chain.append(source)
                    next_frontier.append(source)
            frontier = next_frontier
        return chain

    def adjacency(self, dataset_id: int | None) -> dict[int, list[tuple["models.Transformation", bool, int]]]:
        """The searchable universe for one dataset: its lineage's facts plus this space's claims.

        The partition holds where it matters. An *unrelated* dataset's edges still never
        enter this search -- that is what stops a BFS wandering out through a co-tenant and
        returning a path shorter than the truth. But a dataset this one was derived from is
        not unrelated: the path to the space runs straight through it.
        """
        if dataset_id in self._adjacency_cache:
            return self._adjacency_cache[dataset_id]

        edges = list(self.root_edges)
        if dataset_id is not None:
            for ancestor_id in self.lineage(dataset_id):
                edges += self.dataset_edges.get(ancestor_id, [])

        adjacency = graph_logic.adjacency_of(edges)
        self._adjacency_cache[dataset_id] = adjacency
        return adjacency
