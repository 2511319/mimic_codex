"""
Простая in-memory реализация реестра версий знаний и алиасов.

Это каркас для Wave B: поддерживает операции регистрации версий и
разрешение алиасов вида ``lore_latest`` → ``version_id``. В боевом
окружении хранение можно вынести в БД/Postgres, но для разработки
достаточно процесса и файлов.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict


@dataclass
class KnowledgeVersion:
    """Запись о версии знаний."""

    id: str
    semver: str
    kind: str  # lore | episode | srd | art | global
    status: str  # stage | latest | archived
    created_at: datetime = field(default_factory=datetime.utcnow)
    activated_at: datetime | None = None
    notes: str | None = None


@dataclass
class KnowledgeAlias:
    """Связка alias → version_id."""

    name: str
    version_id: str


class KnowledgeVersionRegistry:
    """Простейший реестр версий и алиасов."""

    def __init__(self) -> None:
        self._versions: Dict[str, KnowledgeVersion] = {}
        self._aliases: Dict[str, KnowledgeAlias] = {}

    def register(self, version: KnowledgeVersion) -> None:
        self._versions[version.id] = version
        # Автоматически выставляем alias kind_latest если его нет.
        latest_alias = f"{version.kind}_latest"
        self._aliases.setdefault(latest_alias, KnowledgeAlias(latest_alias, version.id))

    def set_alias(self, alias: str, version_id: str) -> None:
        if version_id not in self._versions:
            raise KeyError(f"Version '{version_id}' is not registered")
        self._aliases[alias] = KnowledgeAlias(alias, version_id)

    def get_version_id(self, *, alias: str | None = None, version_id: str | None = None) -> str:
        if version_id:
            if version_id not in self._versions:
                raise KeyError(f"Version '{version_id}' is not registered")
            return version_id
        if not alias:
            raise ValueError("Either alias or version_id must be provided")
        try:
            return self._aliases[alias].version_id
        except KeyError as exc:
            raise KeyError(f"Alias '{alias}' is not configured") from exc

    def snapshot(self) -> dict[str, str]:
        """Возвращает карту alias -> version_id (для отладки/метрик)."""

        return {name: alias.version_id for name, alias in self._aliases.items()}
