from collections import deque

from memory37.vector_store import PgVectorStore, VectorRecord


class FakeCursor:
    def __init__(self, queries: list[tuple[str, tuple | list | None]], results: list[tuple] | None = None) -> None:
        self._collector = queries
        self._results = deque(results or [])

    def execute(self, query, params=None):
        self._collector.append((str(query), params))

    def fetchall(self):
        return list(self._results)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self, results: list[tuple] | None = None) -> None:
        self.queries: list[tuple[str, tuple | list | None]] = []
        self._results = results or []
        self.committed = False
        self.closed = False

    def cursor(self):
        return FakeCursor(self.queries, self._results)

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def test_pgvector_store_upsert_executes_insert_sql(monkeypatch) -> None:
    connection = FakeConnection()

    def factory():  # noqa: D401
        return connection

    store = PgVectorStore(factory, table="test_vectors", dimension=3)
    records = [
        VectorRecord(item_id="kn_1", vector=[0.1, 0.2, 0.3], metadata={"domain": "scene"}),
        VectorRecord(item_id="kn_2", vector=[0.4, 0.5, 0.6], metadata={"domain": "npc"}),
    ]

    store.upsert(records)

    queries = connection.queries
    assert any("CREATE TABLE IF NOT EXISTS" in q for q, _ in queries)
    assert any("INSERT INTO" in q for q, _ in queries)
    assert connection.committed
    assert connection.closed


def test_pgvector_store_query_returns_records(monkeypatch) -> None:
    result_rows = [("kn_1", [0.1, 0.2, 0.3], {"domain": "scene"})]
    connection = FakeConnection(result_rows)

    def factory():
        return connection

    store = PgVectorStore(factory, table="test_vectors", dimension=3)
    store._schema_initialized = True  # skip DDL in test

    records = store.query([0.1, 0.2, 0.3], top_k=5)

    assert len(records) == 1
    assert records[0].item_id == "kn_1"
    assert records[0].metadata["domain"] == "scene"
