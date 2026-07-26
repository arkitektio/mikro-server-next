# RFC-9: Data lives in a space; a space belongs to nobody

**Status:** Implemented (July 2026). Migrations `0042`/`0043`/`0044`.
**Supersedes:** RFC-6's "one truth per space" — both the collision guard and the
one-registration-per-placement rule — the PHYSICAL kind, and the dataset-owned calibration.
**Breaking:** throughout, deliberately.

## The model

Three concepts, and nothing else:

- a **space** is a node (`CoordinateSystem`);
- a **map** between two spaces is an edge (`Transformation`);
- **data lives in exactly one space**, and says so with a foreign key of its own.

`CoordinateSystem` keeps `name`, `epoch`, `organization`, `creator`, `provenance`. It has no
foreign key to anything: it does not know what lives in it, owns nothing, and carries no
classification. Ask it for `residents` and it answers by looking at who points at it.

## What ownership was doing, and why none of it survived

Seven nullable owner FKs used to point back at the containers. They were carrying three jobs:

**Telling a fact from a claim.** `is_registration_target` was "no owner FK is set", and the
walk kept only edges whose output was not one. But that was a second, lossy encoding of what
`Transformation.validity` already states — a pyramid edge is `VALIDATED` because the server
derived it, an authored alignment is `MANUAL`. To know how far to trust an edge, read the
edge. Checked by inspection before committing to this: **every** consumer of
`is_registration_target`, `fact_edges` and `claim_root` died with them.

**Lifecycle.** A cascade was how "this space is no longer used" got said. Residence says it
directly: a space nothing lives in and no scene composes over is garbage, and the orphan
sweep collects it together with its edges.

**`kind`.** It only ever labelled which container pointed back. The honest question about a
space is what data lives in it, and that is a list, not an enum — so `kind`,
`CoordinateSystemKind` and `isAdoptableWorld` are gone and `residents` replaces them. A space
with no residents is a pure reference frame: a world, an atlas. That is the only distinction
the four-value label was really carrying, and `_UNINHABITED` in `core/logic/graph.py` is the
one place that still needs it.

## What the shape buys

**Two special cases evaporate rather than being ported.** A level-0 `DataArray` and an
unsliced `Lens` used to own *no* system, with a null standing in for "the dataset's own grid"
and a convention explaining it. They now simply live in that grid, pointing at the same node
the dataset does. And a calibration stops being a kind of thing: it is a space with an edge
into it, which is all it ever was.

**Spaces become shareable.** The residence key is a plain `ForeignKey`, not a one-to-one, so a
hundred tiles genuinely acquired in one stage frame can say so — while two unrelated
acquisitions still get their own, because the writer creates one each. Sharing is expressible
without being automatic.

**Creation runs one write each, in dependency order.** Space, then the data that lives in it,
then the edges. The old docstring claimed a container-side key would be a cycle; it never
was — every creation path already ran container → system → edge with the edge written last.

## Performance: invert the question, do not prefetch it

The obvious worry is that every ownership read becomes a reverse lookup. It does not, because
the question changes direction.

Ownership asked *space → data*, which was a local column and becomes a reverse lookup the
moment the key moves. **Residence asks *data → space*, and that is `coordinate_system_id` — a
local column on a row the graph modules already fetch.** A dataset's spaces are the distinct
`coordinate_system_id`s of its dataset row, its `DataArray` rows and its `Lens` rows.

Where a batch genuinely needs space → data, `graph.residence_map(system_ids)` answers for a
whole set in three `IN` queries, flat in the spaces *and* in the residents.
`space_graph` goes further and fetches the **residents** of the candidate spaces directly,
which retired a seven-way `select_related`.

Four per-row reads slipped through the first pass, in `placeable_system_ids_in`,
`_fetch_collection_edges` and `scenes_by_sole_dataset` (twice). Each was a free column read
under ownership and a query under residence. **The query-count tests were the only thing that
caught them** — which is exactly what they exist for, and why they must stay.

## What was given up

Placement no longer has exactly one answer. RFC-6's argument was that *"letting the rival row
in would put the choice back into the walk, which is exactly where it must never live"* — and
that is precisely what this reverses. Claim chains are legal, rival claims are allowed, and a
BFS can reach a space by more than one route.

The replacement is an explicit tie-break rather than a guarantee from the data: fewest hops,
then the strongest weakest-validity, then the lexicographically smallest edge-id sequence.
`pathToWorld` returns the winner and `alternativePaths` exposes the losers, so a rival
registration is visible rather than silently discarded.

**This part is designed but not yet built.** See below.

## Not done

- `all_paths` / `best_path` and `Layer.alternativePaths`: until they exist, the walk returns
  whichever path the BFS finds first, which is deterministic but unstated.
- The scene bootstrap's mirror rule falls back to `calibrated_neighbours`, mirroring only when
  exactly one unit-carrying space is one edge out. `createSceneFromDataset` was to gain an
  explicit `mirror:` argument; it has not.
- The orphan sweep still refuses a space any edge touches, so deleting a container can strand
  a space plus its edges. The policy change to "nothing lives here and no scene roots here,
  and its edges go with it" is not written.
- `CreateADatasetInput.calibration` still has its old name rather than `physicalSpace`.
- ~75 tests still assert the old vocabulary (`kind`, `createCalibration`); the suite is at
  419/494.
