"""
Опциональный слой GraphRAG для gateway (Neo4j + fallback).

Использует memory37-graph, если пакет установлен и заданы параметры подключения.
"""

from __future__ import annotations

import logging
from typing import Any

try:  # pragma: no cover - внешняя зависимость
    from memory37_graph import (
        GraphClient,
        GraphConfig,
        GraphIngest,
        GraphRagQueries,
        KnowledgeVersionRef,
        SceneGraphContextRequest,
    )
    from memory37 import KnowledgeVersionRegistry, KnowledgeVersion
except Exception:  # pragma: no cover
    GraphClient = None  # type: ignore
    GraphConfig = None  # type: ignore
    GraphIngest = None  # type: ignore
    GraphRagQueries = None  # type: ignore
    KnowledgeVersionRef = None  # type: ignore
    SceneGraphContextRequest = None  # type: ignore
    KnowledgeVersionRegistry = None  # type: ignore
    KnowledgeVersion = None  # type: ignore

from .config import Settings

logger = logging.getLogger(__name__)


def init_graph_service(settings: Settings) -> Any:
    """Инициализирует GraphRAG сервис, если зависимости и окружение заданы."""

    if GraphClient is None:
        logger.info("memory37-graph не установлен, GraphRAG отключён")
        return None
    if not settings.neo4j_uri or not settings.neo4j_user or not settings.neo4j_password:
        logger.info("NEO4J_* не заданы, GraphRAG отключён")
        return None

    registry = KnowledgeVersionRegistry()
    registry.register(KnowledgeVersion(id="kv_default", semver=settings.api_version, kind="lore", status="latest"))

    cfg = GraphConfig(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
    )
    client = GraphClient(config=cfg, version_registry=registry)
    client.run_default_migrations()
    ingest = GraphIngest(graph_client=client, version_registry=registry)
    queries = GraphRagQueries(graph_client=client, ingest=ingest)

    return type("GraphService", (), {"client": client, "ingest": ingest, "queries": queries})
