"""
Каркас GraphRAG-слоя для Memory37 (Neo4j или in-memory fallback).

MVP реализует in-memory граф для разработки и unit-тестов. Подключение
к Neo4j возможно при наличии драйвера, но не является обязательным для
работы функциональных тестов Wave B.
"""

from .client import GraphClient, GraphConfig, KnowledgeVersionRef
from .ingest import GraphIngest
from .queries import GraphRagQueries, SceneGraphContext, SceneGraphContextRequest

__all__ = [
    "GraphClient",
    "GraphConfig",
    "KnowledgeVersionRef",
    "GraphIngest",
    "GraphRagQueries",
    "SceneGraphContext",
    "SceneGraphContextRequest",
]
