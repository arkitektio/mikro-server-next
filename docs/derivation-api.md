# Recording where data came from: two call sequences

A derivation is one edge of the coordinate graph — *this data's space, and how it relates to
the space it was computed from* — and it runs between any two **containers**: an array
dataset, a table dataset, a mesh collection, an annotation collection. Not only between two
images, which is all it could express before.

Two sequences, chosen because they run in opposite directions and answer the two questions
the model has to keep apart:

| | direction | the edge | what it buys |
|---|---|---|---|
| **A. SMLM** | table → image | a real `SCALE` | the reconstruction inherits the table's placement |
| **B. Segmentation** | image → mask → table | `BY_DIMENSION`, then `UNMAPPABLE` | the lineage is recorded; no geometry is claimed |

The rule that separates them, and the one thing to take away:

> **Naming a source is not the same as claiming a map.** An omitted `transform` writes an
> `UNMAPPABLE` edge: the lineage is on record and nothing is asserted about where the data
> sits. Placement is inherited only across a transform you state.

That default is deliberate and it is the opposite of what you may expect. A fabricated
identity would lie whenever the units differ, and it would outrank a real edge in the
placement walk — so the server never invents one.

## The shape of `derivedFrom`

Every creator takes the same list. It is a discriminated union: `kind` says which *sort of
source* you are naming, and only that member's id field is read.

```graphql
derivedFrom: [{
  kind: TABLE_DATASET            # LENS | DATASET | TABLE_DATASET
                                 # MESH_COLLECTION | ANNOTATION_COLLECTION | COORDINATE_SYSTEM
  tableDataset: "<id>"           # the field the kind selects; any other is rejected
  transform: {kind: SCALE, scale: [10.0, 10.0]}   # omit for UNMAPPABLE
  valueRelation: TRANSFORMED     # IDENTICAL | TRANSFORMED | CATEGORIZED
}]
```

Two fields, two orthogonal statements. `transform` says **where the data sits**;
`valueRelation` says **what happened to the numbers**. A threshold is spatially `IDENTITY`
with `CATEGORIZED` values; a crop is a `TRANSLATION` with `IDENTICAL` ones.

**The order is the priority.** The first entry is the primary parent — the one that places
this data. A fusion names several; the rest are recorded facts that no placement walk
crosses. An `UNMAPPABLE` first entry with a mappable one behind it is refused, because the
walks would take the primary and stop while a workable parent sat unused.

---

# A. An SMLM localization table, and the image reconstructed from it

## 1. The table

Its coordinate columns are what make it more than rows. Declared as `COORDINATE` with an
`axisType` and a `unit`, they become the **axes of a metric space** the table owns — so a
localization table is a placeable thing, not a bag of numbers.

```graphql
mutation {
  createTableDataset(input: {
    name: "locs"
    data: "<parquet store id>"          # from requestParquetUpload
    columns: [
      {name: "y", dtype: "DOUBLE", role: COORDINATE, axisType: SPACE, unit: "nanometer"},
      {name: "x", dtype: "DOUBLE", role: COORDINATE, axisType: SPACE, unit: "nanometer"},
      {name: "photons",   dtype: "DOUBLE"},
      {name: "precision", dtype: "DOUBLE"}
    ]
  }) {
    id
    coordinateSystem { id axes { name type unit } }   # you need this id in step 3
  }
}
```

The spatial columns must be **all calibrated or all pixel-index** — a half-calibrated space
composes wrongly into one matrix, so it is refused rather than stored. Declare the axes in
type order (time, then channel and custom, then space); the order is enforced, because
`resolve_render_axes` reads x/y/z off *position* and an out-of-order declaration renders
wrong rather than failing.

## 2. The reconstruction

Render the localizations into a voxel grid and ingest it as an ordinary array dataset — with
`derivedFrom` naming the **table**.

The table is in nanometres and the render is in pixels, so the edge is a real `SCALE`: at a
10 nm pixel, one pixel per ten nanometres.

```graphql
mutation {
  createADataset(input: {
    name: "reconstruction"
    data: "<zarr store id>"
    scales: []
    axes: [
      {name: "z", type: SPACE},
      {name: "y", type: SPACE},
      {name: "x", type: SPACE}
    ]
    derivedFrom: [{
      kind: TABLE_DATASET
      tableDataset: "<locs id>"
      transform: {kind: SCALE, scale: [10.0, 10.0, 10.0]}
      valueRelation: TRANSFORMED       # counts, not the localizations themselves
    }]
  }) { id intrinsicSystem { id } }
}
```

> **A rank note.** `SCALE` carries one number per input axis and lowers to a square matrix,
> so it relates spaces of **equal rank**. A 3-D render off a 2-D table is not a `SCALE` — it
> is a `BY_DIMENSION` naming the axes it acts on:
>
> ```graphql
> transform: {
>   kind: BY_DIMENSION
>   inputAxes: ["y", "x"], outputAxes: ["y", "x"]
>   scale: [10.0, 10.0]
> }
> ```
>
> which says nothing about `z` — correct, because a 2-D table constrains nothing along it.

## 3. Place the table, and the image comes along

Register the **table** into the world once. The reconstruction inherits it, because its
derivation is mappable and the placement walk crosses it.

```graphql
mutation {
  createCoordinateSystem(input: {
    name: "slide"
    axes: [
      {name: "y", type: SPACE, unit: "micrometer"},
      {name: "x", type: SPACE, unit: "micrometer"}
    ]
    registrations: [{
      tableDataset: "<locs id>"
      transform: {kind: SCALE, scale: [0.001, 0.001]}   # nm -> µm
      validity: VALIDATED
    }]
  }) { id }
}
```

A layer over the reconstruction now reports `placement: PLACED`, with a `pathToWorld`
running through the table — and refining the table's registration moves the image with it,
because there is one copy of the fact.

**Register the table, not the render.** Registering both writes two independent claims that
can drift; the derivation is what ties them together, and it is already recorded.

---

# B. An image, its segmentation, and a table of measurements

The dereference half of this — the `FIELD` edge that makes the mask's pixels *the map* into
the table — is `docs/field-transforms-api.md`. This is the provenance half, and the two are
complementary: `FIELD` says which space the ids live in, `derivedFrom` says where the data
came from.

## 1. The stack, and a lens over it

```graphql
mutation {
  createADataset(input: {
    name: "raw"
    data: "<zarr store id>"
    scales: []
    axes: [
      {name: "c", type: CHANNEL},
      {name: "y", type: SPACE},
      {name: "x", type: SPACE}
    ]
  }) { id intrinsicSystem { id } }
}

mutation { createLens(input: {dataset: "<raw id>", slices: []}) { id } }
```

Name the **lens** rather than the dataset when there is one: a lens is a selection, and its
own edge back to the dataset already carries the crop, so pointing at it gets the rest of
the chain for free. `kind: DATASET` is the shorthand for "the whole grid, and I have no lens
worth minting".

## 2. The segmentation

It drops `c`, so the map is `BY_DIMENSION` — name the axes you keep. `IDENTITY` is refused
the moment the axis names differ: a rank change wearing an identity's clothes.

```graphql
mutation {
  createADataset(input: {
    name: "nuclei labels"
    data: "<zarr store id>"
    scales: []
    axes: [{name: "y", type: SPACE}, {name: "x", type: SPACE}]
    derivedFrom: [{
      kind: LENS
      lens: "<raw lens id>"
      transform: {kind: BY_DIMENSION, inputAxes: ["y", "x"], outputAxes: ["y", "x"]}
      valueRelation: CATEGORIZED       # the values became labels
    }]
  }) { id intrinsicSystem { id } }
}
```

`CATEGORIZED` earns its keep twice: it is the premise the `FIELD` dereference builds on, and
it is the one thing that makes a bootstrapped scene render this as a **label map** — nothing
about an array's structure distinguishes a segmentation from an intensity image.

The mask is placed wherever the raw stack is, with no registration of its own.

## 3. The attributes table

One row per object, and **no coordinate columns**: the rows enumerate objects rather than
sitting anywhere. The table's space is then a single `INDEX` axis.

```graphql
mutation {
  createTableDataset(input: {
    name: "nuclei morphology"
    data: "<parquet store id>"
    columns: [
      {name: "i",              dtype: "BIGINT", role: COORDINATE, axisType: INDEX},
      {name: "area",           dtype: "DOUBLE"},
      {name: "mean_intensity", dtype: "DOUBLE"}
    ]
    derivedFrom: [{
      kind: DATASET
      dataset: "<mask id>"
      valueRelation: TRANSFORMED       # measurements of the mask, not the mask's numbers
    }]                                 # no transform: UNMAPPABLE, and that is the truth
  }) { id coordinateSystem { id axes { name type } } }
}
```

**The omitted `transform` is the whole point here.** The rows are per-object measurements;
they are not anywhere. `UNMAPPABLE` records that this table came from that mask *and* that
its geometry did not survive — which is strictly more than saying nothing, and strictly more
honest than an identity.

An `INDEX` coordinate column carries **no unit**: there is nothing to measure between object
3 and object 4. Try to relate an index space with a metric kind and `assert_edge_rank`
refuses it, naming the axis — an affine edge can never land on a table's index space, which
is what "tables are leaves" means in practice.

## 4. The dereference

Add the `FIELD` edge so the mask's pixels *are* the lookup into the table. That is
`docs/field-transforms-api.md` step 4, unchanged by any of this:

```graphql
mutation {
  createTransformation(input: {
    input:  "<mask intrinsic system id>"
    output: "<table coordinate system id>"
    transform: {
      kind: FIELD
      field: "<mask intrinsic system id>"     # the mask's own pixels are the map
      inputAxes: ["y", "x"]
      outputAxes: ["i"]
    }
  }) { id }
}
```

---

# Reading it back

`derivedFrom` on any container returns the edges, one hop up. `derivedResidents` on a
dataset returns everything computed from it, one hop down — including the tables and
collections that `derivedDatasets`, which stays honestly about datasets, does not list.

For the whole component, walk it:

```graphql
query Lineage($system: ID!) {
  lineageGraph(coordinateSystem: $system) {
    nodes {
      __typename
      ... on ADataset { name }
      ... on TableDataset { name }
    }
    edges { id kind valueRelation input { id } output { id } }
  }
}
```

Root it at any container's coordinate system — `intrinsicSystem.id` for a dataset,
`coordinateSystem.id` for a table or collection. It walks **derivation edges only**, in both
directions, so from the mask in sequence B you get the raw stack above it and the morphology
table below it. `coordinateGraph` is the wrong tool here: it crosses every edge touching a
space, so one registration drags in every other dataset registered into the same world.

`lineageGraph` is **kind-blind** — the `UNMAPPABLE` hop to the measurement table is in it,
and has to be, or the chain breaks exactly where it gets interesting. Filter on `edges.kind`
for the sub-chain that actually places things.

Two kinds of edge are never in it, and for the same reason — neither says where anything
came from:

- **a registration**, which says where data was *put*. It points into a world, and a world
  belongs to no container, so it is not a lineage edge by construction rather than by filter.
- **a `FIELD`**, which says the mask's pixels *are* the lookup into the table. Left in, the
  mask in sequence B would report the table as something it was *derived from* — backwards.
  The table's provenance is its own `derivedFrom`, which is the separate `UNMAPPABLE` edge
  step 3 wrote. This is the same line RFC-7 draws for the attribute-plan walk: *FIELD edges
  are payload, never connectivity.*

So in sequence B the mask and the morphology table are joined by **two** edges that say
different things, and only one of them is lineage.

# What is refused, and why

| you write | you get |
|---|---|
| `derivedFrom` with no `kind` | the schema refuses it: `kind` is required and each member requires its own id |
| `{kind: LENS, tableDataset: "3"}` | *A LENS derivation requires `lens`* — the member reads its own field and no other |
| `SCALE` between spaces of different rank | refused: one number per input axis lowers to a square matrix. Use `BY_DIMENSION` |
| a metric kind onto an `INDEX` axis | refused, naming the axis: object 3 × 2 is not object 6 |
| `[{kind: LENS, lens: "1"}, {kind: LENS, lens: "2", transform: {kind: IDENTITY}}]` | refused: the first entry is the primary parent and is `UNMAPPABLE` by default, so it would hide the mappable one behind it. State its transform |
| the same source twice | refused: one entry per source; its transform already says everything |

# Where this is pinned

`tests/test_cross_container_derivation.py` runs both sequences through the real mutations,
including `test_the_documented_sequences_run_end_to_end`, which executes the calls on this
page. A doc that names a field the schema does not have is worse than no doc — it reads as
verified — so the sequences cannot rot into fiction without a red test.
