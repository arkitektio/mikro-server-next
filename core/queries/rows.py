
from core import models, types, enums, filters as f, pagination as p, age, scalars
import strawberry
from typing import Union
from itertools import chain
from core.duck import get_current_duck



def rows(info, table: strawberry.ID, filters: f.TableFilter | None = None, pagination: p.TablePaginationInput | None = None) -> list[scalars.MetricMap]:
    if filters is None:
        filters = f.TableFilter()
    if pagination is None:
        pagination = p.TablePaginationInput()


    table = models.Table.objects.get(id=table)

    print("xxx")
    x = get_current_duck()


    sql =  f"""
        SELECT * FROM {table.store.duckdb_string}
        LIMIT {pagination.limit}
        OFFSET {pagination.offset};
    """
    print(sql)
    



    result = x.connection.sql(sql).df()
    
    return result.to_dict(orient='records')


