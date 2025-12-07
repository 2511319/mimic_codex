"""
TTL utilities and cleanup scheduler hints.

В MVP реализовано:
- конфиг TTL по доменам
- функция cleanup для in-memory и Neo4j
- примеры cron/APOC для удаления просроченных узлов/связей
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class TTLConfig:
    episode_days: int = 180
    npc_relation_days: int = 180
    quest_relation_days: int = 365


def apoc_cleanup_snippets() -> Dict[str, str]:
    return {
        "delete_nodes":
        """
        CALL apoc.periodic.repeat(
          'cleanup_nodes',
          'MATCH (n) WHERE n.expires_at IS NOT NULL AND datetime(n.expires_at) < datetime() DETACH DELETE n',
          3600
        )
        """,
        "delete_rels":
        """
        CALL apoc.periodic.repeat(
          'cleanup_rels',
          'MATCH ()-[r]-() WHERE r.expires_at IS NOT NULL AND datetime(r.expires_at) < datetime() DELETE r',
          3600
        )
        """,
    }
