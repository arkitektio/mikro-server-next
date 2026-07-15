"""A table dataset is a parquet table that owns its space, placeable by its coordinate columns.

Two shapes in one object. Declare coordinate columns (x, y in nanometres) and the table
owns a placeable coordinate system whose axes ARE those columns -- a localization table
that registers into a scene like an image does. Declare none and it degenerates to the old
FeatureCollection: a single INDEX axis enumerating the rows, and an UNMAPPABLE edge that
records "this came from that image" while denying that any pixel is a row.

The load-bearing tests here are the placement one (a point layer over a table dataset must
reach world through the table's own derivation edge) and the column-mapping one (x/y/z are
resolved by axis *name*, not array position, so a table declared (x, y, z) is not silently
transposed).
"""

import pytest
from asgiref.sync import sync_to_async
from kante.context import HttpContext

from core import enums, models
from mikro_server.schema import schema
from tests import seed

CREATE = """
mutation Create($input: CreateTableDatasetInput!) {
  createTableDataset(input: $input) {
    id
    name
    store { id key }
    columns { name dtype role axisType unit order }
    coordinateSystem { id kind axes { name type unit order } }
    derivedFrom {
      id kind
      output { id kind }
      ... on UnmappableTransformation { reason }
    }
  }
}
"""

PLACEMENT = """
query Placement($id: ID!) {
  scene(id: $id) {
    layers {
      id
      placement
      pathToWorld {
        inverted
        transformation { id kind input { id kind } output { id kind } }
      }
    }
  }
}
"""

_AFFINE_3D = [
    [1.0, 0.0, 0.0, 5.0],
    [0.0, 1.0, 0.0, 5.0],
    [0.0, 0.0, 1.0, 0.0],
]


async def _parquet(ctx: HttpContext, key: str) -> models.ParquetStore:
    return await sync_to_async(models.ParquetStore.objects.create)(path=f"s3://parquet/{key}", bucket="parquet", key=key, organization=ctx.request.organization)


async def _create(ctx: HttpContext, key: str, **input_fields) -> dict:
    store = await _parquet(ctx, key)
    return await schema.execute(CREATE, context_value=ctx, variable_values={"input": {"data": str(store.pk), **input_fields}})


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_coordinate_table_owns_a_placeable_space(authenticated_context: HttpContext):
    """Its coordinate columns become SPACE axes of a TABLE system, in declared order and units."""
    result = await _create(
        authenticated_context,
        "localizations",
        name="molecules",
        columns=[
            {"name": "y", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE", "unit": "nanometer"},
            {"name": "x", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE", "unit": "nanometer"},
            {"name": "photons", "dtype": "DOUBLE", "role": "ATTRIBUTE"},
        ],
    )
    assert not result.errors, result.errors
    table = result.data["createTableDataset"]

    assert table["coordinateSystem"]["kind"] == "TABLE"
    axes = table["coordinateSystem"]["axes"]
    assert [a["name"] for a in axes] == ["y", "x"]
    assert [a["type"] for a in axes] == ["SPACE", "SPACE"]
    assert all("nanometer" in a["unit"] for a in axes)
    assert [a["order"] for a in axes] == [0, 1]
    # The attribute column is declared but is not an axis.
    assert {c["name"] for c in table["columns"]} == {"y", "x", "photons"}
    assert next(c for c in table["columns"] if c["name"] == "photons")["role"] == "ATTRIBUTE"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_measurement_table_is_the_feature_collection_case(authenticated_context: HttpContext):
    """No coordinate columns: a single INDEX axis, and an UNMAPPABLE edge to its source."""
    dataset = await seed.create_adataset(authenticated_context, "Labels")
    system = await sync_to_async(lambda: dataset.intrinsic_coordinate_system)()

    result = await _create(
        authenticated_context,
        "morphology",
        name="nuclei morphology",
        columns=[{"name": "area", "dtype": "DOUBLE", "role": "ATTRIBUTE"}, {"name": "mean_intensity", "dtype": "DOUBLE", "role": "ATTRIBUTE"}],
        coordinateSystem=str(system.pk),
    )
    assert not result.errors, result.errors
    table = result.data["createTableDataset"]

    axes = table["coordinateSystem"]["axes"]
    assert [a["name"] for a in axes] == ["object"]
    assert axes[0]["type"] == "INDEX"
    assert axes[0]["unit"] is None
    assert table["derivedFrom"]["kind"] == "UNMAPPABLE"
    assert table["derivedFrom"]["output"]["id"] == str(system.pk)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_the_default_derivation_is_unmappable_even_with_coordinates(authenticated_context: HttpContext):
    """Naming a source is not authoring a map: without an explicit kind the edge stays UNMAPPABLE."""
    dataset = await seed.create_adataset(authenticated_context, "Labels")  # (c, y, x)
    system = await sync_to_async(lambda: dataset.intrinsic_coordinate_system)()

    result = await _create(
        authenticated_context,
        "loc-default",
        name="molecules",
        columns=[
            {"name": "y", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"},
            {"name": "x", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"},
        ],
        coordinateSystem=str(system.pk),
    )
    assert not result.errors, result.errors
    assert result.data["createTableDataset"]["derivedFrom"]["kind"] == "UNMAPPABLE"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_identity_across_mismatched_rank_is_rejected(authenticated_context: HttpContext):
    """A (y,x) table cannot claim IDENTITY into a (c,y,x) source; BY_DIMENSION is how a rank change is stated."""
    dataset = await seed.create_adataset(authenticated_context, "Labels")  # (c, y, x)
    system = await sync_to_async(lambda: dataset.intrinsic_coordinate_system)()

    bad = await _create(
        authenticated_context,
        "loc-identity",
        name="molecules",
        columns=[
            {"name": "y", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"},
            {"name": "x", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"},
        ],
        coordinateSystem=str(system.pk),
        derivedFrom={"kind": "IDENTITY"},
    )
    assert bad.errors, "an identity between a 2-axis table and a 3-axis image is a rank change in disguise"

    good = await _create(
        authenticated_context,
        "loc-bydim",
        name="molecules",
        columns=[
            {"name": "y", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"},
            {"name": "x", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"},
        ],
        coordinateSystem=str(system.pk),
        derivedFrom={"kind": "BY_DIMENSION", "inputAxes": ["y", "x"], "outputAxes": ["y", "x"]},
    )
    assert not good.errors, good.errors
    assert good.data["createTableDataset"]["derivedFrom"]["kind"] == "BY_DIMENSION"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_freestanding_table_has_no_edge(authenticated_context: HttpContext):
    """No source coordinate system: the table is a root, with no derivation edge."""
    result = await _create(
        authenticated_context,
        "free",
        name="molecules",
        columns=[{"name": "y", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"}, {"name": "x", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"}],
    )
    assert not result.errors, result.errors
    assert result.data["createTableDataset"]["derivedFrom"] is None


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_out_of_order_coordinate_columns_are_rejected(authenticated_context: HttpContext):
    """Space-before-time violates the ordering the render-axis derivation relies on."""
    result = await _create(
        authenticated_context,
        "bad-order",
        name="molecules",
        columns=[
            {"name": "x", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"},
            {"name": "t", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "TIME"},
        ],
    )
    assert result.errors, "time must come before space"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_coordinate_column_must_be_space_or_time(authenticated_context: HttpContext):
    """A CHANNEL axis is not a coordinate: it indexes acquisitions, not positions."""
    result = await _create(
        authenticated_context,
        "bad-type",
        name="molecules",
        columns=[
            {"name": "y", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"},
            {"name": "x", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"},
            {"name": "c", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "CHANNEL"},
        ],
    )
    assert result.errors, "a coordinate column must be SPACE or TIME"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_the_table_dataset_exposes_no_rows(authenticated_context: HttpContext):
    """Like FeatureCollection: the client reads the Parquet, GraphQL never paginates rows."""
    sdl = schema.as_str()
    definition = sdl[sdl.find("type TableDataset ") : sdl.find("\n}", sdl.find("type TableDataset "))]
    assert "\n  rows" not in definition
    assert "\n  columns" in definition, "the declared schema is exposed; the row data is not"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_point_layer_over_a_table_dataset_reaches_world(authenticated_context: HttpContext):
    """The whole feature: a localization table is placed through its own derivation edge."""
    dataset = await seed.create_adataset(authenticated_context, "Labels")  # (c, y, x)
    system = await sync_to_async(lambda: dataset.intrinsic_coordinate_system)()

    created = await _create(
        authenticated_context,
        "loc-placed",
        name="molecules",
        columns=[
            {"name": "y", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"},
            {"name": "x", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"},
        ],
        coordinateSystem=str(system.pk),
        derivedFrom={"kind": "BY_DIMENSION", "inputAxes": ["y", "x"], "outputAxes": ["y", "x"]},
    )
    assert not created.errors, created.errors
    table_id = created.data["createTableDataset"]["id"]

    scene = await seed.create_scene(authenticated_context, "Composition")

    def register() -> None:
        edge = models.Transformation.objects.create(
            kind=enums.TransformKindChoices.AFFINE.value,
            input=dataset.intrinsic_coordinate_system,
            output=scene.world_coordinate_system,
            params={"affine": _AFFINE_3D},
            organization=authenticated_context.request.organization,
        )
        scene.coordinate_transformations.add(edge)

    await sync_to_async(register)()

    made = await schema.execute(
        """
        mutation Make($input: CreatePointLayerInput!) {
          createPointLayer(input: $input) { id xColumn yColumn }
        }
        """,
        context_value=authenticated_context,
        variable_values={"input": {"scene": str(scene.pk), "tableDataset": table_id}},
    )
    assert not made.errors, made.errors
    # The mappings come from the declared columns, by name.
    assert made.data["createPointLayer"]["xColumn"] == "x"
    assert made.data["createPointLayer"]["yColumn"] == "y"

    placement = await schema.execute(PLACEMENT, context_value=authenticated_context, variable_values={"id": str(scene.pk)})
    assert not placement.errors, placement.errors
    path = placement.data["scene"]["layers"][0]["pathToWorld"]
    assert path is not None, "a table dataset is placed by the image its rows were localized in"
    assert path[-1]["transformation"]["output"]["kind"] == "WORLD"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_column_mappings_are_by_name_not_position(authenticated_context: HttpContext):
    """A table declared (x, y, z) must not have x and z silently swapped by array-order logic."""
    created = await _create(
        authenticated_context,
        "xyz",
        name="molecules",
        columns=[
            {"name": "x", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"},
            {"name": "y", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"},
            {"name": "z", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"},
        ],
    )
    assert not created.errors, created.errors
    scene = await seed.create_scene(authenticated_context, "Composition")

    made = await schema.execute(
        """
        mutation Make($input: CreatePointLayerInput!) {
          createPointLayer(input: $input) { id xColumn yColumn zColumn }
        }
        """,
        context_value=authenticated_context,
        variable_values={"input": {"scene": str(scene.pk), "tableDataset": created.data["createTableDataset"]["id"]}},
    )
    assert not made.errors, made.errors
    layer = made.data["createPointLayer"]
    assert layer["xColumn"] == "x", "x must be the column named x, not the last spatial column"
    assert layer["yColumn"] == "y"
    assert layer["zColumn"] == "z"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_unregistered_derived_table_layer_inherits_an_assumed_placement(authenticated_context: HttpContext):
    """A table derived from a dataset gets the same courtesy an image layer does: an assumed placement.

    ``ensure_registered`` pins the source's root on the shared axis names, so the point
    layer resolves to world through an assumed edge -- the placement rests on an assumption
    (UNKNOWN validity), but it is not silently unplaced.
    """
    dataset = await seed.create_adataset(authenticated_context, "Labels")  # (c, y, x)
    system = await sync_to_async(lambda: dataset.intrinsic_coordinate_system)()

    created = await _create(
        authenticated_context,
        "loc-unreg",
        name="molecules",
        columns=[{"name": "y", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"}, {"name": "x", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"}],
        coordinateSystem=str(system.pk),
        derivedFrom={"kind": "BY_DIMENSION", "inputAxes": ["y", "x"], "outputAxes": ["y", "x"]},
    )
    assert not created.errors, created.errors
    scene = await seed.create_scene(authenticated_context, "Composition")  # world (z, y, x), shares y/x

    made = await schema.execute(
        """
        mutation Make($input: CreatePointLayerInput!) {
          createPointLayer(input: $input) { id placementValidity }
        }
        """,
        context_value=authenticated_context,
        variable_values={"input": {"scene": str(scene.pk), "tableDataset": created.data["createTableDataset"]["id"]}},
    )
    assert not made.errors, made.errors
    assert made.data["createPointLayer"]["placementValidity"] == "UNKNOWN", "placed, but by an assumption"

    placement = await schema.execute(PLACEMENT, context_value=authenticated_context, variable_values={"id": str(scene.pk)})
    assert not placement.errors, placement.errors
    assert placement.data["scene"]["layers"][0]["pathToWorld"] is not None


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_freestanding_table_layer_has_no_path(authenticated_context: HttpContext):
    """A table derived from nothing has no source to inherit a placement from, so it is unplaced."""
    created = await _create(
        authenticated_context,
        "free-layer",
        name="molecules",
        columns=[{"name": "y", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"}, {"name": "x", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"}],
    )
    assert not created.errors, created.errors
    scene = await seed.create_scene(authenticated_context, "Composition")

    made = await schema.execute(
        """
        mutation Make($input: CreatePointLayerInput!) {
          createPointLayer(input: $input) { id }
        }
        """,
        context_value=authenticated_context,
        variable_values={"input": {"scene": str(scene.pk), "tableDataset": created.data["createTableDataset"]["id"]}},
    )
    assert not made.errors, made.errors

    placement = await schema.execute(PLACEMENT, context_value=authenticated_context, variable_values={"id": str(scene.pk)})
    assert not placement.errors, placement.errors
    assert placement.data["scene"]["layers"][0]["pathToWorld"] is None
