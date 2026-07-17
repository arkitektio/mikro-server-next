# RFC-7: Attribute plans

**Status:** Draft, not implemented.
**Supersedes:** nothing. This is the read side that the FIELD edge
(`docs/field-transforms-api.md`) implies and does not answer.
**Unchanged:** the edge table, the placement walk, `is_traversable` / `_INVERTIBLE_KINDS`,
`coordinateGraph`, and every existing DuckDB path — this adds a query that reads no store.

## The problem: the FIELD edge made a question askable that nothing answers

A `FIELD` edge records that a label mask's pixels *are* the map into a table of objects. So
"what is under this pixel, and what do we know about it?" became a question about the graph
rather than about client convention. Nothing answers it.

The obvious answer executes the chain server-side —
`attributesForCS(coord: {x, y, t}, cs)`: walk to the mask, read `mask[t,y,x] = 7`, look up row
7, return its attributes. Four things say no.

**The server cannot read arrays, and should not learn to.** There is no zarr, numpy, s3fs,
fsspec or tensorstore dependency in this repo. `ZarrStore.fill_info()` reads exactly one file,
`zarr.json`, via boto3 (`datalayer/datalayer.py:214`); no chunk key is ever constructed and no
codec is ever run. Clients get scoped temporary S3 credentials (`requestZarrAccess`,
`datalayer/mutations/zarr.py:22`) and mount the prefix themselves. Evaluating a FIELD
server-side means a new dependency, chunk addressing, decompression and a chunk cache — in
order to re-fetch a pixel **the client already has on screen**, because it is rendering that
mask as a label layer.

**The DuckDB path is degraded, and a new query would inherit all of it.** `core/duck.py:41` —
`get_current_duck()` returns a fresh `DuckLayer()` per call, so the `cached_property`
connection caches nothing: a new `duckdb.connect()` plus a new `CREATE SECRET`, never closed,
on every invocation. The `current_duckdb` ContextVar that `DuckExtension.on_operation` sets
(`mikro_server/schema.py:917`) is never read anywhere — the pooling this file was designed for
was never wired up. `RowFilter.clause` is concatenated raw into SQL
(`core/queries/rows.py:70`) on a connection holding S3 credentials. `Query.rows` returns `[]`
for every row (`core/queries/rows.py:11`, a diverged `parseRow` whose first statement discards
its own argument). `Query.instance_mask_view_label` calls `parquet_store.get_row`, which is
defined nowhere. None of it is covered: `tests/test_table_rows.py:45` mocks DuckDB out because
"the test stack has no DuckDB-reachable object store".

**Parquet has no point-lookup index.** `WHERE i = 7` is a scan. Row-group zone maps prune only
if the key is clustered — plausible for a freshly segmented `i`, not for an `instance_id`
after tracking. DuckDB is an analytical engine; this is an OLTP point lookup.

**And this module already refused this query, in prose.** `MeshCollection`
(`core/models/coords.py:428`) explains why it exposes no `meshes` field:

> "the client asks the datalayer for temporary read credentials and queries the Parquet
> directly (e.g. with DuckDB) ... It deliberately exposes no ``meshes`` field: a paginated
> list would look natural, someone would build a UI on it, and it would end up walking tens of
> millions of Parquet rows through GraphQL to feed a render loop."

Attributes-at-a-pixel is exactly the UI-on-a-GraphQL-parquet-read that paragraph refuses. The
answer is not to argue with it.

## The model: four rules

**Rule 1 — the server returns a plan; a worker executes it.** This is the first rule of
`core/models/coords.py` applied to values instead of geometry: *"Edges are facts, paths are
queries."* The plan names the array to sample, the axes to sample it on, the parquet to query
and the columns to select. A zarr+duckdb worker — in the browser, or anywhere — runs it with
credentials it already has.

**Rule 2 — a plan takes no coordinate.** The steps do not depend on the point: "sample the
mask, that gives `i`; look up `i` in that parquet" is the same plan for every pixel. So a
client fetches it once and executes it per hover, locally, with zero round-trips. A
coord-bearing query would be one request per pixel, and could never beat the client reading
its own already-rendered mask. This is the rule that makes the RFC worth writing: it is not a
concession to purity, it is faster than the alternative it replaces.

**Rule 3 — composition was never the objection.** The real invariant is *never compose **to
world***. `path_in_scene` (`core/logic/graph.py:1967`) concedes its answer is unique under
one-truth-per-space and still refuses to compose, because world is scene-owned. Meanwhile the
server *does* compose at query time when the destination is scene-independent —
`phasor.axis_scale` via `Lens.phasor` (`core/types/adataset.py:638`), justified in
`core/logic/phasor.py` as "real arithmetic [that] belongs on the server rather than in every
client that wants a lifetime". A table's space is scene-independent, so this query would be
*permitted* to compose. It composes nothing anyway, so the rule never comes up — but it should
be recorded that the wall has a door, and that this RFC is not standing outside it.

**Rule 4 — the plan carries its own SQL.** The server emits
`SELECT "area", "mean_intensity" FROM read_parquet(?) WHERE "t" = ? AND "i" = ?` — identifiers
taken from validated `TableColumn` rows and quoted, values as `?` placeholders, never
interpolated. The worker binds and executes. This is what stops Rule 1 from costing every
client a reimplementation, and it is strictly safer than `RowFilter.clause`, which is raw
client SQL on a credentialed connection today.

## The surface

```graphql
attributePlans(system: ID!): [AttributePlan!]!

type AttributePlan {
  edge: FieldTransformation!
  table: TableDataset!
  sample: SampleStep!
  lookup: LookupStep!
}

type SampleStep {                        # zarr worker
  store: ZarrStore!                      # -> accessGrant / presignedUrl already exist
  consumes: [String!]!                   # ["y","x"] in the field system's axis order
  produces: [String!]!                   # ["i"] -- per-edge; siblings may differ
  passthrough: [String!]!                # ["t"] -- axes the edge did not consume
}

type LookupStep {                        # duckdb worker
  store: ParquetStore!                   # -> accessGrant / presignedUrl already exist
  keyColumns: [PlanKeyColumn!]!          # axis name -> column + dtype, in bind order
  attributes: [TableDatasetColumn!]!     # what to SELECT -- never *
  sql: String!                           # parameterized; bind keyColumns in order
}
```

`produces` is per-edge on purpose: two FIELD edges off one mask may name their produced axis
`i` and `label_id`. Zip the sampled value against *that edge's* `output_axes`, never a shared
key set.

**Do not assume one row per point.** `(t, i)` uniqueness is a convention; no unique index backs
it. The worker gets rows, plural.

## The running example

A timelapse `(t,c,y,x)`; a per-frame instance mask `(t,y,x)` whose values are object ids; a
table of per-object measurements keyed `(t, i)`; and a second table of intensity measurements
keyed the same way, hanging off the same mask.

    mask (t,y,x)
      ├── FIELD, field = self ──> objects (t,i)      area, mean_intensity
      └── FIELD, field = self ──> intensity (t,i)    integrated, background

`attributePlans(system: <mask intrinsic>)` returns **two** plans. Each carries one
`SampleStep` — read the mask's level-0 store, consume `(y,x)`, produce `i`, pass `t` through —
and one `LookupStep` naming that table's parquet, its `(t, i)` key columns and its attribute
columns.

The client, which is already rendering that mask, reads `mask[5, 100, 200] = 7` from the chunk
it already has, then runs both lookups with `(t=5, i=7)`. No round-trip, no server-side pixel
read, no composition.

## The walk is one level, and the type system already forces it

The instinct is a BFS over a tree. It is not — and nothing new has to enforce that:

- `assert_edge_rank` refuses the metric kinds (SCALE / TRANSLATION / AFFINE / ROTATION) over an
  INDEX axis, so **an affine edge can never land on a table's index space.** Only a FIELD can.
- FIELD is absent from `_INVERTIBLE_KINDS`, so a table can never reach a sibling table. Fan-out
  exists only while standing on the mask.
- `is_traversable` excludes UNMAPPABLE, so a degenerate measurement table stays correctly
  unreachable — the FIELD/UNMAPPABLE split doing exactly the job it was added for.

So the walk is a filter, not a search:

```python
edges = models.Transformation.objects.filter(
    input=system, parent__isnull=True,
    kind=enums.TransformKindChoices.FIELD.value,
    organization=info.context.request.organization,
).select_related("output__table_dataset").prefetch_related("output__table_dataset__columns")

for edge in edges:
    if edge.output.table_dataset_id is None:
        continue   # a warp-field target: a pixel grid, not a table
```

Filter on **`input`**, not `field`: a self-dereference stores `field` as NULL (read through
`Transformation.effective_field`), and edges that point *at* a warp field via `field` must not
be followed — their outputs are pixel grids, not tables. The `table_dataset_id is None` guard
covers that.

Do **not** reach for `traverse()` (`core/logic/graph.py:1644`): it is deliberately undirected,
and direction is load-bearing here. Write the emission as a loop over one level so that depth
becomes an extension rather than a rewrite.

`SampleStep.store` needs a small resolver: `system.data_array` → that `DataArray.store`;
`system.intrinsic_of` → the level-0 `DataArray.store` (unique per `(dataset, level)`). A
**lens-owned** field system owns no array of its own (`Lens`: "A selection over a dataset.
Nothing else.") — refuse it rather than guess.

`LookupStep.keyColumns` come from `table.columns_by_role(COORDINATE)`, matched by axis name.
That mapping is an invariant rather than a guess: `TableColumn`'s docstring says name, type and
unit on a coordinate column "are the same fact as the derived `Axis`".

## The `value_column` question

Should a FIELD be able to name *which parquet column* is the value, so
`objects(t,i) → tracks(instance_id)` becomes expressible? (Gap 2 of the FIELD work.)

**It does not reintroduce what the FIELD work removed.** The `DISPLACEMENTS` / `COORDINATES`
split restated an *array* property on the edge, where the two could drift apart. *Which column
is the map* is genuinely per-edge: one table can key `instance_id` → tracks and `parent_id` →
lineage. The array cannot say which; only the map can.

**It should be an FK to `TableColumn`, not a name.** A bare column name is `store_id`-in-params
at smaller scale — the exact mistake the FIELD work replaced by making the field a node. An FK
validates existence by construction and cascades.

**The scalar rule already covers it, unchanged.** A table's system cannot declare a
`COORDINATE` / `DISPLACEMENT` value axis (`_COORDINATE_AXIS_TYPES` is SPACE/TIME/INDEX), so a
parquet field has no value axis → scalar → produces exactly one axis. `assert_field_produces`
needs no new branch. That fit is evidence the shape is right.

**null-means-self still holds.** `objects(t,i) --FIELD--> tracks(instance_id)` has
`field == input`, so `field` is null and the column FK carries the rest.

**New validations**, all in `build_registration_edge`: column set → the field's system must be
table-owned, and the column must belong to *that* table; column null + field table-owned →
refuse ("which column?"); column set + field array-owned → refuse ("an array has one value").

**The wart:** zarr sub-selection is a node (a `Lens`); parquet sub-selection would be an edge
field. Asymmetric. A "table lens" would restore the symmetry and is not worth it.

**But it is not a prerequisite, and the reason is sharper than "ship less".** Multi-table
*breadth* — "collect from every attached table" — is **sibling fan-out**: several FIELD edges
sharing one `input` mask, fully expressible today with no new modelling. `value_column` buys
only *depth*. The first increment already returns multiple tables.

## What this deliberately cannot model

- **A pixel read.** The plan says which array and which axes; it never says what is in them.
  The client owns pixels, because the client already has them.
- **An answer.** `attributePlans` returns instructions, never attributes. Anything that wants
  values runs the plan.
- **A scene.** The query is scene-independent by construction, like `coordinateGraph`. The
  moment it takes a `scene:` argument it has become `pathToWorld` with extra steps.
- **Depth > 1**, until `value_column` lands.

## Current gaps

1. **The parquet point lookup is a scan.** The real fix is clustering/sorting on `(t, i)` at
   write time so row-group zone maps prune — a write-path change
   (`core/mutations/table_dataset.py`) plus a docs note so ingest tooling sorts. Nothing in
   this RFC helps.
2. **`core/duck.py` is broken**: leaked connections per call, a dead pooling ContextVar, and a
   hardcoded `ENDPOINT 'minio:9000'` despite settings deriving `AWS_S3_ENDPOINT_URL`. And
   `RowFilter.clause` (`core/queries/rows.py:70`) is an injection sink on a credentialed
   connection. **None are prerequisites — which is the strongest argument for this shape.**
   They remain real bugs and want their own ticket.
3. **`traverse()` does not follow `field` FKs**, so a warp field's array never appears as a node
   in `coordinateGraph`. Arguably a bug the FIELD work introduced by making fields nodes.
4. `core/logic/tables.py`'s `row_values` / `row_count` / `columns` are typed against the
   **legacy** `models.Table`, not `TableDataset`, and `core/queries/rows.py::parseRow` is
   broken — neither is reusable here.

## Open questions

- **Is the SQL string the right call?** It bakes the DuckDB dialect into the server. The stated
  consumer is a duckdb worker, so it fits; a non-duckdb consumer would read `keyColumns` and
  `attributes` and ignore `sql`. Both live on the type, which may be one too many.
- **Should a plan carry the version of the edge it was built from?** Rule 2 tells clients to
  cache it, so the question is what makes a cached plan wrong. Narrower than it first looks: a
  plan names columns and SQL, not values, so the parquet's *contents* changing does not stale
  it — returning new values is the point. Nor can its schema move under it: a table's store
  and its `TableColumn` rows are written once by `create_table_dataset` and by nothing else
  (`update_table_dataset` touches name and description alone). That leaves exactly one vector,
  the **edge** — deleted, or refined with a `version` bump. Putting `edge.version` on the plan
  would let a client tell. Whether that is worth a field, or whether refetching on a miss is
  simpler, is open.
- **Is `attributePlans` the right altitude**, or should `coordinateGraph` simply follow `field`
  FKs (gap 3) and let clients filter? `pathToWorld` existing alongside `coordinateGraph` is the
  precedent for a focused path query — but a precedent is not an argument.

## Verification, when it is built

- The walk is pure over `Transformation` rows — so, **unlike every other parquet path in this
  codebase, it is testable for real**: a plan reads nothing, so there is nothing to mock and no
  object store to be unreachable.
- Cases: sibling fan-out to two tables with differently named produced axes; a FIELD to a warp
  field skipped; an UNMAPPABLE sibling absent; a lens-owned field system refused.
- The SQL builder is a pure `(sql, params)` function → assert it with no database. That is the
  injection regression test.
- Ablate the `table_dataset_id is None` guard and assert a warp-field target starts appearing
  as a bogus plan.
- SDL: assert `type SampleStep` and friends appear, mirroring `tests/test_schema.py:188` — the
  only thing that catches a type silently dropping out of the schema.
