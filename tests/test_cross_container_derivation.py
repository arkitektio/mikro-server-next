"""A derivation runs between *containers*, whichever kind they are.

"This data was computed from that data" is one edge, and it was only ever expressible
between two array datasets: `createADataset(derivedFrom:)` named a `Lens` and nothing else,
while the three collections named a bare `coordinateSystem` -- so a table could not say
which image its rows were segmented out of without the caller looking that image's *system*
id up by hand, and an image reconstructed from a table could not say so at all.

Two directions matter here, and they are not symmetric:

- **image -> table.** An instance mask's per-object measurements. The table's rows enumerate
  objects rather than sitting anywhere, so its space is an INDEX axis and the only honest
  edge is UNMAPPABLE -- which is exactly what an omitted `transform` now means.
- **table -> image.** An SMLM localization table's coordinate columns declare a *metric*
  space in nanometres, so a reconstruction rendered from it relates to it by a real SCALE,
  and inherits the table's placement the way a derived image inherits its parent's.

The second is what forced the placement machinery to be keyed by container rather than by
dataset: keyed by dataset, a table had no key to be a parent under, so the edge was not
refused -- it was silently dropped from `derivedFrom` and never walked.
"""

import re

import pytest
from asgiref.sync import sync_to_async
from kante.context import HttpContext

from core import enums, models
from core.inputs.coords import derived_from_union_types
from mikro_server.schema import schema
from tests import seed

CREATE_TABLE = """
mutation Create($input: CreateTableDatasetInput!) {
  createTableDataset(input: $input) {
    id
    coordinateSystem { id axes { name type unit } }
    derivedFrom { id kind valueRelation output { id residents { __typename } } }
  }
}
"""

DATASET_LINEAGE = """
query Lineage($id: ID!) {
  adataset(id: $id) {
    id
    derivedFrom { id kind output { id residents { __typename ... on TableDataset { name } } } }
  }
}
"""

PLACEMENT = """
query Placement($id: ID!) {
  scene(id: $id) {
    layers { id placement pathToWorld { inverted transformation { id kind } } }
  }
}
"""


async def _parquet(ctx: HttpContext, key: str) -> models.ParquetStore:
    return await sync_to_async(models.ParquetStore.objects.create)(path=f"s3://parquet/{key}", bucket="parquet", key=key, organization=ctx.request.organization)


async def _table(ctx: HttpContext, name: str, *, columns: list, derived_from: list | None = None) -> dict:
    """A table dataset through the real mutation."""
    store = await _parquet(ctx, f"table-{name}")
    result = await schema.execute(
        CREATE_TABLE,
        context_value=ctx,
        variable_values={"input": {"name": name, "data": str(store.pk), "columns": columns, "derivedFrom": derived_from or []}},
    )
    assert not result.errors, result.errors
    return result.data["createTableDataset"]


_MEASUREMENT_COLUMNS = [
    {"name": "object", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"},
    {"name": "area", "dtype": "DOUBLE"},
]

_LOCALIZATION_COLUMNS = [
    {"name": "y", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE", "unit": "nanometer"},
    {"name": "x", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE", "unit": "nanometer"},
]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_measurement_table_says_which_image_it_was_measured_from(authenticated_context: HttpContext) -> None:
    """image -> table, naming the *container* rather than hunting for its system id.

    The transform is omitted, so the edge is UNMAPPABLE: the rows are per-object
    measurements and are not anywhere. That is the lineage recorded and no geometry
    claimed, which is the whole "naming a source is not the same as claiming a map" rule.
    """
    mask = await seed.create_adataset(authenticated_context, "InstanceMask", axes=seed.YX_AXES, shapes=[[64, 64]])

    table = await _table(
        authenticated_context,
        "Objects",
        columns=_MEASUREMENT_COLUMNS,
        derived_from=[{"kind": "DATASET", "dataset": str(mask.pk), "valueRelation": "TRANSFORMED"}],
    )

    assert [axis["name"] for axis in table["coordinateSystem"]["axes"]] == ["object"], "rows enumerate objects; they are not placed"
    assert len(table["derivedFrom"]) == 1
    edge = table["derivedFrom"][0]
    assert edge["kind"] == "UNMAPPABLE", "an omitted transform records the lineage and claims no geometry"
    assert edge["valueRelation"] == "TRANSFORMED"
    assert [r["__typename"] for r in edge["output"]["residents"]] == ["ADataset", "DataArray"], "the far end is the image the rows were measured from"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_image_says_which_table_it_was_reconstructed_from(authenticated_context: HttpContext) -> None:
    """table -> image: the direction that was previously unexpressible in either sense.

    Not merely unsupported -- **silently dropped**. `derivation_edges` resolved an edge's
    output to an `ADataset` and discarded the edge when it could not, so this assertion
    fails on the old code by coming back with an empty list rather than an error.
    """
    table = await _table(authenticated_context, "Localizations", columns=_LOCALIZATION_COLUMNS)
    render = await _reconstruction(authenticated_context, table, transform={"kind": "SCALE", "scale": [10.0, 10.0]})

    result = await schema.execute(DATASET_LINEAGE, context_value=authenticated_context, variable_values={"id": str(render)})
    assert not result.errors, result.errors

    parents = result.data["adataset"]["derivedFrom"]
    assert len(parents) == 1, "the table parent must not be dropped"
    assert parents[0]["kind"] == "SCALE"
    residents = parents[0]["output"]["residents"]
    assert [r["__typename"] for r in residents] == ["TableDataset"] and residents[0]["name"] == "Localizations"


async def _reconstruction(ctx: HttpContext, table: dict, *, transform: dict) -> str:
    """An array dataset derived from a table, through the real ingest mutation."""
    from unittest.mock import patch

    store = await sync_to_async(models.ZarrStore.objects.create)(
        path="s3://zarr/render",
        bucket="zarr",
        key="render",
        shape=[64, 64],
        chunks=[64, 64],
        version="3",
        dtype="uint8",
        populated=True,
        organization=ctx.request.organization,
    )
    with patch("datalayer.models.ZarrStore.fill_info", return_value=None):
        result = await schema.execute(
            "mutation D($input: CreateADatasetInput!) { createADataset(input: $input) { id } }",
            context_value=ctx,
            variable_values={
                "input": {
                    "name": "Reconstruction",
                    "data": str(store.id),
                    "scales": [],
                    "axes": [{"name": "y", "type": "SPACE"}, {"name": "x", "type": "SPACE"}],
                    "derivedFrom": [{"kind": "TABLE_DATASET", "tableDataset": table["id"], "transform": transform, "valueRelation": "TRANSFORMED"}],
                }
            },
        )
    assert not result.errors, result.errors
    return result.data["createADataset"]["id"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_reconstruction_is_placed_through_its_localization_table(authenticated_context: HttpContext) -> None:
    """The payoff: register the table, and the image built from it comes along.

    This is what container-keying the fact tree bought. Keyed by dataset id, the walks had
    no key for a table -- `_derivation_descendants` never discovered the reconstruction as
    a descendant, and `container_buckets` closed over nothing -- so the image was
    UNREGISTERED however real the SCALE edge was.

    The transform is stated explicitly, and has to be: an omitted one is UNMAPPABLE, and
    `is_traversable` refuses that edge, so nothing would be inherited through it.
    """
    table = await _table(authenticated_context, "Localizations", columns=_LOCALIZATION_COLUMNS)
    render = await _reconstruction(authenticated_context, table, transform={"kind": "SCALE", "scale": [10.0, 10.0]})
    scene = await seed.create_scene(authenticated_context, "Composition")

    def register_and_layer() -> None:
        # The table is registered into the world; the reconstruction is not.
        models.Transformation.objects.create(
            kind=enums.TransformKindChoices.SCALE.value,
            input=models.TableDataset.objects.get(pk=table["id"]).coordinate_system,
            output=scene.world,
            params={"scale": [0.001, 0.001]},
            organization=authenticated_context.request.organization,
        )
        dataset = models.ADataset.objects.get(pk=render)
        # An unsliced lens: its space *is* the dataset's intrinsic grid, so the layer sits
        # exactly where the reconstruction does.
        lens = models.Lens.objects.create(dataset=dataset, slices=[])
        models.Layer.objects.create(kind=enums.LayerKindChoices.IMAGE.value, scene=scene, lens=lens)

    await sync_to_async(register_and_layer)()

    result = await schema.execute(PLACEMENT, context_value=authenticated_context, variable_values={"id": str(scene.pk)})
    assert not result.errors, result.errors

    layer = result.data["scene"]["layers"][0]
    assert layer["placement"] == "PLACED", "the reconstruction inherits the table's registration"
    kinds = [step["transformation"]["kind"] for step in layer["pathToWorld"]]
    assert "SCALE" in kinds and len(kinds) >= 2, f"the path runs through the table: {kinds}"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_measurement_tables_index_space_refuses_a_metric_edge(authenticated_context: HttpContext) -> None:
    """RFC-7's "tables are leaves", enforced by the axis types rather than by a container check.

    The distinction that makes the SMLM case work is not "table" versus "image" -- it is
    whether the table declared coordinate columns. One with none gets a single INDEX axis,
    and `assert_edge_rank` refuses arithmetic on it: the distance between object 3 and
    object 4 means nothing.
    """
    mask = await seed.create_adataset(authenticated_context, "InstanceMask", axes=seed.YX_AXES, shapes=[[64, 64]])
    store = await _parquet(authenticated_context, "table-refused")

    result = await schema.execute(
        CREATE_TABLE,
        context_value=authenticated_context,
        variable_values={
            "input": {
                "name": "Objects",
                "data": str(store.pk),
                "columns": _MEASUREMENT_COLUMNS,
                "derivedFrom": [{"kind": "DATASET", "dataset": str(mask.pk), "transform": {"kind": "SCALE", "scale": [1.0]}}],
            }
        },
    )
    assert result.errors and "INDEX axis" in str(result.errors[0]), str(result.errors and result.errors[0])
    assert not await sync_to_async(models.TableDataset.objects.filter(name="Objects").exists)(), "a refused edge rolls the table back with it"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_source_reports_its_non_dataset_children_under_its_own_name(authenticated_context: HttpContext) -> None:
    """`derivedDatasets` stays about datasets; `derivedResidents` is the wider question.

    The narrow walk requires the edge's input to *be* an intrinsic system, which is exactly
    what confines it to array datasets -- so a measurement table computed from this image
    is missing from it. That was widened by adding a second field rather than by changing
    what the first one returns: `derivedDatasets` returning a table would be a field whose
    name lies.
    """
    mask = await seed.create_adataset(authenticated_context, "InstanceMask", axes=seed.YX_AXES, shapes=[[64, 64]])
    await _table(authenticated_context, "Objects", columns=_MEASUREMENT_COLUMNS, derived_from=[{"kind": "DATASET", "dataset": str(mask.pk)}])

    result = await schema.execute(
        """
        query Children($id: ID!) {
          adataset(id: $id) {
            derivedDatasets { id name }
            derivedResidents { __typename ... on TableDataset { name } }
          }
        }
        """,
        context_value=authenticated_context,
        variable_values={"id": str(mask.pk)},
    )
    assert not result.errors, result.errors

    dataset = result.data["adataset"]
    assert dataset["derivedDatasets"] == [], "no *dataset* was derived from the mask"
    assert [(r["__typename"], r.get("name")) for r in dataset["derivedResidents"]] == [("TableDataset", "Objects")]


def test_the_derivation_union_is_published_for_codegen() -> None:
    """The third `@unionElementOf` instance, held to the same two rules as the other two.

    Both are silent failures. A member input is referenced by no field, so dropping
    `derived_from_union_types` from the schema's `types=[...]` erases it from the SDL with
    no import error and no query error; and a member that declares only its own id field
    generates a type a client cannot construct, having no way to say what it is derived
    from *with*.
    """
    sdl = schema.as_str()
    common = ["kind", "transform", "valueRelation"]

    for member in derived_from_union_types:
        start = sdl.find(f"input {member.__name__} ")
        assert start >= 0, f"{member.__name__} missing from the SDL"
        header = sdl[start : sdl.find("{", start)]
        assert '@unionElementOf(union: "DerivedFromInput", discriminator: "kind", key: ' in header, f"{member.__name__} lacks its annotation"

        body = sdl[start : sdl.find("\n}", start)]
        missing = [field for field in common if not re.search(rf"^\s*{field}:", body, re.M)]
        assert not missing, f"{member.__name__} does not declare the common fields {missing}"

    # Every source kind a client may name has a member to name it with.
    enum_body = sdl[sdl.find("enum DerivationSourceKind") : sdl.find("}", sdl.find("enum DerivationSourceKind"))]
    for kind in enums.DerivationSourceKind:
        assert kind.value in enum_body
    assert len(derived_from_union_types) == len(list(enums.DerivationSourceKind))


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_registration_is_not_reported_as_a_derivation(authenticated_context: HttpContext) -> None:
    """`derivedFrom` on a freestanding collection must stay empty after it is registered.

    `collection_derivation_edge` took the earliest edge out of the collection's system,
    kind-blind *and* order-blind -- so registering a freestanding collection with
    `createTransformation` made that registration answer a field documented as "the edge
    back into the data it was computed from". Pre-existing bug; the shared derivation
    predicate is what fixes it, since a world has no residents to be a container.
    """
    table = await _table(authenticated_context, "Freestanding", columns=_LOCALIZATION_COLUMNS)
    assert table["derivedFrom"] == [], "nothing was named, so nothing is reported"

    scene = await seed.create_scene(authenticated_context, "Composition")

    def register() -> None:
        models.Transformation.objects.create(
            kind=enums.TransformKindChoices.SCALE.value,
            input=models.TableDataset.objects.get(pk=table["id"]).coordinate_system,
            output=scene.world,
            params={"scale": [0.001, 0.001]},
            organization=authenticated_context.request.organization,
        )

    await sync_to_async(register)()

    result = await schema.execute(
        "query T($id: ID!) { tableDataset(id: $id) { derivedFrom { id kind } } }",
        context_value=authenticated_context,
        variable_values={"id": table["id"]},
    )
    assert not result.errors, result.errors
    assert result.data["tableDataset"]["derivedFrom"] == [], "a registration is where the data was put, not where it came from"
