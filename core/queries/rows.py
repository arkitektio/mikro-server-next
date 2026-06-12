from core import models, types, enums, filters as f, pagination as p, scalars
import strawberry
from typing import Union
from itertools import chain
from core.duck import get_current_duck
from datalayer.datalayer import get_current_datalayer
from core.scoping import get_for_org


def parseRow(row) -> scalars.MetricMap:
    row = []
    parsed_row = []
    for idx, value in enumerate(row):
        if isinstance(value, bytes):
            try:
                value = value.decode("utf-8")
            except Exception:
                value = str(value)
        elif isinstance(value, memoryview):
            try:
                value = value.tobytes().decode("utf-8")
            except Exception:
                value = str(value)
        elif isinstance(value, list):
            try:
                value = [float(x) for x in value]
            except Exception:
                value = [str(x) for x in value]
        elif isinstance(value, dict):
            try:
                value = {str(k): float(v) for k, v in value.items()}
            except Exception:
                value = {str(k): str(v) for k, v in value.items()}

        elif isinstance(value, float):
            if value == float("inf") or value == float("-inf") or value != value:
                value = str(value)
        elif isinstance(value, datetime.date):
            value = value.isoformat()

        else:
            value = str(value)

        parsed_row.append(value)

    return parsed_row


def rows(
    info,
    table: strawberry.ID,
    filters: f.RowFilter | None = None,
    pagination: p.TablePaginationInput | None = None,
) -> list[scalars.MetricMap]:
    if filters is None:
        filters = f.RowFilter()
    if pagination is None:
        pagination = p.TablePaginationInput()

    table = get_for_org(models.Table, info, id=table)

    x = get_current_duck()
    datalayer = get_current_datalayer()

    sql = f"""
        SELECT * FROM read_parquet('s3://{datalayer.get_bucket_config("parquet").bucket}/{table.store.key}')
        """

    if filters.clause:
        sql += f"""
        {filters.clause}
        """

    sql += f"""
        LIMIT {pagination.limit}
        OFFSET {pagination.offset};
    """

    result = x.connection.sql(sql).df()

    return result.apply(parseRow, axis=1).tolist()
