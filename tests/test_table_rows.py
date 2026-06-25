"""The virtual tableRows/tableCells/tableRow/tableCell queries.

These resolvers previously referenced the Python builtin ``id`` (and the
TableCell constructor was called without its required fields), so every call
crashed. The parquet access now lives in core.logic.tables; it is mocked here
because the test stack has no DuckDB-reachable object store.
"""

from unittest.mock import patch

import pytest

from core.models import Dataset, Table
from kante.context import HttpContext
from mikro_server.schema import schema

# DESCRIBE-shaped column tuples: (name, type, nullable, key, default, extra)
COLUMNS = [
    ("intensity", "DOUBLE", "YES", None, None, None),
    ("label", "VARCHAR", "YES", None, None, None),
]


def _row_values(table: Table, row_id: int) -> list:
    return [float(row_id), f"cell-{row_id}"]


async def _seed_table(ctx: HttpContext) -> Table:
    dataset = await Dataset.objects.acreate(
        name="DS",
        creator=ctx.request.user,
        organization=ctx.request.organization,
        membership=ctx.request.membership,
    )
    return await Table.objects.acreate(
        name="Measurements",
        dataset=dataset,
        creator=ctx.request.user,
        organization=ctx.request.organization,
    )


def _mocked_tables() -> tuple:
    return (
        patch("core.logic.tables.row_count", return_value=3),
        patch("core.logic.tables.columns", return_value=COLUMNS),
        patch("core.logic.tables.row_values", side_effect=_row_values),
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_table_rows(db: None, authenticated_context: HttpContext) -> None:
    """tableRows enumerates rows with pagination and resolves values per row."""
    table = await _seed_table(authenticated_context)

    query = """
        query Rows($table: ID!, $pagination: OffsetPaginationInput) {
            tableRows(table: $table, pagination: $pagination) {
                id
                rowId
                name
                values
                columns { name }
            }
        }
    """
    p1, p2, p3 = _mocked_tables()
    with p1, p2, p3:
        result = await schema.execute(
            query,
            context_value=authenticated_context,
            variable_values={"table": str(table.id), "pagination": {"offset": 1, "limit": 2}},
        )

    assert not result.errors, result.errors
    rows = result.data["tableRows"]
    assert [r["rowId"] for r in rows] == [1, 2]
    assert rows[0]["id"] == f"{table.id}-1"
    assert rows[0]["name"] == "Row 1"
    assert rows[0]["values"] == [1.0, "cell-1"]
    assert [c["name"] for c in rows[0]["columns"]] == ["intensity", "label"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_table_cells(db: None, authenticated_context: HttpContext) -> None:
    """tableCells flattens rows x columns row-major and carries the cell values."""
    table = await _seed_table(authenticated_context)

    query = """
        query Cells($table: ID!, $pagination: OffsetPaginationInput) {
            tableCells(table: $table, pagination: $pagination) {
                id
                rowId
                columnId
                value
                name
            }
        }
    """
    p1, p2, p3 = _mocked_tables()
    with p1, p2, p3:
        result = await schema.execute(
            query,
            context_value=authenticated_context,
            variable_values={"table": str(table.id), "pagination": {"offset": 1, "limit": 3}},
        )

    assert not result.errors, result.errors
    cells = result.data["tableCells"]
    # 3 rows x 2 columns row-major = (0,0)(0,1)(1,0)(1,1)(2,0)(2,1); offset 1 limit 3
    assert [(c["rowId"], c["columnId"]) for c in cells] == [(0, 1), (1, 0), (1, 1)]
    assert cells[0]["value"] == "cell-0"
    assert cells[1]["value"] == 1.0
    assert cells[0]["name"] == "label"
    assert cells[1]["id"] == f"{table.id}-1-0"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_table_row_and_cell_by_compound_id(db: None, authenticated_context: HttpContext) -> None:
    """The singular tableRow/tableCell queries resolve compound IDs."""
    table = await _seed_table(authenticated_context)

    p1, p2, p3 = _mocked_tables()
    with p1, p2, p3:
        result = await schema.execute(
            """
            query Get($row: ID!, $cell: ID!) {
                tableRow(id: $row) { id rowId values }
                tableCell(id: $cell) { id rowId columnId value }
            }
            """,
            context_value=authenticated_context,
            variable_values={"row": f"{table.id}-2", "cell": f"{table.id}-2-1"},
        )

    assert not result.errors, result.errors
    assert result.data["tableRow"]["rowId"] == 2
    assert result.data["tableRow"]["values"] == [2.0, "cell-2"]
    assert result.data["tableCell"]["value"] == "cell-2"
    assert result.data["tableCell"]["columnId"] == 1
