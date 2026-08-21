"""`axes`: a table's space, stated, with what identifies each axis carried on the axis.

Until 2026-08-20 a table said this in two sibling lists. `keyedBy` named sources and *not*
the axes they keyed -- the pairing was recovered inside `write_key_edges` by subtracting the
source's axes from the table's, which is correct and invisible -- while `Column.references`
named a table and lived somewhere else entirely. Both are one question, asked of an axis:
**what are these positions?** So both are now `IdentificationInput`, carried per axis, in a
list, and the sparse path uses the same union (`core/inputs/identification.py`).

Three things fall out, and each has a test below:

* the pairing is stated, so a source that keys a different axis than the caller believed is
  refused naming both halves rather than "one place holds one id";
* fan-in is expressible -- one axis, n sources -- which `write_key_edges` always supported
  and the singular sparse form could not say;
* "a table with no coordinate columns cannot be keyed" stops being a runtime check, because
  there is no axis to hang an identification on. See `test_keyed_by.py` for that one.
"""

import pytest
from asgiref.sync import sync_to_async
from kante.context import HttpContext

from core import models
from mikro_server.schema import schema
from tests import seed

CREATE = """
mutation Create($input: CreateTableDatasetInput!) {
  createTableDataset(input: $input) {
    id
    columns { name role order references { id } }
    coordinateSystem { axes { name type order } }
  }
}
"""

_LOCALIZATIONS = [
    {"name": "y", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE", "unit": "nanometer"},
    {"name": "x", "dtype": "DOUBLE", "role": "COORDINATE", "axisType": "SPACE", "unit": "nanometer"},
    {"name": "photons", "dtype": "DOUBLE", "role": "ATTRIBUTE"},
]


async def _parquet(ctx: HttpContext, key: str, columns: list[dict]) -> models.ParquetStore:
    """A finished store carrying exactly the columns these tests declare over."""
    return await sync_to_async(models.ParquetStore.objects.create)(
        path=f"s3://parquet/{key}", bucket="parquet", key=key, organization=ctx.request.organization, populated=True,
        columns=[{"name": name, "type": dtype, "nullable": True} for name, dtype in seed.split_declaration(columns)[0]],
    )


async def _create(ctx: HttpContext, name: str, columns: list[dict], axes: list[dict] | None = None):
    store = await _parquet(ctx, name.replace(" ", "-"), columns)
    payload = {
        "name": name,
        "data": str(store.pk),
        **({"axes": seed.split_payload(columns)["axes"]} if axes is None else {"axes": axes}),
        "columns": seed.split_payload(columns)["columns"],
    }
    return await schema.execute(CREATE, context_value=ctx, variable_values={"input": payload})


# --- the space is stated, not filtered out of the columns --------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_the_axis_order_is_the_axes_list_not_the_column_order(authenticated_context: HttpContext):
    """`Column.order` is the column declaration; `Axis.order` is the axes list. Independent.

    They used to be one thing -- the axes were the coordinate columns in whatever order they
    happened to appear -- which is the same order for every caller who thought about it and an
    accident for everyone else. It matters: x is the *last* spatial axis and y the one before
    it, by position and never by name, so a space in the wrong order renders mirrored rather
    than failing.
    """
    result = await _create(
        authenticated_context,
        "molecules",
        _LOCALIZATIONS,
        axes=[{"column": "x", "type": "SPACE", "unit": "nanometer"}, {"column": "y", "type": "SPACE", "unit": "nanometer"}],
    )
    assert not result.errors, result.errors
    table = result.data["createTableDataset"]

    assert [axis["name"] for axis in table["coordinateSystem"]["axes"]] == ["x", "y"], "the axes list"
    assert [column["name"] for column in table["columns"]] == ["y", "x", "photons"], "the columns list"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_column_left_out_of_the_axes_is_an_ordinary_undeclared_column(authenticated_context: HttpContext):
    """There is no such thing as "a coordinate column missing from `axes`" any more.

    Before 3b a column said its own role, so `axes` and `columns` could disagree about which
    columns were the space and it was worth refusing. Now `axes` is the *only* thing that makes
    a column a coordinate: a column left out is simply a column, inferred from the file as an
    ATTRIBUTE. Two declarations that cannot disagree do not need a check.
    """
    result = await _create(
        authenticated_context, "molecules", _LOCALIZATIONS,
        axes=[{"column": "y", "type": "SPACE", "unit": "nanometer"}],
    )

    assert not result.errors, result.errors
    table = result.data["createTableDataset"]
    assert [axis["name"] for axis in table["coordinateSystem"]["axes"]] == ["y"]
    roles = {column["name"]: column["role"] for column in table["columns"]}
    assert roles == {"y": "COORDINATE", "x": "ATTRIBUTE", "photons": "ATTRIBUTE"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_axis_declared_twice_is_refused(authenticated_context: HttpContext):
    result = await _create(
        authenticated_context, "molecules", _LOCALIZATIONS, axes=[{"column": "y", "type": "SPACE"}, {"column": "y", "type": "SPACE"}, {"column": "x", "type": "SPACE"}]
    )

    assert result.errors
    assert "declares the axis ['y'] more than once" in str(result.errors[0])


# --- identification, carried on the axis -------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_table_axis_may_be_identified_by_the_table_it_enumerates(authenticated_context: HttpContext):
    """Item 7's product space, said the way the sparse path already said it.

    An INDEX axis' values are already ids, so naming the table it enumerates is not a second
    map -- it is what the enumeration is *of*. It landed on `Column.references` before and
    still does; what changed is that the caller says it on the axis, in the same field that
    names a mask, instead of on a column in a different vocabulary.
    """
    cells = await _create(
        authenticated_context,
        "cells",
        [
            {"name": "cell_id", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"},
            {"name": "area", "dtype": "DOUBLE", "role": "ATTRIBUTE"},
        ],
    )
    assert not cells.errors, cells.errors
    cell_table = cells.data["createTableDataset"]["id"]

    contacts = await _create(
        authenticated_context,
        "contacts",
        [
            {"name": "nucleus_id", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"},
            {"name": "cell_id", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"},
            {"name": "overlap", "dtype": "DOUBLE", "role": "ATTRIBUTE"},
        ],
        axes=[
            {"column": "nucleus_id", "type": "INDEX"},
            {"column": "cell_id", "type": "INDEX", "identifiedBy": [{"kind": "TABLE", "table": cell_table}]},
        ],
    )
    assert not contacts.errors, contacts.errors

    references = {c["name"]: c["references"] for c in contacts.data["createTableDataset"]["columns"]}
    assert references["cell_id"] == {"id": cell_table}, "it lands on the column, as it always did"
    assert references["nucleus_id"] is None


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_table_identification_on_a_space_axis_is_refused(authenticated_context: HttpContext):
    """A position in nanometres and a row id are different things.

    The narrowing item 7 argued for, and it has to be written by hand: `TableAxisInput`
    carries the identification and the *column* carries the type, so nothing structural stops
    a SPACE axis being declared to enumerate a table's rows.
    """
    cells = await _create(
        authenticated_context,
        "cells",
        [{"name": "cell_id", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"}],
    )
    assert not cells.errors, cells.errors

    result = await _create(
        authenticated_context,
        "molecules",
        _LOCALIZATIONS,
        axes=[
            {"column": "y", "type": "SPACE", "unit": "nanometer"},
            {"column": "x", "type": "SPACE", "unit": "nanometer", "identifiedBy": [{"kind": "TABLE", "table": cells.data["createTableDataset"]["id"]}]},
        ],
    )

    assert result.errors
    message = str(result.errors[0])
    assert "is not an INDEX axis" in message
    assert "positions rather than ids" in message
    assert not await sync_to_async(models.TableDataset.objects.filter(name="molecules").exists)()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_axis_identified_by_two_tables_is_refused(authenticated_context: HttpContext):
    """Fan-in is only meaningful for the kinds that author an edge.

    Two masks keying one axis are two edges, each standing on its own. Two *tables* would be
    two different answers to what a position along the axis is -- and one column carries one
    `references`, so only one of them could even be recorded.
    """
    first = await _create(
        authenticated_context, "cells", [{"name": "cell_id", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"}]
    )
    second = await _create(
        authenticated_context, "nuclei", [{"name": "nucleus_id", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"}]
    )
    assert not first.errors and not second.errors

    result = await _create(
        authenticated_context,
        "contacts",
        [{"name": "thing_id", "dtype": "BIGINT", "role": "COORDINATE", "axisType": "INDEX"}],
        axes=[
            {
                "column": "thing_id",
                "type": "INDEX",
                "identifiedBy": [
                    {"kind": "TABLE", "table": first.data["createTableDataset"]["id"]},
                    {"kind": "TABLE", "table": second.data["createTableDataset"]["id"]},
                ],
            }
        ],
    )

    assert result.errors
    message = str(result.errors[0])
    assert "identified by more than one table" in message
    assert "two masks may key one axis" in message, "say which fan-in is meaningful"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_an_axis_with_no_identification_is_ordinary(authenticated_context: HttpContext):
    """`identifiedBy` defaults to empty, and that is the common case.

    A localization table's `x` axis is identified by nothing: its values are positions, and a
    position is not an id of anything. The sparse path refuses an empty list because every
    axis of a matrix is positions-and-nothing-else; a table's is not, which is why that check
    belongs to the caller that means it rather than to the shared splitter.
    """
    result = await _create(authenticated_context, "molecules", _LOCALIZATIONS)

    assert not result.errors, result.errors
    axes = result.data["createTableDataset"]["coordinateSystem"]["axes"]
    assert [axis["name"] for axis in axes] == ["y", "x"]
