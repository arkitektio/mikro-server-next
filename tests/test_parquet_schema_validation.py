"""Validating a declared table schema against the parquet actually uploaded.

`createTableDataset(validate_schema: true)` DESCRIBEs the caller's parquet through DuckDB and
refuses a column the file does not have. The whole path raised `AttributeError: 'DuckLayer'
object has no attribute 'sql'` before reaching DuckDB: `columns_for_store` was written against
a facade method the class never grew, and nothing exercised it -- `test_table_datasets` covers
the placement and column-mapping behaviour but always leaves `validate_schema` off.

So the tests here are deliberately split. The delegation runs against a **real** DuckDB
connection, because a stub asserting `duck.sql` was called would have passed on the broken code
just as happily. The store-to-SQL wiring is stubbed, because DuckDB reads S3 over its own HTTP
client, which `moto` (a botocore patch) does not intercept -- that half is only testable
against a live object store.
"""

import pytest

from core.duck import DuckLayer
from core.logic import tables as tables_logic


def test_the_duck_layer_offers_the_query_method_its_callers_use():
    """A real query through the facade, not an assertion that a mock was called.

    `columns_for_store` calls `duck.sql(...)`. That the class *has* `connection` is not the
    contract its callers were written to, and the gap between the two was an exception on every
    schema validation.
    """
    layer = DuckLayer()

    assert layer.sql("SELECT 42 AS answer;").fetchall() == [(42,)]


def test_the_facade_runs_on_the_s3_configured_connection():
    """The point of the facade: the secret setup stays an implementation detail.

    A caller reaching through `.connection` itself would work too, but then every call site
    owns the knowledge that a connection needs configuring before it can see S3.
    """
    layer = DuckLayer()

    assert layer.sql("SELECT 1;").fetchall() == [(1,)]
    assert layer.connection is layer.connection, "one configured connection per layer, not one per query"


def test_a_store_is_described_rather_than_read(monkeypatch):
    """The validation is a DESCRIBE over the parquet, never a scan of its values.

    A table dataset can be very large and the mutation only needs its column names and types,
    so reading rows to learn the schema would make creation cost the size of the data.
    """
    captured: list[str] = []

    class FakeRelation:
        def fetchall(self):
            return [("object_id", "BIGINT", "YES", None, None, None)]

    class FakeDuck:
        def sql(self, query: str):
            captured.append(query)
            return FakeRelation()

    monkeypatch.setattr(tables_logic, "get_current_duck", lambda: FakeDuck())
    monkeypatch.setattr(tables_logic, "parquet_source_for_store", lambda store: "s3://tables/abc123")

    assert tables_logic.columns_for_store(object()) == [("object_id", "BIGINT", "YES", None, None, None)]

    (query,) = captured
    assert "DESCRIBE SELECT * FROM read_parquet('s3://tables/abc123')" in query
    assert "LIMIT" not in query.upper(), "a DESCRIBE needs no row limit -- it reads no rows"


@pytest.mark.django_db
def test_the_parquet_source_names_the_configured_bucket(settings):
    """The URL DuckDB is handed is built from the datalayer's own bucket configuration."""

    class FakeStore:
        key = "abc123"

    assert tables_logic.parquet_source_for_store(FakeStore()).startswith("s3://")
    assert tables_logic.parquet_source_for_store(FakeStore()).endswith("/abc123")

