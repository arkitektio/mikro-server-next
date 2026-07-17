"""Attribute plans: the read side the FIELD edge implies (RFC-7).

The server returns a plan; a worker executes it. A plan names the array to sample, the
axes to sample it on, the parquet to query and the columns to select -- and takes no
coordinate, so a client fetches it once and runs it per hover against the mask chunks it
is already rendering. The walk is pure over ``Transformation`` rows, so -- unlike every
other parquet path in this codebase -- it is testable for real: a plan reads nothing, so
there is nothing to mock and no object store to be unreachable.

The load-bearing tests: sibling fan-out (two tables off one mask, with differently named
produced axes -- the reason `produces` is per-edge), the warp-field skip (a FIELD whose
output is a pixel grid must not appear as a bogus plan; ablate the ``table_dataset_id``
guard in ``build_attribute_plans`` and it does), the refusals (a lens owns no array; an
array with no store cannot be sampled), and the SQL builder's injection test (identifiers
quoted, values only ever ``?``).

``TableColumn.references`` is tested here too: it is the record-land sibling of the FIELD
edge (FIELD is the single crossing from geometry into records; between tables, a relation
is a schema fact), and the plans' `attributes` carry it to the client.
"""

import pytest
from asgiref.sync import sync_to_async
from django.db.models.deletion import ProtectedError
from kante.context import HttpContext

from core import enums, models
from core.logic import attribute_plans as attribute_plans_logic
from core.logic import graph as graph_logic
from mikro_server.schema import schema
from tests import seed

CREATE_TABLE = """
mutation Create($input: CreateTableDatasetInput!) {
  createTableDataset(input: $input) {
    id
    columns { name role references { id name } }
    coordinateSystem { id axes { name type } }
  }
}
"""

CREATE_TRANSFORM = """
mutation Create($input: CreateTransformationInput!) {
  createTransformation(input: $input) { id }
}
"""

PLANS = """
query Plans($system: ID!, $maxDepth: Int) {
  attributePlans(system: $system, maxDepth: $maxDepth) {
    edge { id version }
    table { id name }
    path { transformation { id version } inverted }
    sample { system { id } store { id } consumes produces passthrough }
    lookup {
      store { id }
      keyColumns { axis column { name dtype } }
      attributes { name references { id } }
      sql
    }
  }
}
"""

#: A timelapse mask: per-frame object ids, so the table key is (t, i) and t passes through.
TYX_AXES = [
    seed.axis("t", enums.AxisType.TIME),
    seed.axis("y", enums.AxisType.SPACE),
    seed.axis("x", enums.AxisType.SPACE),
]


async def _parquet(ctx: HttpContext, key: str) -> models.ParquetStore:
    return await sync_to_async(models.ParquetStore.objects.create)(path=f"s3://parquet/{key}", bucket="parquet", key=key, organization=ctx.request.organization)


async def _mask(ctx: HttpContext, name: str = "nuclei labels", axes: list | None = None, shapes: list | None = None, with_store: bool = True) -> models.ADataset:
    """A label-mask dataset whose level-0 array has a zarr store a plan can name."""
    dataset = await seed.create_adataset(ctx, name, axes=axes or TYX_AXES, shapes=shapes or [[10, 64, 64]])
    if with_store:

        def attach() -> None:
            store = models.ZarrStore.objects.create(path=f"s3://zarr/{name}", bucket="zarr", key=name.replace(" ", "-"), organization=ctx.request.organization)
            array = dataset.data_arrays.get(level=0)
            array.store = store
            array.save()

        await sync_to_async(attach)()
    return dataset


async def _table(ctx: HttpContext, name: str, columns: list[dict]) -> dict:
    result = await schema.execute(CREATE_TABLE, context_value=ctx, variable_values={"input": {"name": name, "data": str((await _parquet(ctx, name.replace(" ", "-"))).pk), "columns": columns}})
    assert not result.errors, result.errors
    return result.data["createTableDataset"]


async def _field_edge(ctx: HttpContext, mask_system: models.CoordinateSystem, table: dict, output_axes: list[str]) -> None:
    """The dereference: the mask's own pixels are the map, (y,x) consumed, ids produced."""
    result = await schema.execute(
        CREATE_TRANSFORM,
        context_value=ctx,
        variable_values={
            "input": {
                "input": str(mask_system.pk),
                "output": table["coordinateSystem"]["id"],
                "field": str(mask_system.pk),
                "kind": "FIELD",
                "inputAxes": ["y", "x"],
                "outputAxes": output_axes,
            }
        },
    )
    assert not result.errors, result.errors


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_sibling_fan_out_returns_one_plan_per_table(authenticated_context: HttpContext):
    """Two FIELD edges off one mask are two plans, each zipped against its OWN produced axis.

    The produced axis is per-edge on purpose: objects names it `i`, intensity names it
    `label_id`, and a client zipping the sampled value against a shared key set would be
    wrong for one of them. Multi-table breadth is sibling fan-out -- no `value_column`,
    no join modelling, nothing beyond edges that exist today.
    """
    mask = await _mask(authenticated_context)
    mask_system = await sync_to_async(lambda: mask.intrinsic_coordinate_system)()

    objects = await _table(
        authenticated_context,
        "nuclei morphology",
        [
            {"name": "t", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "TIME"},
            {"name": "i", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"},
            {"name": "area", "dtype": "DOUBLE", "role": "ATTRIBUTE"},
            {"name": "mean_intensity", "dtype": "DOUBLE", "role": "ATTRIBUTE"},
        ],
    )
    intensity = await _table(
        authenticated_context,
        "nuclei intensity",
        [
            {"name": "t", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "TIME"},
            {"name": "label_id", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"},
            {"name": "integrated", "dtype": "DOUBLE", "role": "ATTRIBUTE"},
        ],
    )
    await _field_edge(authenticated_context, mask_system, objects, ["i"])
    await _field_edge(authenticated_context, mask_system, intensity, ["label_id"])

    result = await schema.execute(PLANS, context_value=authenticated_context, variable_values={"system": str(mask_system.pk)})
    assert not result.errors, result.errors
    plans = result.data["attributePlans"]
    assert len(plans) == 2, "one plan per sibling table"

    by_table = {plan["table"]["name"]: plan for plan in plans}
    morphology = by_table["nuclei morphology"]
    assert morphology["sample"]["consumes"] == ["y", "x"]
    assert morphology["sample"]["produces"] == ["i"]
    assert morphology["sample"]["passthrough"] == ["t"], "the axis the edge did not consume passes through by name"
    assert morphology["sample"]["system"]["id"] == str(mask_system.pk), "a mask's own pixels are the map"
    assert [(key["axis"], key["column"]["name"]) for key in morphology["lookup"]["keyColumns"]] == [("t", "t"), ("i", "i")]
    assert morphology["lookup"]["sql"] == 'SELECT "area", "mean_intensity" FROM read_parquet(?) WHERE "t" = ? AND "i" = ?'
    assert morphology["edge"]["version"] == 1, "the cache key rides on the edge"

    assert by_table["nuclei intensity"]["sample"]["produces"] == ["label_id"], "the produced axis is per-edge, never a shared key set"
    assert by_table["nuclei intensity"]["lookup"]["sql"] == 'SELECT "integrated" FROM read_parquet(?) WHERE "t" = ? AND "label_id" = ?'


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_warp_field_target_is_not_a_plan(authenticated_context: HttpContext):
    """A FIELD whose output is a pixel grid is a registration, not a dereference.

    ABLATION: drop the ``table_dataset_id is None`` guard in ``build_attribute_plans`` and
    this edge comes back as a bogus plan with no table to look anything up in.
    """
    mask = await _mask(authenticated_context, axes=seed.YX_AXES, shapes=[[64, 64]])
    atlas = await seed.create_adataset(authenticated_context, "atlas", axes=seed.YX_AXES, shapes=[[64, 64]])
    mask_system = await sync_to_async(lambda: mask.intrinsic_coordinate_system)()

    def warp_edge() -> None:
        models.Transformation.objects.create(
            kind=enums.TransformKindChoices.FIELD.value,
            input=mask_system,
            output=atlas.intrinsic_coordinate_system,
            field=mask_system,
            input_axes=["y", "x"],
            output_axes=["y", "x"],
            organization=authenticated_context.request.organization,
        )

    await sync_to_async(warp_edge)()

    result = await schema.execute(PLANS, context_value=authenticated_context, variable_values={"system": str(mask_system.pk)})
    assert not result.errors, result.errors
    assert result.data["attributePlans"] == [], "a pixel-grid target is skipped, not planned"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_degenerate_table_is_not_a_plan(authenticated_context: HttpContext):
    """A table with no coordinate columns enumerates rows on a synthetic axis nothing can bind.

    The `object` axis has no backing column, so there is no WHERE clause to write --
    positional parquet access is not a lookup a plan can state honestly. The same table is
    refused as a reference target, for the same reason.
    """
    mask = await _mask(authenticated_context, axes=seed.YX_AXES, shapes=[[64, 64]])
    mask_system = await sync_to_async(lambda: mask.intrinsic_coordinate_system)()
    degenerate = await _table(authenticated_context, "measurements", [{"name": "area", "dtype": "DOUBLE", "role": "ATTRIBUTE"}])

    def edge() -> None:
        models.Transformation.objects.create(
            kind=enums.TransformKindChoices.FIELD.value,
            input=mask_system,
            output=models.CoordinateSystem.objects.get(pk=degenerate["coordinateSystem"]["id"]),
            field=mask_system,
            input_axes=["y", "x"],
            output_axes=["object"],
            organization=authenticated_context.request.organization,
        )

    await sync_to_async(edge)()

    result = await schema.execute(PLANS, context_value=authenticated_context, variable_values={"system": str(mask_system.pk)})
    assert not result.errors, result.errors
    assert result.data["attributePlans"] == []


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_lens_owned_field_is_refused(authenticated_context: HttpContext):
    """A lens is a selection over a dataset, nothing else: it owns no array to sample.

    Refused rather than guessed -- resolving through to the dataset's store would silently
    ignore the crop the lens exists to state.
    """
    mask = await _mask(authenticated_context, axes=seed.YX_AXES, shapes=[[64, 64]])
    mask_system = await sync_to_async(lambda: mask.intrinsic_coordinate_system)()
    table = await _table(authenticated_context, "objects", [{"name": "i", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"}, {"name": "area", "dtype": "DOUBLE", "role": "ATTRIBUTE"}])

    def lens_field_edge() -> None:
        lens = models.Lens.objects.create(dataset=mask, slices=[])
        lens_system = models.CoordinateSystem.objects.create(name="crop", lens=lens, organization=authenticated_context.request.organization)
        models.Transformation.objects.create(
            kind=enums.TransformKindChoices.FIELD.value,
            input=mask_system,
            output=models.CoordinateSystem.objects.get(pk=table["coordinateSystem"]["id"]),
            field=lens_system,
            input_axes=["y", "x"],
            output_axes=["i"],
            organization=authenticated_context.request.organization,
        )

    await sync_to_async(lens_field_edge)()

    result = await schema.execute(PLANS, context_value=authenticated_context, variable_values={"system": str(mask_system.pk)})
    assert result.errors, "a lens-owned field must be refused, not resolved through"
    assert "lens" in str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_array_without_a_store_is_refused(authenticated_context: HttpContext):
    """A plan names the array a worker samples; an array with no store cannot be named."""
    mask = await _mask(authenticated_context, axes=seed.YX_AXES, shapes=[[64, 64]], with_store=False)
    mask_system = await sync_to_async(lambda: mask.intrinsic_coordinate_system)()
    table = await _table(authenticated_context, "objects", [{"name": "i", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"}, {"name": "area", "dtype": "DOUBLE", "role": "ATTRIBUTE"}])
    await _field_edge(authenticated_context, mask_system, table, ["i"])

    result = await schema.execute(PLANS, context_value=authenticated_context, variable_values={"system": str(mask_system.pk)})
    assert result.errors, "an unsampleable array must be refused"
    assert "no zarr store" in str(result.errors[0])


def test_the_sql_builder_quotes_identifiers_and_never_interpolates_values():
    """The injection regression test: a hostile column name is a quoted identifier, nothing more.

    Pure ``(columns) -> sql``, asserted with no database -- and strictly safer than
    ``RowFilter.clause``, which is raw client SQL on a credentialed connection today.
    """
    hostile = models.TableColumn(name='a"; DROP TABLE rows; --', dtype="DOUBLE", role=enums.TableColumnRoleChoices.ATTRIBUTE.value)
    key = attribute_plans_logic.PlanKeySpec(axis="i", column=models.TableColumn(name="i", dtype="BIGINT", role=enums.TableColumnRoleChoices.COORDINATE.value))

    sql = attribute_plans_logic.build_lookup_sql(attribute_columns=[hostile], key_columns=[key])

    assert sql == 'SELECT "a""; DROP TABLE rows; --" FROM read_parquet(?) WHERE "i" = ?', "the embedded quote is doubled, so the name cannot close its own identifier"
    assert sql.count("?") == 2, "one placeholder for the parquet path, one per key -- values never appear in the string"


def test_the_sql_builder_selects_keys_when_a_table_has_only_coordinates():
    """A table whose every column is a coordinate still answers: the row exists."""
    t = attribute_plans_logic.PlanKeySpec(axis="t", column=models.TableColumn(name="t", dtype="BIGINT", role=enums.TableColumnRoleChoices.COORDINATE.value))
    i = attribute_plans_logic.PlanKeySpec(axis="i", column=models.TableColumn(name="i", dtype="BIGINT", role=enums.TableColumnRoleChoices.COORDINATE.value))

    sql = attribute_plans_logic.build_lookup_sql(attribute_columns=[], key_columns=[t, i])

    assert sql == 'SELECT "t", "i" FROM read_parquet(?) WHERE "t" = ? AND "i" = ?'


# --- discovery through the fact graph: probe the image, answer from the mask -----------


async def _derive(
    ctx: HttpContext,
    derived: models.ADataset,
    source_system: models.CoordinateSystem,
    *,
    kind: str = "IDENTITY",
    input_axes: list[str] | None = None,
    output_axes: list[str] | None = None,
    value_relation: str | None = "CATEGORIZED",
) -> models.Transformation:
    """The derivation edge a segmentation writes: derived intrinsic -> source space.

    Exactly what `_write_derivation_edges` calls, without the lens + upload ceremony.
    """

    def build() -> models.Transformation:
        return graph_logic.write_relation_edge(
            name=f"{derived.name} <- {source_system.name}",
            input_system=derived.intrinsic_coordinate_system,
            output_system=source_system,
            kind=kind,
            input_axes=input_axes,
            output_axes=output_axes,
            value_relation=value_relation,
            ctx=seed._creation(ctx),
        )

    return await sync_to_async(build)()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_probing_the_source_image_finds_the_derived_masks_plans(authenticated_context: HttpContext):
    """The scene-hover case: probe the image layer's system, answer from the derived mask.

    The image is (t,c,y,x); the mask is (t,y,x), derived BY_DIMENSION on the axes it kept
    (a segmentation is silent about `c`). The plan comes back with the derivation edge as
    a one-step `path`, inverted -- the edge is stored mask->image, the probe walks it
    backwards -- and `passthrough` is computed off the MASK's axes: `t` alone, never a
    bogus `c` borrowed from where the caller happens to stand. ABLATION: compute
    passthrough off the probed system and this test's last assert fails first.
    """
    image = await seed.create_adataset(
        authenticated_context,
        "timelapse",
        axes=[seed.axis("t", enums.AxisType.TIME), seed.axis("c", enums.AxisType.CHANNEL), seed.axis("y", enums.AxisType.SPACE), seed.axis("x", enums.AxisType.SPACE)],
        shapes=[[10, 3, 64, 64]],
    )
    mask = await _mask(authenticated_context, "instance map")
    derivation = await _derive(authenticated_context, mask, await sync_to_async(lambda: image.intrinsic_coordinate_system)(), kind="BY_DIMENSION", input_axes=["t", "y", "x"], output_axes=["t", "y", "x"])

    table = await _table(
        authenticated_context,
        "nuclei morphology",
        [
            {"name": "t", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "TIME"},
            {"name": "i", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"},
            {"name": "area", "dtype": "DOUBLE", "role": "ATTRIBUTE"},
        ],
    )
    mask_system = await sync_to_async(lambda: mask.intrinsic_coordinate_system)()
    await _field_edge(authenticated_context, mask_system, table, ["i"])

    image_system = await sync_to_async(lambda: image.intrinsic_coordinate_system)()
    result = await schema.execute(PLANS, context_value=authenticated_context, variable_values={"system": str(image_system.pk)})
    assert not result.errors, result.errors
    plans = result.data["attributePlans"]
    assert len(plans) == 1, "the mask's plan is found through the derivation edge"

    plan = plans[0]
    assert plan["path"] == [{"transformation": {"id": str(derivation.pk), "version": 1}, "inverted": True}], "the edge is stored mask->image; the probe walks it backwards"
    assert plan["sample"]["system"]["id"] == str(mask_system.pk)
    assert plan["sample"]["consumes"] == ["y", "x"]
    assert plan["sample"]["passthrough"] == ["t"], "passthrough is the MASK's unconsumed axes: the image's `c` does not exist there"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_probing_the_mask_directly_returns_an_empty_path(authenticated_context: HttpContext):
    """A locally-rooted plan carries no steps: you are already standing where it samples."""
    image = await seed.create_adataset(authenticated_context, "source", axes=seed.YX_AXES, shapes=[[64, 64]])
    mask = await _mask(authenticated_context, "labels", axes=seed.YX_AXES, shapes=[[64, 64]])
    await _derive(authenticated_context, mask, await sync_to_async(lambda: image.intrinsic_coordinate_system)())
    table = await _table(authenticated_context, "objects", [{"name": "i", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"}, {"name": "area", "dtype": "DOUBLE", "role": "ATTRIBUTE"}])
    mask_system = await sync_to_async(lambda: mask.intrinsic_coordinate_system)()
    await _field_edge(authenticated_context, mask_system, table, ["i"])

    result = await schema.execute(PLANS, context_value=authenticated_context, variable_values={"system": str(mask_system.pk)})
    assert not result.errors, result.errors
    assert [plan["path"] for plan in result.data["attributePlans"]] == [[]]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_sibling_masks_correspond_through_their_parent(authenticated_context: HttpContext):
    """Probing mask A finds mask B's table: the point in A does correspond to a point in B.

    The question is "what corresponds to this point", not "what belongs to this dataset" --
    and the guardrails (no registrations, no UNMAPPABLE, no rank-changing inverses) bound
    the answer to grids that honestly correspond. Local plans sort first, so a client that
    wants only its own reads a stable prefix (or filters `path.length == 0`).
    """
    image = await seed.create_adataset(authenticated_context, "source", axes=seed.YX_AXES, shapes=[[64, 64]])
    image_system = await sync_to_async(lambda: image.intrinsic_coordinate_system)()

    plans_by_mask: dict[str, models.Transformation] = {}
    for name, produced in (("nuclei", "i"), ("cytoplasm", "label_id")):
        mask = await _mask(authenticated_context, f"{name} labels", axes=seed.YX_AXES, shapes=[[64, 64]])
        plans_by_mask[name] = await _derive(authenticated_context, mask, image_system)
        table = await _table(authenticated_context, f"{name} table", [{"name": produced, "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"}, {"name": "area", "dtype": "DOUBLE", "role": "ATTRIBUTE"}])
        await _field_edge(authenticated_context, await sync_to_async(lambda m=mask: m.intrinsic_coordinate_system)(), table, [produced])

    nuclei_system = await sync_to_async(lambda: models.ADataset.objects.get(name="nuclei labels").intrinsic_coordinate_system)()
    result = await schema.execute(PLANS, context_value=authenticated_context, variable_values={"system": str(nuclei_system.pk)})
    assert not result.errors, result.errors
    plans = result.data["attributePlans"]
    assert [plan["table"]["name"] for plan in plans] == ["nuclei table", "cytoplasm table"], "own plan first, then by distance"
    assert plans[0]["path"] == []
    assert [(step["transformation"]["id"], step["inverted"]) for step in plans[1]["path"]] == [
        (str(plans_by_mask["nuclei"].pk), False),
        (str(plans_by_mask["cytoplasm"].pk), True),
    ], "down A's derivation forward, up B's backward"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_rank_changing_derivation_is_not_walked_backwards(authenticated_context: HttpContext):
    """A (y,x) mask embedded into a (z,y,x) image has no inverse to offer the probe.

    `is_reverse_traversable` refuses the unequal-rank hop, so the mask is honestly
    unreachable from the image -- better absent than a plan whose path cannot be composed.
    """
    image = await seed.create_adataset(authenticated_context, "volume", axes=[seed.axis("z", enums.AxisType.SPACE), seed.axis("y", enums.AxisType.SPACE), seed.axis("x", enums.AxisType.SPACE)], shapes=[[8, 64, 64]])
    mask = await _mask(authenticated_context, "slice labels", axes=seed.YX_AXES, shapes=[[64, 64]])
    table = await _table(authenticated_context, "objects", [{"name": "i", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"}, {"name": "area", "dtype": "DOUBLE", "role": "ATTRIBUTE"}])
    mask_system = await sync_to_async(lambda: mask.intrinsic_coordinate_system)()
    await _field_edge(authenticated_context, mask_system, table, ["i"])

    def embed() -> None:
        models.Transformation.objects.create(
            kind=enums.TransformKindChoices.AFFINE.value,
            input=mask_system,
            output=image.intrinsic_coordinate_system,
            params={"affine": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]},
            organization=authenticated_context.request.organization,
        )

    await sync_to_async(embed)()

    image_system = await sync_to_async(lambda: image.intrinsic_coordinate_system)()
    result = await schema.execute(PLANS, context_value=authenticated_context, variable_values={"system": str(image_system.pk)})
    assert not result.errors, result.errors
    assert result.data["attributePlans"] == []


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_unmappable_derivation_is_not_walked(authenticated_context: HttpContext):
    """UNMAPPABLE declares no point corresponds -- discovery must not compose across it."""
    image = await seed.create_adataset(authenticated_context, "source", axes=seed.YX_AXES, shapes=[[64, 64]])
    mask = await _mask(authenticated_context, "labels", axes=seed.YX_AXES, shapes=[[64, 64]])
    await _derive(authenticated_context, mask, await sync_to_async(lambda: image.intrinsic_coordinate_system)(), kind="UNMAPPABLE", value_relation=None)
    table = await _table(authenticated_context, "objects", [{"name": "i", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"}, {"name": "area", "dtype": "DOUBLE", "role": "ATTRIBUTE"}])
    await _field_edge(authenticated_context, await sync_to_async(lambda: mask.intrinsic_coordinate_system)(), table, ["i"])

    image_system = await sync_to_async(lambda: image.intrinsic_coordinate_system)()
    result = await schema.execute(PLANS, context_value=authenticated_context, variable_values={"system": str(image_system.pk)})
    assert not result.errors, result.errors
    assert result.data["attributePlans"] == []


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_sliced_lens_hop_appears_in_the_path(authenticated_context: HttpContext):
    """A mask derived from a crop is two backward steps from the image: lens edge, then derivation."""
    image = await seed.create_adataset(authenticated_context, "source", axes=seed.YX_AXES, shapes=[[64, 64]])
    lens = await seed.create_lens(authenticated_context, image, slices=[{"axis": "y", "start": 8, "stop": 40}])
    lens_system = await sync_to_async(lambda: lens.coordinate_system)()
    mask = await _mask(authenticated_context, "crop labels", axes=seed.YX_AXES, shapes=[[32, 64]])
    await _derive(authenticated_context, mask, lens_system)
    table = await _table(authenticated_context, "objects", [{"name": "i", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"}, {"name": "area", "dtype": "DOUBLE", "role": "ATTRIBUTE"}])
    await _field_edge(authenticated_context, await sync_to_async(lambda: mask.intrinsic_coordinate_system)(), table, ["i"])

    image_system = await sync_to_async(lambda: image.intrinsic_coordinate_system)()
    result = await schema.execute(PLANS, context_value=authenticated_context, variable_values={"system": str(image_system.pk)})
    assert not result.errors, result.errors
    plans = result.data["attributePlans"]
    assert len(plans) == 1
    assert [step["inverted"] for step in plans[0]["path"]] == [True, True], "image <- lens crop <- mask, both edges walked backwards"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_registrations_never_extend_discovery(authenticated_context: HttpContext):
    """Two datasets sharing a scene's world do not correspond by that fact alone.

    A registration is a claim a scene composes; this query has no scene, so the walk never
    even stands on the SHARED system. ABLATION: drop the SHARED-side exclusions in
    `fact_paths` (or `fact_edges`' registration filter) and the foreign mask's plan
    appears here.
    """
    scene = await seed.create_scene(authenticated_context)
    plain = await seed.create_adataset(authenticated_context, "plain", axes=seed.YX_AXES, shapes=[[64, 64]])
    mask = await _mask(authenticated_context, "labels", axes=seed.YX_AXES, shapes=[[64, 64]])
    table = await _table(authenticated_context, "objects", [{"name": "i", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"}, {"name": "area", "dtype": "DOUBLE", "role": "ATTRIBUTE"}])
    await _field_edge(authenticated_context, await sync_to_async(lambda: mask.intrinsic_coordinate_system)(), table, ["i"])
    await seed.register_into_scene(authenticated_context, scene, plain)
    await seed.register_into_scene(authenticated_context, scene, mask)

    plain_system = await sync_to_async(lambda: plain.intrinsic_coordinate_system)()
    result = await schema.execute(PLANS, context_value=authenticated_context, variable_values={"system": str(plain_system.pk)})
    assert not result.errors, result.errors
    assert result.data["attributePlans"] == []


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_field_edge_is_payload_never_connectivity(authenticated_context: HttpContext):
    """A warp-field FIELD edge onto another grid must not carry discovery into that grid."""
    atlas = await seed.create_adataset(authenticated_context, "atlas", axes=seed.YX_AXES, shapes=[[64, 64]])
    mask = await _mask(authenticated_context, "atlas labels", axes=seed.YX_AXES, shapes=[[64, 64]])
    await _derive(authenticated_context, mask, await sync_to_async(lambda: atlas.intrinsic_coordinate_system)())
    table = await _table(authenticated_context, "objects", [{"name": "i", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"}, {"name": "area", "dtype": "DOUBLE", "role": "ATTRIBUTE"}])
    await _field_edge(authenticated_context, await sync_to_async(lambda: mask.intrinsic_coordinate_system)(), table, ["i"])

    probe = await seed.create_adataset(authenticated_context, "moving image", axes=seed.YX_AXES, shapes=[[64, 64]])
    probe_system = await sync_to_async(lambda: probe.intrinsic_coordinate_system)()

    def warp() -> None:
        models.Transformation.objects.create(
            kind=enums.TransformKindChoices.FIELD.value,
            input=probe_system,
            output=atlas.intrinsic_coordinate_system,
            field=probe_system,
            input_axes=["y", "x"],
            output_axes=["y", "x"],
            organization=authenticated_context.request.organization,
        )

    await sync_to_async(warp)()

    result = await schema.execute(PLANS, context_value=authenticated_context, variable_values={"system": str(probe_system.pk)})
    assert not result.errors, result.errors
    assert result.data["attributePlans"] == [], "the warp FIELD is neither a plan (pixel-grid target) nor a road to the atlas' plans"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_max_depth_limits_discovery(authenticated_context: HttpContext):
    """`maxDepth` bounds the walk exactly like coordinateGraph's: siblings are two hops away."""
    image = await seed.create_adataset(authenticated_context, "source", axes=seed.YX_AXES, shapes=[[64, 64]])
    image_system = await sync_to_async(lambda: image.intrinsic_coordinate_system)()
    for name, produced in (("nuclei", "i"), ("cytoplasm", "label_id")):
        mask = await _mask(authenticated_context, f"{name} labels", axes=seed.YX_AXES, shapes=[[64, 64]])
        await _derive(authenticated_context, mask, image_system)
        table = await _table(authenticated_context, f"{name} table", [{"name": produced, "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"}, {"name": "area", "dtype": "DOUBLE", "role": "ATTRIBUTE"}])
        await _field_edge(authenticated_context, await sync_to_async(lambda m=mask: m.intrinsic_coordinate_system)(), table, [produced])

    nuclei_system = await sync_to_async(lambda: models.ADataset.objects.get(name="nuclei labels").intrinsic_coordinate_system)()
    capped = await schema.execute(PLANS, context_value=authenticated_context, variable_values={"system": str(nuclei_system.pk), "maxDepth": 1})
    assert not capped.errors, capped.errors
    assert [plan["table"]["name"] for plan in capped.data["attributePlans"]] == ["nuclei table"], "depth 1 reaches the image, not the sibling behind it"


# --- TableColumn.references: the record-land sibling of the FIELD edge ----------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_column_references_the_table_its_values_identify(authenticated_context: HttpContext):
    """`instance_id` on the objects table is a declared foreign key into tracks.

    The FK states only *which table*: which column carries the target's row identity is
    already declared there (its single INDEX coordinate column), and restating it here
    would be a second copy of one fact, free to disagree.
    """
    tracks = await _table(
        authenticated_context,
        "tracks",
        [
            {"name": "instance_id", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"},
            {"name": "duration", "dtype": "DOUBLE", "role": "ATTRIBUTE"},
        ],
    )
    objects = await _table(
        authenticated_context,
        "tracked objects",
        [
            {"name": "i", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"},
            {"name": "instance_id", "dtype": "BIGINT", "role": "TRACK_ID", "references": tracks["id"]},
            {"name": "area", "dtype": "DOUBLE", "role": "ATTRIBUTE"},
        ],
    )

    column = next(col for col in objects["columns"] if col["name"] == "instance_id")
    assert column["references"] == {"id": tracks["id"], "name": "tracks"}

    referencing = await sync_to_async(lambda: [col.name for col in models.TableDataset.objects.get(pk=tracks["id"]).referenced_by.all()])()
    assert referencing == ["instance_id"], "the reverse relation answers 'who keys into me'"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_coordinate_column_cannot_reference(authenticated_context: HttpContext):
    """A coordinate places the row in this table's own space; it does not point elsewhere."""
    tracks = await _table(authenticated_context, "tracks", [{"name": "instance_id", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"}, {"name": "duration", "dtype": "DOUBLE", "role": "ATTRIBUTE"}])
    store = await _parquet(authenticated_context, "coord-ref")

    result = await schema.execute(
        CREATE_TABLE,
        context_value=authenticated_context,
        variable_values={"input": {"name": "bad", "data": str(store.pk), "columns": [{"name": "i", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX", "references": tracks["id"]}]}},
    )
    assert result.errors, "a COORDINATE column with a reference must be refused"
    assert "does not point elsewhere" in str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_composite_keyed_table_cannot_be_referenced(authenticated_context: HttpContext):
    """A single value cannot identify a row of a (t, i)-keyed table: refuse, don't guess."""
    timelapse = await _table(
        authenticated_context,
        "per-frame objects",
        [
            {"name": "t", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "TIME"},
            {"name": "i", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"},
            {"name": "area", "dtype": "DOUBLE", "role": "ATTRIBUTE"},
        ],
    )
    store = await _parquet(authenticated_context, "composite-ref")

    result = await schema.execute(
        CREATE_TABLE,
        context_value=authenticated_context,
        variable_values={"input": {"name": "bad", "data": str(store.pk), "columns": [{"name": "object_ref", "dtype": "BIGINT", "role": "ID", "references": timelapse["id"]}]}},
    )
    assert result.errors, "a composite-keyed target must be refused"
    assert "exactly one INDEX axis" in str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_degenerate_table_cannot_be_referenced(authenticated_context: HttpContext):
    """The synthetic `object` axis enumerates rows with no backing column to look a value up in."""
    degenerate = await _table(authenticated_context, "measurements", [{"name": "area", "dtype": "DOUBLE", "role": "ATTRIBUTE"}])
    store = await _parquet(authenticated_context, "degenerate-ref")

    result = await schema.execute(
        CREATE_TABLE,
        context_value=authenticated_context,
        variable_values={"input": {"name": "bad", "data": str(store.pk), "columns": [{"name": "row_ref", "dtype": "BIGINT", "role": "ID", "references": degenerate["id"]}]}},
    )
    assert result.errors, "a synthetic row enumeration must be refused as a reference target"
    assert "synthetic row enumeration" in str(result.errors[0])


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_referenced_table_cannot_be_deleted(authenticated_context: HttpContext):
    """PROTECT, for the same reason a warp field is PROTECTed: deleting tracks out from
    under a column keying it would orphan the meaning of every value in that column."""
    tracks = await _table(authenticated_context, "tracks", [{"name": "instance_id", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"}, {"name": "duration", "dtype": "DOUBLE", "role": "ATTRIBUTE"}])
    objects = await _table(
        authenticated_context,
        "tracked objects",
        [
            {"name": "i", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"},
            {"name": "instance_id", "dtype": "BIGINT", "role": "TRACK_ID", "references": tracks["id"]},
        ],
    )

    def delete_target() -> None:
        models.TableDataset.objects.get(pk=tracks["id"]).delete()

    with pytest.raises(ProtectedError):
        await sync_to_async(delete_target)()

    def delete_in_order() -> None:
        models.TableDataset.objects.get(pk=objects["id"]).delete()
        models.TableDataset.objects.get(pk=tracks["id"]).delete()

    await sync_to_async(delete_in_order)()
