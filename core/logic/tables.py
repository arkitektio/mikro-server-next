"""DuckDB access to the parquet behind a store.

Was shared by the legacy ``Table`` GraphQL type and its virtual row/cell resolvers. Those
are gone; what remains is the store-level half, which ``core.mutations.table_dataset`` uses
to validate a declared schema against the parquet a caller actually uploaded -- a DESCRIBE
over S3, never a read of the values.

That line was briefly crossed, for a picker that wanted a class column's distinct values and a
measure column's range. It was put back: the client already holds an ``accessGrant`` for the
same parquet and is reading it anyway, so a scan here buys nothing it could not do locally and
costs this server a query whose price is set by someone else's row count.
"""

from core.duck import get_current_duck
from datalayer.datalayer import get_current_datalayer


def parquet_source_for_store(store) -> str:
    """The s3 URL of a parquet store, whichever model references it."""
    datalayer = get_current_datalayer()
    return f"s3://{datalayer.get_bucket_config('parquet').bucket}/{store.key}"


def columns_for_store(store) -> list[tuple]:
    """The DESCRIBE rows (name, type, nullable, key, default, extra) of a parquet store's file."""
    duck = get_current_duck()
    sql = f"""
        DESCRIBE SELECT * FROM read_parquet('{parquet_source_for_store(store)}');
        """
    return duck.sql(sql).fetchall()
