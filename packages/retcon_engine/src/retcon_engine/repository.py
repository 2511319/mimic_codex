from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Iterable

from .models import (
    CanonPatchCandidate,
    CanonPatchDecision,
    CanonPatchRecord,
    GlobalMetaSnapshot,
    RetconPackage,
    WorldEvent,
)


class RetconRepository:
    """Простейшее in-memory хранилище для Retcon Engine."""

    def __init__(self) -> None:
        self._packages: list[RetconPackage] = []
        self._world_events: list[WorldEvent] = []
        self._snapshots: list[GlobalMetaSnapshot] = []
        self._candidates: dict[str, CanonPatchCandidate] = {}
        self._patches: list[CanonPatchRecord] = []
        self._last_tick_at: datetime | None = None
        self._world_stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    @property
    def last_tick_at(self) -> datetime | None:
        return self._last_tick_at

    def store_package(self, package: RetconPackage, events: Iterable[WorldEvent]) -> None:
        self._packages.append(package)
        for event in events:
            self._world_events.append(event)
        stats = self._world_stats[package.world_id]
        stats["packages"] += 1
        stats["events"] += len(list(events))

    def list_packages_since(self, since: datetime) -> list[RetconPackage]:
        return [pkg for pkg in self._packages if pkg.received_at >= since]

    def add_snapshot(self, snapshot: GlobalMetaSnapshot) -> None:
        self._snapshots.append(snapshot)
        self._last_tick_at = snapshot.collected_to
        for candidate in snapshot.candidates:
            self._candidates[candidate.candidate_id] = candidate

    def list_candidates(self, world_id: str | None = None) -> list[CanonPatchCandidate]:
        if world_id:
            return [c for c in self._candidates.values() if c.world_id == world_id]
        return list(self._candidates.values())

    def apply_patch(
        self,
        candidate_id: str,
        decision: CanonPatchDecision,
        applied_by: str,
        *,
        world_version_prefix: str = "S1",
    ) -> CanonPatchRecord:
        candidate = self._candidates.get(candidate_id)
        if not candidate:
            raise KeyError(f"candidate {candidate_id} not found")
        version_suffix = len(self._patches) + 1
        record = CanonPatchRecord(
            candidate_id=candidate_id,
            decision=decision,
            applied_by=applied_by,
            applied_at=datetime.utcnow(),
            new_world_version=f"{world_version_prefix}-v{version_suffix}",
        )
        self._patches.append(record)
        return record

    def stats(self, world_id: str) -> dict[str, int]:
        return dict(self._world_stats.get(world_id, {}))


__all__ = ["RetconRepository"]
