from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable

from memory37.versioning import KnowledgeVersionRegistry

try:  # pragma: no cover - optional Neo4j
    import neo4j  # type: ignore
except Exception:  # pragma: no cover
    neo4j = None  # type: ignore


@dataclass
class GraphConfig:
    uri: str
    user: str
    password: str
    database: str | None = None


@dataclass
class KnowledgeVersionRef:
    alias: str | None = None
    version_id: str | None = None


class GraphSession:
    """Простейшая сессия графа с версионным контекстом."""

    def __init__(self, version_id: str, run_fn: Callable[[str, dict[str, Any]], Iterable[dict[str, Any]]]) -> None:
        self.version_id = version_id
        self._run_fn = run_fn

    def run(self, cypher: str, parameters: dict[str, Any] | None = None) -> Iterable[dict[str, Any]]:
        params = parameters or {}
        params.setdefault("version_id", self.version_id)
        return self._run_fn(cypher, params)


class GraphClient:
    """
    Обёртка над Neo4j-драйвером с graceful fallback на in-memory.

    Если драйвер недоступен или не настроен, клиент продолжит работать на
    in-memory слое, достаточном для unit-тестов и локальной разработки.
    """

    def __init__(
        self,
        config: GraphConfig | None,
        version_registry: KnowledgeVersionRegistry,
    ) -> None:
        self._config = config
        self._version_registry = version_registry
        self._driver = self._init_driver(config)
        self._memory_runs: list[tuple[str, dict[str, Any]]] = []  # для тестов

    def _init_driver(self, config: GraphConfig | None):  # pragma: no cover - внешняя зависимость
        if config is None or neo4j is None:
            return None
        return neo4j.GraphDatabase.driver(config.uri, auth=(config.user, config.password))

    def resolve_version_id(self, ref: KnowledgeVersionRef) -> str:
        return self._version_registry.get_version_id(alias=ref.alias, version_id=ref.version_id)

    @contextlib.contextmanager
    def session(self, ref: KnowledgeVersionRef) -> GraphSession:
        version_id = self.resolve_version_id(ref)
        if self._driver:
            def _run(cypher: str, params: dict[str, Any]) -> Iterable[dict[str, Any]]:
                with self._driver.session(database=self._config.database if self._config else None) as sess:
                    result = sess.run(cypher, params)
                    return [record.data() for record in result]

            yield GraphSession(version_id, _run)
        else:
            def _run_memory(cypher: str, params: dict[str, Any]) -> Iterable[dict[str, Any]]:
                # Для MVP просто фиксируем вызовы, чтобы их можно было читать в GraphIngest/Queries.
                self._memory_runs.append((cypher, params))
                return []

            yield GraphSession(version_id, _run_memory)

    def close(self) -> None:  # pragma: no cover - внешняя зависимость
        if self._driver:
            self._driver.close()

    def has_driver(self) -> bool:
        return self._driver is not None

    def run_default_migrations(self) -> None:
        """Создаёт базовые индексы/констрейнты при наличии Neo4j."""

        if not self._driver or neo4j is None:
            return
        stmts = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:KnowledgeRoot) REQUIRE n.version_id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Location) REQUIRE (n.id, n.knowledge_version_id) IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:NPC) REQUIRE (n.id, n.knowledge_version_id) IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Faction) REQUIRE (n.id, n.knowledge_version_id) IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Quest) REQUIRE (n.id, n.knowledge_version_id) IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Item) REQUIRE (n.id, n.knowledge_version_id) IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Event) REQUIRE (n.id, n.knowledge_version_id) IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Concept) REQUIRE (n.id, n.knowledge_version_id) IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Episode) REQUIRE (n.id, n.knowledge_version_id) IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Party) REQUIRE (n.id, n.knowledge_version_id) IS UNIQUE",
        ]
        with self._driver.session(database=self._config.database if self._config else None) as session:
            for stmt in stmts:
                session.run(stmt)
            session.run(
                """
                MERGE (k:KnowledgeRoot {version_id:$vid})
                ON CREATE SET k.created_at=$now
                """,
                vid="kv_default",
                now=datetime.utcnow().isoformat(),
            )
