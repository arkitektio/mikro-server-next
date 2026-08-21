# What is here? From a point in world space to everything hanging off it

> Every query below is exercised end-to-end by
> `tests/test_what_is_here.py::test_the_documented_walkthrough_runs_end_to_end`, so this page
> cannot rot into fiction without a red test.

A user clicks in a scene. You have a point in the scene's **world** coordinates and nothing
else. This page is the sequence from there to every record that hangs off that point: which
data is under the cursor, which voxel that is, what the voxel says, what metadata was pinned
at that coordinate, and which row of which parquet describes the object it belongs to.

`docs/attribute-plans-api.md` is the second half of this journey and starts where step 6 ends —
*"you have a pixel in the mask's space"*. This page is how you get a pixel.

The contract in one sentence:

> **The server says where things are and how to read them; your client reads the bytes.**
> No field anywhere returns the value at a coordinate.

That is not an omission. You are already holding the chunk the point falls in — you rendered
it — so the value is a lookup in memory, while a server that answered per point would be one
round-trip per mouse move and could never compete. Everything below is fetched once per scene
and cached; the per-hover work is arithmetic and a chunk read.

## The frames, and which way each hop points

Five coordinate systems stand between a click and a row, and the whole page is about moving
between them:

    world (the scene's)
      ↑  registration edges          Layer.asAffine / pathToWorld     (stored: pixel → world)
    intrinsic (dataset level-0 pixels)
      ↑  level edge                  ImageLayer.levelPaths            (stored: level → intrinsic)
    level grid (the voxels you rendered)
      │  read the array                                               (zarr, your chunk)
      ↓  the value IS the id
    object id
      │  attributePlans lookup                                        (parquet, DuckDB)
      ↓
    a row of measurements

**Every stored edge points up.** The server composes forward only and holds no inverse
anywhere — that is a deliberate property of the coordinate graph, not a missing feature, and
`core/logic/space_graph.py` says so in as many words. Going *down* the diagram, which is what a
click needs, is your matrix inversion. It is the one piece of real math a client owns, and the
rest of this page is mostly about giving you the right matrix to invert.

## 1. What is here at all

Ask the world system what is in view of your point. A click is a degenerate box:

```graphql
query WhatIsHere($world: ID!, $min: [Float!]!, $max: [Float!]!) {
  coordinateSystem(id: $world) {
    inView(region: {min: $min, max: $max}) {
      source { __typename ... on ArrayDataset { id name } }
      system { id }                       # the frame `extent` and `path` are anchored at
      extent { axis min max }
      extentState                         # KNOWN | CONDITIONAL | UNREADABLE | NON_AFFINE | INVERTED
      validity                            # how known this placement is
      invariance                          # what survives the walk
      path { transformation { id } inverted }
      anchors { id coordinates }          # step 5 -- free here, so take it here
    }
  }
}
```

`region` names a **leading prefix** of the system's axes and says nothing about the rest, so a
2D box asked of a `(t,z,y,x)` world constrains `t` and `z` — not `y` and `x`. Order your box by
the world's own `axes` (see step 4 on why axis order is never assumed), and pad it to the
axes you actually mean to constrain.

Two things about the answer are easy to misread:

- **A source with no extent is not a source that is absent.** Refusing to bound something is
  not the same as knowing it is out of view, so it comes back anyway with `extentState` saying
  why: `UNREADABLE` for geometry the server never opens (a mesh collection's vertices, a
  table's rows, both in files it does not read), `NON_AFFINE` for a warp field on the path,
  `INVERTED` for a path walked against its stored direction, and `CONDITIONAL` for a source
  registered per index — see step 2.
- **The extent names only the axes it constrains.** A `(c,y,x)` dataset registered onto the
  `(y,x)` of a `(t,z,y,x)` world is a *slab*, extended along `t` and `z`. There is no entry for
  those axes because nothing measured them, and a zero written there would have culled the
  dataset out of every view it is really in.

## 2. World → pixel

For each layer you care about, ask for its placement as one matrix:

```graphql
query Placement($scene: ID!) {
  scene(id: $scene) {
    layers {
      id
      placement                                    # PLACED | CONDITIONAL | UNREGISTERED | UNMAPPABLE
      asAffine { matrix inputAxes outputAxes total }
    }
  }
}
```

`matrix` is `M × (N+1)`, rows outermost: one row per axis in `outputAxes` (world), one column
per axis in `inputAxes` (the layer's own pixel grid), plus a final translation column. So the
forward map is `world = A · pixel + t`, with `A = matrix[:, :N]` and `t = matrix[:, N]`.

You want the other direction:

```js
// The columns the matrix actually varies with. A column of zeros means this input axis
// does not reach the output at all -- a channel axis that no registration maps -- and it
// must be fixed from elsewhere (the layer's own channel selection) rather than solved for.
const live = plan.inputAxes.filter((_, j) => matrix.some((row) => row[j] !== 0));

// What is left is square exactly when the path constrains as many world axes as it varies
// input axes. Invert that block; everything else you already know.
const A = square(matrix, live, plan.outputAxes);
const t = matrix.map((row) => row[row.length - 1]);
const pixel = solve(A, worldPoint(plan.outputAxes).map((w, i) => w - t[i]));
```

Three shapes to handle, and you will meet all three:

- **`total: true`, square** — the ordinary case. Invert and you are done.
- **`total: false`** — `outputAxes` does not cover the world, because the registration is
  honest about the axes it says nothing about. Your click's coordinates along the missing axes
  are not constrained by this layer at all; whatever the viewer is showing along them (the
  current `t`, the current `z`) is the answer. Pass `strict: true` if you would rather be
  refused than handed a partial map.
- **`asAffine` is null** — there is no single map, and `placement` says which of three
  reasons. `UNREGISTERED` is a gap someone can close by authoring a registration;
  `UNMAPPABLE` is a fact to badge and stop looking (the data's geometry did not survive the
  operation that produced it); `CONDITIONAL` means it *is* registered, per index, and the
  answer depends on a coordinate you have not fixed.

For that last one, pass the coordinate you are standing at and the map resolves:

```graphql
asAffine(at: [{name: "c", value: 2}]) { matrix inputAxes outputAxes total }
```

This is how per-channel chromatic drift and per-timepoint drift correction are carried: one
scoped edge per index, crossed only when a query names that index. Without `at` the server will
not pick one for you, because where the data sits genuinely depends on the channel and choosing
arbitrarily would be a wrong answer rather than a missing one. `placement`, `placementValidity`
and `placementInvariance` all take the same `at`.

## 3. Which pyramid level

You are not rendering level 0 at every zoom, and the level you *are* rendering has its own
grid. Ask for all of them:

```graphql
query Levels($scene: ID!) {
  scene(id: $scene) {
    layers {
      ... on ImageLayer {
        levelPaths {
          dataArray { id level shape chunkShape store { id key } }
          path { transformation { id } inverted }
        }
      }
    }
  }
}
```

Each entry is anchored at **that level's own array system**, not at the dataset's intrinsic
grid. Pick a level by zoom, compose its `path` (inverting the flagged steps), and invert
*that* — not the layer's `asAffine`, which lands you in level-0 pixels and is off by the
pyramid factor everywhere else.

The factors are worth knowing even though you never compute them: a level's scale is the true
ratio of the shapes, not a nominal `2 ** level`. A 36-voxel `z` axis floors to 36, 18, 9, 4, 2,
1 — real factors 1, 2, 4, **9, 18, 36**. A client that assumes powers of two is correct for
`xy` and wrong in `z` from level 3 down.

## 4. Read the voxel

The store hands out its own credentials as a **field**, so the grant comes back with the same
query rather than a separate mutation round-trip:

```graphql
dataArray { store { key bucket accessGrant { accessKey secretKey sessionToken region path expiresIn } } }
```

Then two conventions decide whether you read the right voxel:

**Axis order is the system's, not a convention.** Index the array in `Axis.order` order —
`order` *is* the index into `shape`. Do not reach for `zyx`, and do not reuse whatever your
renderer decided x and y were: render-axis derivation answers a different question (which axis
goes on screen) and the two are allowed to disagree.

```graphql
dataArray { coordinateSystem { axes { name order type unit } } }
```

**The voxel centre is the origin.** Voxel `n` occupies `[n − 0.5, n + 0.5)`, so a continuous
coordinate becomes an index with `Math.round`, not `Math.floor` — flooring puts you half a
voxel off, consistently, in a way that looks like a registration error and is not. The
half-voxel offset a downsample introduces is already baked into the stored level edge, so
composing the path is all the correction you need; applying your own on top double-counts it.

What the value means depends on the layer: an `ImageLayer`'s voxel is an intensity and the
journey ends here. A `LabelLayer`'s voxel is an **object id**, and steps 6 and 7 are about what
that id opens up.

## 5. What metadata was pinned here

Acquisition facts hang off **coordinate anchors**: a set of coordinates, and the spokes
recorded at them. You already have them from step 1 (`SourcePlacement.anchors`), or from
`Lens.activeAnchors` if you are working a lens rather than a region.

```graphql
anchors {
  coordinates                                       # {"c": 0, "t": 5} -- level-0 pixel indices
  microscope { state { stage { x y z } temperature } }
  omeMetadata { metadata }
  valueHistogram { histogram bins min max p1 p99 }
  channelLabel { label }
  lightGraph { graph { elements { __typename } edges { __typename } } }
  phasorHistograms { axis harmonic bins counts profile calibrated }
  phasorCalibrations { axis harmonic phaseOffset modulationFactor reference }
}
```

**Matching is containment, and precedence is yours.** An anchor pins the axes it names and is
*global along every axis it omits*. So for a point at `c=0, t=5`, all three of `{}`, `{"c": 0}`
and `{"c": 0, "t": 5}` match, and the server ranks none of them — `inView` returns every anchor
whose slab overlaps your region, deliberately, because which one wins is a question about your
UI and not about the data. The rule to apply:

```js
const matches = anchors.filter((a) =>
  Object.entries(a.coordinates).every(([axis, v]) => point[axis] === v));
const winner = matches.sort(
  (a, b) => Object.keys(b.coordinates).length - Object.keys(a.coordinates).length)[0];
```

Most specific wins, and per spoke rather than per anchor: a global anchor may carry the light
path while a `{"c": 0}` anchor carries the channel label, and both are the right answer for
their own field. Resolve each spoke down the sorted list and take the first non-null.

Two are **lists** rather than single spokes — `phasorHistograms` and `phasorCalibrations` —
because one anchor may carry a phasor at several harmonics and over several axes, and its
coordinates cannot pin either. Select within the list by `axis` and `harmonic`.

`coordinates` are **level-0 intrinsic pixel indices**. If step 3 put you on level 2, convert
back up before matching, or match on the non-spatial axes only (`c`, `t`), which is what
anchors almost always pin anyway.

## 6. What object is under it, and what is known about it

Your `LabelLayer` voxel gave you an id. From here `docs/attribute-plans-api.md` takes over in
full; the handoff is exactly this:

```graphql
query Plans($system: ID!) { attributePlans(system: $system) { ... } }
```

Probe with the **mask dataset's intrinsic system** and you get its own plans; probe with the
**image's** and the derived mask's plans come back too, each carrying the `path` to walk. Each
plan names an array to sample, the axes to sample it on, and the parquet to query — and takes
no coordinate, which is why one fetch serves every hover.

The one line joining the two pages: the value you read in step 4 binds to the plan's
`sample.produces` name, and the axes you did *not* consume (`t`, typically) join the key by
name through `sample.passthrough`. Zip against the plan's own names, never a shared key set —
two sibling plans over one mask may call the produced axis `i` and `label_id`.

## 7. How much to trust the answer, and when to refetch

Two fields qualify every placement, and neither is stored — both are derived from the path, so
refining one registration moves every layer that looks through it:

- **`placementValidity`** — the weakest edge on the path. `VALIDATED` was checked or derived
  by the server, `MANUAL` was authored, `INFERRED` was read from metadata, `UNKNOWN` is a
  guess. Badge it; do not hide it.
- **`placementInvariance`** — what survives the walk, weakest-first over the path:
  `ISOMETRY ⊂ SIMILARITY ⊂ AFFINE ⊂ DIFFEOMORPHIC ⊂ NONE`. This is the field that decides
  whether a **scalar length in world units means anything** for this layer: a point size, a
  stroke width, a camera zoom are well defined from `SIMILARITY` up and meaningless below it,
  because under an anisotropic map there is no single world unit to denominate them in.

For caching, the staleness vector is always an **edge**, never a value:

| you cached | it goes stale when |
|---|---|
| an `asAffine` matrix, a level path | any `PlacementStep.transformation` on it is deleted or its `version` moves |
| an attribute plan | its FIELD `edge` or any `path` step does — cache against every `(id, version)` pair |
| a bounding box you derived yourself | `coordinateSystem.transformVersion` changes: it counts the writes along the chain to intrinsic |

Parquet contents changing does *not* stale a plan — returning new values is the point, and a
table's store and columns are written once.

## What this path refuses, and why

| situation | what you get |
|---|---|
| a layer over a source nothing registers into the world | `createLayer` refused it at authoring time; `placement` reads `UNREGISTERED` if the registration was deleted afterwards |
| a layer whose data reaches the world only across an `UNMAPPABLE` edge | `placement: UNMAPPABLE` — there is no registration to author, so do not send anyone looking |
| a per-index registration, queried without `at` | `placement: CONDITIONAL`, `asAffine: null`, `extentState: CONDITIONAL` — supply the coordinate |
| a path crossing a warp `FIELD` | `asAffine` errors rather than returning null, naming the edge: there is no closed form to compose |
| a path with a rank-changing or singular step | same — the error names what stopped it |
| an extent asked of a mesh or table source | returned with `extentState: UNREADABLE`; the server does not open those files |

## Performance, honestly

Steps 1–3 are per scene, not per hover: fetch the placements, the level paths and the plans
once, cache them against the edge versions above, and the per-hover cost is an inversion of a
small matrix plus a read from a chunk you already have. Nothing in this path needs a round-trip
after the first.

The one genuine cost is the parquet lookup in step 6, and it is a scan unless the file is
sorted by its key columns — no plan can compensate for that at read time. Debounce hover, reuse
one DuckDB connection, and sort at write time.
