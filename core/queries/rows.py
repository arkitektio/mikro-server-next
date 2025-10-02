from core import models, types, enums, filters as f, pagination as p, scalars
import strawberry
from typing import Union
from itertools import chain
from core.duck import get_current_duck


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

    table = models.Table.objects.get(id=table)

    x = get_current_duck()

    sql = f"""
        SELECT * FROM {table.store.duckdb_string}
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
