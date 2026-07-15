"""DuckDB access to the parquet data behind Table rows, columns and cells.

Shared by the Table GraphQL type and the virtual TableRow/TableCell
resolvers so the parquet SQL lives in one place.
"""

from typing import Any

from core import models
from core.duck import get_current_duck
from datalayer.datalayer import get_current_datalayer


def parquet_source_for_store(store) -> str:
    """The s3 URL of a parquet store, whichever model references it."""
    datalayer = get_current_datalayer()
    return f"s3://{datalayer.get_bucket_config('parquet').bucket}/{store.key}"


def parquet_source(table: models.Table) -> str:
    """The s3 URL of the parquet file backing this table."""
    return parquet_source_for_store(table.store)


def columns_for_store(store) -> list[tuple]:
    """The DESCRIBE rows (name, type, nullable, key, default, extra) of a parquet store's file."""
    duck = get_current_duck()
    sql = f"""
        DESCRIBE SELECT * FROM read_parquet('{parquet_source_for_store(store)}');
        """
    return duck.connection.sql(sql).fetchall()


def columns(table: models.Table) -> list[tuple]:
    """The DESCRIBE rows (name, type, nullable, key, default, extra) of the table's parquet file."""
    return columns_for_store(table.store)


def row_count(table: models.Table) -> int:
    """The number of rows in the table's parquet file."""
    duck = get_current_duck()
    sql = f"""
        SELECT COUNT(*) FROM read_parquet('{parquet_source(table)}');
        """
    return duck.connection.sql(sql).fetchall()[0][0]


def row_values(table: models.Table, row_id: int) -> list[Any]:
    """The raw values of one row of the table's parquet file."""
    duck = get_current_duck()
    sql = f"""
        SELECT * FROM read_parquet('{parquet_source(table)}') LIMIT 1 OFFSET {int(row_id)};
        """
    rows = duck.connection.sql(sql).fetchall()
    if not rows:
        raise ValueError(f"Table {table.id} has no row {row_id}")
    return list(rows[0])
