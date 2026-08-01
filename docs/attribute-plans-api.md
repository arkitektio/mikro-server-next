# Attribute plans: what is under this pixel?

A label mask's pixels are the map into a table of objects — that is what a `FIELD` edge
records (`docs/field-transforms-api.md`). This guide is the read side: how a client asks
*"what is under this pixel, and what do we know about it?"* and answers it **itself**, with
DuckDB and zarr, using a plan the server hands it once.

The contract in one sentence:

> **The server returns a plan; a worker executes it.** The plan names the array to sample,
> the axes to sample it on, the parquet to query and the columns to select — and never a
> value, a credential, or a coordinate.

Why no coordinate? Because "sample the mask, that gives `i`; look up `i` in that parquet"
is the same plan for **every** pixel. Fetch it once, cache it, and run it per hover,
locally, with zero round-trips — against mask chunks you are already rendering. A
coord-bearing query would be one request per pixel and could never compete.

## The cast

A timelapse `(t, c, y, x)`; a per-frame instance mask `(t, y, x)` whose values are object
ids; and two measurement tables hanging off the same mask:

    mask (t,y,x)
      ├── FIELD, field = self ──> nuclei morphology (t, i)        area, mean_intensity
      └── FIELD, field = self ──> nuclei intensity (t, label_id)  integrated

Note the differently named produced axes — `i` and `label_id`. That is allowed, per-edge,
and it is why you always zip the sampled value against *the plan's own* names.

## Fetch the plans

```graphql
query Plans($system: ID!) {          # $system = the mask's intrinsic system
  attributePlans(system: $system) {
    edge { id version }              # the cache key: refetch when either changes
    table { id name }
    sample {
      system { id }                  # the array being sampled (== $system for a mask)
      store { id }                   # ask it for an accessGrant to read chunks
      consumes                       # ["y","x"]  index the array here
      produces                       # ["i"]      what the value means, per-edge
      passthrough                    # ["t"]      unconsumed axes join the key by name
    }
    lookup {
      store { id }                   # ask it for an accessGrant to read the parquet
      keyColumns { axis column { name dtype } }
      attributes { name dtype references { id } }
      sql                            # parameterized DuckDB, see bind order below
    }
  }
}
```

For the mask above this returns **two** plans (sibling fan-out: one per attached table).
The morphology one, abridged:

```json
{
  "table":  {"name": "nuclei morphology"},
  "sample": {"consumes": ["y", "x"], "produces": ["i"], "passthrough": ["t"]},
  "lookup": {
    "keyColumns": [{"axis": "t", "column": {"name": "t"}},
                   {"axis": "i", "column": {"name": "i"}}],
    "attributes": [{"name": "area"}, {"name": "mean_intensity"}],
    "sql": "SELECT \"area\", \"mean_intensity\" FROM read_parquet(?) WHERE \"t\" = ? AND \"i\" = ?"
  }
}
```

## Execute it: the hover loop (browser)

You are already rendering the mask, so the sample step costs nothing — read the value from
the chunk on screen. Then bind the lookup **by axis name**, never by position in your own
head:

```js
const plans = await fetchPlansOnce(maskSystemId);     // cache against edge {id, version}

function onHover(t, y, x) {
  for (const plan of plans) {
    const value = renderedMask.valueAt(t, y, x);      // SampleStep, free: your own chunk
    if (value === 0) continue;                        // background

    const held = { t, [plan.sample.produces[0]]: value };
    const params = [
      parquetUrlFor(plan.lookup.store),               // read_parquet(?) binds FIRST
      ...plan.lookup.keyColumns.map((k) => held[k.axis]),
    ];
    const rows = await duck.query(plan.lookup.sql, params);
    show(plan.table.name, rows);                      // rows, PLURAL -- see below
  }
}
```

## Execute it: a headless worker (Python)

A worker that is not rendering anything runs both halves itself, with credentials from the
stores' own access grants — a plan never carries them:

```python
import duckdb
import zarr

# -- SampleStep: the zarr half -------------------------------------------------
grant = request_zarr_access(plan.sample.store)        # scoped, temporary S3 credentials
mask = zarr.open(mount(grant), mode="r")              # axis order = sample.system's axes
value = int(mask[t, y, x])                            # consumes ["y","x"], t passes through

# -- LookupStep: the duckdb half -----------------------------------------------
grant = request_parquet_access(plan.lookup.store)
con = duckdb.connect()
con.execute(create_secret_from(grant))

held = {"t": t, plan.sample.produces[0]: value}       # zip against THIS plan's names
params = [grant.url, *[held[k.axis] for k in plan.lookup.key_columns]]
rows = con.execute(plan.lookup.sql, params).fetchall()
```

Three rules a worker must not improvise around:

- **Bind order.** The parquet path/URL first (it is the `read_parquet(?)` argument), then
  the key values in `keyColumns` order. The SQL contains only `?` placeholders —
  identifiers are baked in, quoted, from validated declared columns; values never are.
- **Rows, plural.** `(t, i)` uniqueness is a convention; no unique index backs it. Handle
  zero rows (an id the table never measured) and several (a re-run appended).
- **Per-plan names.** Two sibling edges may name their produced axis differently. Zip the
  sampled value against `produces` of the plan you are executing, never a shared key set.

And one to know about: `read_parquet(?)` as a prepared-statement parameter needs a
reasonably recent DuckDB — pin your worker's version rather than string-formatting the
path in, which would defeat the one place the plan is deliberately parameterized.

## Probing through the graph: hovering the source image

In a scene you rarely hover the mask — you hover the **image**, and the mask is a separate,
derived dataset. Plans are discovered for you: probe the image's system and every plan in
its *fact family* comes back, found through derivation edges (and pyramid levels, lenses,
calibrations — never through a registration: what shares a scene's world does not
correspond by that fact alone). Each discovered plan carries a `path`:

```graphql
query Plans($system: ID!) {          # $system = the IMAGE's intrinsic system this time
  attributePlans(system: $system) {
    table { name }
    path { transformation { id version } inverted }   # empty for locally-rooted plans
    sample { system { id } consumes produces passthrough }
    lookup { sql keyColumns { axis column { name } } }
  }
}
```

For a `(t,c,y,x)` timelapse whose `(t,y,x)` instance mask was derived with the usual
BY_DIMENSION-on-kept-axes edge, the mask's plan arrives with a one-step path — the
derivation edge, `inverted: true` (it is stored mask→image; your probe walks it
backwards). The hover loop gains exactly one line:

```js
function onHover(t, c, y, x) {                       // image-space coordinates
  for (const plan of plans) {
    const p = applyPath(plan.path, { t, c, y, x }); // compose steps in order, inverting
                                                    // the flagged ones -- pathToWorld's
                                                    // contract. Here: drop c, keep t,y,x
    const value = maskChunks.valueAt(p);            // then everything as before
    const held = { ...passthroughOf(plan, p), [plan.sample.produces[0]]: value };
    ...
  }
}
```

Three things to rely on, and one to know:

- **`passthrough` is stated in the plan's own space** (the FIELD edge's input system),
  never yours: the image's `c` will not appear in the mask plan's key.
- **Local plans sort first.** A client that only wants what is rooted where it probed
  filters `path.length === 0` and reads a stable prefix.
- **The cache key grew:** a plan is stale when its FIELD edge *or any path step* is
  deleted or version-bumped — cache against all of their `(id, version)` pairs.
- **Unreachable is honest.** A mask whose derivation drops an axis without naming the kept
  ones (a rank-changing edge), or whose relation is UNMAPPABLE, is simply absent — there
  is no path a worker could compose, so none is invented. `maxDepth` bounds the walk if
  you want only near neighbours.

## The reverse direction needs no plan at all

"Highlight every pixel of the row I clicked" is the same correspondence read the other
way, and the graph refuses to walk it (an object is a *set* of pixels — there is no point
to return). You do not need it walked: the plan already told you the mask's values live on
the table's `i` axis, so the highlight is a predicate on pixels you already have:

```js
highlight = (pixel) => pixel === clickedRow.i;        // a shader, not a query
```

## Caching

A plan names columns and SQL, never values — so the parquet's contents changing does not
stale it (returning new values is the point), and its schema cannot move (a table's store
and columns are written once). The staleness vectors are the **edges**: the FIELD edge the
plan was built from, and every `path` step on the way to it — deleted, or refined with a
`version` bump. Cache plans keyed on the full set of `(id, version)` pairs (the FIELD edge
plus each `path.transformation`); refetch on a miss.

## One hop further: `references`

A returned attribute column may carry a `references`: a declared foreign key stating that
its values identify rows of another table. This is how tracking looks — segmentation
writes the mask and per-frame objects; tracking writes a `tracks` table first, then the
objects table whose `instance_id` column points at it:

```graphql
mutation {
  createTableDataset(input: {
    name: "tracks"
    data: "<parquet store id>"
    columns: [
      {name: "instance_id", dtype: "BIGINT", role: COORDINATE, axisType: INDEX},
      {name: "duration",      dtype: "DOUBLE", role: ATTRIBUTE},
      {name: "mean_velocity", dtype: "DOUBLE", role: ATTRIBUTE}
    ]
  }) { id }
}
```

```graphql
mutation {
  createTableDataset(input: {
    name: "per-frame nuclei"
    data: "<parquet store id>"
    columns: [
      {name: "t",           dtype: "BIGINT", role: COORDINATE, axisType: TIME},
      {name: "i",           dtype: "BIGINT", role: COORDINATE, axisType: INDEX},
      {name: "instance_id", dtype: "BIGINT", role: TRACK_ID, references: "<tracks id>"},
      {name: "area",        dtype: "DOUBLE", role: ATTRIBUTE}
    ]
  }) { id }
}
```

Now the hover answer for pixel value `7` at `t = 5` includes `instance_id = 42`, and the
column's `references` says where `42` means something. Following it is one more lookup you
can write yourself — the target's key column is its single INDEX coordinate column, its
store is on the type:

```sql
SELECT "duration", "mean_velocity" FROM read_parquet(?) WHERE "instance_id" = ?
```

*"What track is under my cursor, and how fast is it moving?"* — two lookups, both local,
zero server round-trips after the plans are cached.

Why is this a column FK and not another `FIELD` edge? Because `FIELD` is the single
crossing from geometry into record-land — it earns its place as a transformation by
consuming spatial axes. Between tables, the relation does no coordinate work; it is a
foreign key, and it lives where schema facts live. (The long version, including why the
FK targets the *table* and never a column: `docs/rfc7-attribute-plans.md`.)

Rules of the road for `references`:

| declaration | outcome |
|---|---|
| a data column (`ID`, `TRACK_ID`, `ATTRIBUTE`, ...) referencing a single-INDEX-keyed table | accepted; readable from both ends (`column.references`, `table.referencedBy`) |
| a `COORDINATE` column with `references` | refused — a coordinate places the row in this table's own space; it does not point elsewhere |
| target keyed `(t, i)` (composite) | refused — a single value cannot identify a row there |
| target with no coordinate columns | refused — its `object` axis is synthetic row enumeration; there is no column to look a value up in |
| deleting a referenced table | refused (`PROTECT`) while any column keys into it — delete the referencing tables first |

## What `attributePlans` refuses, and why

| situation | outcome |
|---|---|
| a `FIELD` edge onto a pixel grid (a warp field's registration) | skipped — a registration, not a dereference; nothing to look up |
| a `FIELD` edge onto the degenerate no-coordinate table | skipped — its synthetic `object` axis has no column to bind in a WHERE |
| the field is a lens-owned system | error — a lens is a selection over a dataset and owns no array; resolving through to the dataset would silently ignore the crop |
| the field's array has no zarr store | error — a plan that cannot name its array is not a plan |
| a map out of a *table* written as a `FIELD` edge | error — that relation is `TableColumn.references`, not geometry |

## Performance note, honestly

The parquet point lookup is a scan: `WHERE i = 7` prunes row groups only if the key is
clustered. Sort your parquet by its key columns (`t`, then the id) at write time and
DuckDB's zone maps do the rest; nothing in the plan can compensate for an unsorted file.
For interactive hover, debounce and reuse one DuckDB connection — the plan is designed so
that everything except the two binds is constant.
