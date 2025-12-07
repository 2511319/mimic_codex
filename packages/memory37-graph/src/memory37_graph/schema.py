"""
Декларативное описание базовых labels/relationships для GraphRAG.

Используется как справочник и для построения миграций. В MVP только
фиксирует строковые константы.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


LABELS = [
    "KnowledgeRoot",
    "Location",
    "NPC",
    "Faction",
    "Quest",
    "Item",
    "Event",
    "Concept",
    "Episode",
    "Party",
]

REL_TYPES = [
    "RELATIONSHIP",
    "MEMBER_OF",
    "LOCATED_IN",
    "OWNS",
    "INVOLVED_IN",
    "BLOCKS",
    "UNLOCKS",
    "CAUSES",
    "NEXT_EPISODE",
    "APPEARED_IN",
    "ABOUT",
    "HAS_TAG",
]


@dataclass
class GraphNode:
    id: str
    type: str
    knowledge_version_id: str
    properties: dict
    expires_at: str | None = None


@dataclass
class GraphRelation:
    from_id: str
    to_id: str
    type: str
    knowledge_version_id: str
    properties: dict
    expires_at: str | None = None


@dataclass
class GraphFact:
    """Структурированное описание узла и его связей."""

    id: str
    type: str
    knowledge_version_id: str
    properties: dict
    expires_at: str | None = None
    relations: list[GraphRelation] | None = None


def validate_label(label: str) -> str:
    if label not in LABELS:
        raise ValueError(f"Unsupported label '{label}'")
    return label


def validate_rel_type(rel_type: str) -> str:
    if rel_type not in REL_TYPES:
        raise ValueError(f"Unsupported relationship type '{rel_type}'")
    return rel_type


def default_constraints() -> Iterable[str]:
    """Набор базовых constraint/migration выражений (Cypher)."""

    yield "CREATE CONSTRAINT IF NOT EXISTS FOR (n:KnowledgeRoot) REQUIRE n.version_id IS UNIQUE"
    for label in LABELS:
        yield (
            f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) "
            "REQUIRE (n.id, n.knowledge_version_id) IS UNIQUE"
        )
