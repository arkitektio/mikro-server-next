"""A table dataset is a parquet table that owns its space, placeable by its coordinate columns.

Two shapes in one object. Declare coordinate columns (x, y in nanometres) and the table
owns a placeable coordinate system whose axes ARE those columns -- a localization table
placed by an explicitly authored registration, like every other layer source. Declare none
and it degenerates to the old FeatureCollection: a single INDEX axis enumerating the rows,
and an UNMAPPABLE edge that records "this came from that image" while denying that any
pixel is a row.

The load-bearing tests here are the placement one (a point layer over a table dataset must
reach world through the table's own derivation edge), the rejection ones (an unplaced
source is refused at layer creation, never silently unplaced or fabricated into place),
and the column-mapping one (x/y/z are resolved by axis *name*, not array position, so a
table declared (x, y, z) is not silently transposed).
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
    columns { name dtype role axisType unit order description }
    coordinateSystem { id  axes { name type unit order description } }
    derivedFrom {
      id kind
      output { id  }
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
        transformation { id kind input { id  } output { id  } }
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

    assert table["coordinateSystem"]["kind"] == "INTRINSIC", "a table's coordinate-column space is its own native (INTRINSIC) space"
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
async def test_a_coordinate_column_must_be_a_permitted_axis_type(authenticated_context: HttpContext):
    """A CHANNEL axis is not a coordinate: it indexes acquisitions, not positions.

    SPACE, TIME and INDEX are the permitted set -- INDEX because an id column's values are the
    coordinates of the space a label mask's pixels point into, exactly as an `x` column's are.
    """
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
    assert result.errors, "a coordinate column must be SPACE, TIME or INDEX"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_table_dataset_is_not_editable_beyond_its_name(authenticated_context: HttpContext):
    """The store, the columns and the coordinate system are fixed at creation.

    Stated in three docstrings and a type description, and until now asserted nowhere -- which
    is how those docstrings came to claim the opposite ("Mutable, like ADataset -- a
    recomputation edits the store"). A reader who believes that builds a cache that goes
    silently stale. The API is the authority, so pin it here.
    """
    created = await _create(
        authenticated_context,
        "fixed-table",
        name="nuclei",
        columns=[{"name": "i", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"}, {"name": "area", "dtype": "DOUBLE", "role": "ATTRIBUTE"}],
    )
    assert not created.errors, created.errors
    table = created.data["createTableDataset"]
    store_at_creation = table["store"]["id"]

    # The whole of the editable surface: two scalar fields, neither of them the data.
    sdl = schema.as_str()
    definition = sdl[sdl.find("input UpdateTableDatasetInput ") : sdl.find("\n}", sdl.find("input UpdateTableDatasetInput "))]
    fields = {line.strip().split(":")[0] for line in definition.split("\n") if ":" in line and not line.strip().startswith('"')}
    assert fields == {"id", "name", "description"}, f"updateTableDataset must not reach the store, the columns or the space, but takes {fields}"

    renamed = await schema.execute(
        "mutation Update($input: UpdateTableDatasetInput!) { updateTableDataset(input: $input) { id name } }",
        context_value=authenticated_context,
        variable_values={"input": {"id": table["id"], "name": "renamed"}},
    )
    assert not renamed.errors, renamed.errors
    assert renamed.data["updateTableDataset"]["name"] == "renamed"

    # ...and the store and the declared schema are exactly where they were.
    after = await sync_to_async(lambda: models.TableDataset.objects.get(pk=table["id"]))()
    assert str(after.store_id) == store_at_creation, "renaming must not disturb the store"
    assert await sync_to_async(lambda: [c.name for c in after.columns.all()])() == ["i", "area"]

    # A table's own system is refused by updateCoordinateSystem: it serves shared spaces only.
    renamed_space = await schema.execute(
        "mutation Update($input: UpdateCoordinateSystemInput!) { updateCoordinateSystem(input: $input) { id name } }",
        context_value=authenticated_context,
        variable_values={"input": {"id": table["coordinateSystem"]["id"], "name": "hijacked"}},
    )
    assert renamed_space.errors, "a table owns its space; only a shared space has a lifecycle of its own"
    assert "owned by a container" in str(renamed_space.errors[0])


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
        models.Transformation.objects.create(
            kind=enums.TransformKindChoices.AFFINE.value,
            input=dataset.intrinsic_coordinate_system,
            output=scene.world,
            params={"affine": _AFFINE_3D},
            organization=authenticated_context.request.organization,
        )

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
    assert path[-1]["transformation"]["output"]["kind"] == "SHARED"


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
    table_id = created.data["createTableDataset"]["id"]
    scene = await seed.create_scene(authenticated_context, "Composition")
    system = await sync_to_async(lambda: models.TableDataset.objects.get(pk=table_id).coordinate_system)()
    await seed.register_into_scene(authenticated_context, scene, system=system)

    made = await schema.execute(
        """
        mutation Make($input: CreatePointLayerInput!) {
          createPointLayer(input: $input) { id xColumn yColumn zColumn }
        }
        """,
        context_value=authenticated_context,
        variable_values={"input": {"scene": str(scene.pk), "tableDataset": table_id}},
    )
    assert not made.errors, made.errors
    layer = made.data["createPointLayer"]
    assert layer["xColumn"] == "x", "x must be the column named x, not the last spatial column"
    assert layer["yColumn"] == "y"
    assert layer["zColumn"] == "z"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_unregistered_derived_table_layer_is_rejected(authenticated_context: HttpContext):
    """A derived table whose source is not registered has no path, so the layer is refused.

    Nothing is fabricated any more: the error names the mutation that closes the gap, and
    registering the source dataset (whose registration the table's derivation edge chains
    through) makes the same call succeed.
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

    make = """
    mutation Make($input: CreatePointLayerInput!) {
      createPointLayer(input: $input) { id placementValidity }
    }
    """
    variables = {"input": {"scene": str(scene.pk), "tableDataset": created.data["createTableDataset"]["id"]}}

    refused = await schema.execute(make, context_value=authenticated_context, variable_values=variables)
    assert refused.errors, "an unplaced source must be refused, not silently unplaced"
    assert "createTransformation" in str(refused.errors[0]), "the error points at the missing registration"
    edge_count = await sync_to_async(models.Transformation.objects.count)()

    await seed.register_into_scene(authenticated_context, scene, dataset)
    made = await schema.execute(make, context_value=authenticated_context, variable_values=variables)
    assert not made.errors, made.errors
    assert made.data["createPointLayer"]["placementValidity"] == "MANUAL", "the weakest edge is the authored registration"
    # The layer mutation itself wrote nothing to the graph: only the explicit registration did.
    assert await sync_to_async(models.Transformation.objects.count)() == edge_count + 2  # wrapper + IDENTITY child

    placement = await schema.execute(PLACEMENT, context_value=authenticated_context, variable_values={"id": str(scene.pk)})
    assert not placement.errors, placement.errors
    assert placement.data["scene"]["layers"][0]["pathToWorld"] is not None


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_freestanding_table_layer_is_rejected_until_its_space_is_registered(authenticated_context: HttpContext):
    """A table derived from nothing has no source to chain through: register its own space, or no layer."""
    created = await _create(
        authenticated_context,
        "free-layer",
        name="molecules",
        columns=[{"name": "y", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"}, {"name": "x", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"}],
    )
    assert not created.errors, created.errors
    table_id = created.data["createTableDataset"]["id"]
    scene = await seed.create_scene(authenticated_context, "Composition")

    make = """
    mutation Make($input: CreatePointLayerInput!) {
      createPointLayer(input: $input) { id }
    }
    """
    variables = {"input": {"scene": str(scene.pk), "tableDataset": table_id}}

    refused = await schema.execute(make, context_value=authenticated_context, variable_values=variables)
    assert refused.errors, "a freestanding table's space reaches no world until someone registers it"
    assert "createTransformation" in str(refused.errors[0])

    system = await sync_to_async(lambda: models.TableDataset.objects.get(pk=table_id).coordinate_system)()
    await seed.register_into_scene(authenticated_context, scene, system=system)
    made = await schema.execute(make, context_value=authenticated_context, variable_values=variables)
    assert not made.errors, made.errors

    placement = await schema.execute(PLACEMENT, context_value=authenticated_context, variable_values={"id": str(scene.pk)})
    assert not placement.errors, placement.errors
    assert placement.data["scene"]["layers"][0]["pathToWorld"] is not None


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_registration_is_not_an_ingest_concern(authenticated_context: HttpContext):
    """createTableDataset takes no `scene`: a registration is a separate, explicit step."""
    sdl = schema.as_str()
    definition = sdl[sdl.find("input CreateTableDatasetInput ") : sdl.find("\n}", sdl.find("input CreateTableDatasetInput "))]
    assert definition, "the input type exists"
    assert "\n  scene" not in definition, "registering into a scene is createTransformation's job, not ingest's"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_column_descriptions_are_stored_and_carried_onto_axes(authenticated_context: HttpContext):
    """A column's description round-trips, and a coordinate column's is carried onto its axis."""
    result = await _create(
        authenticated_context,
        "described",
        name="molecules",
        columns=[
            {"name": "y", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE", "description": "distance from the coverslip"},
            {"name": "x", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE"},
            {"name": "photons", "dtype": "DOUBLE", "role": "ATTRIBUTE", "description": "photon count of the localization"},
        ],
    )
    assert not result.errors, result.errors
    table = result.data["createTableDataset"]

    columns = {c["name"]: c for c in table["columns"]}
    assert columns["photons"]["description"] == "photon count of the localization"
    assert columns["x"]["description"] is None

    axes = {a["name"]: a for a in table["coordinateSystem"]["axes"]}
    assert axes["y"]["description"] == "distance from the coverslip", "the axis is the column, so it carries the same description"
    assert axes["x"]["description"] is None
