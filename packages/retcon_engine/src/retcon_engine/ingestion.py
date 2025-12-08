from __future__ import annotations

from datetime import datetime
from typing import Iterable
from uuid import uuid4

from .models import Importance, RetconPackage, WorldEvent, WorldEventType
from .repository import RetconRepository


class RetconIngestService:
    """Приём RetconPackage из gateway_api и конвертация в WorldEvent."""

    def __init__(self, repository: RetconRepository) -> None:
        self._repository = repository

    def ingest(self, package: RetconPackage) -> list[WorldEvent]:
        events = list(self._build_world_events(package))
        self._repository.store_package(package, events)
        return events

    def _build_world_events(self, package: RetconPackage) -> Iterable[WorldEvent]:
        for impact in package.player_impact:
            event_type = self._resolve_type(impact)
            importance = self._importance_from_scene(impact.get("sceneType"))
            yield WorldEvent(
                id=str(uuid4()),
                world_id=package.world_id,
                campaign_run_id=package.campaign_run_id,
                campaign_template_id=package.campaign_template_id,
                actors=self._actors_from_impact(impact),
                targets=self._targets_from_impact(impact),
                type=event_type,
                importance=importance,
                tags=self._tags_from_impact(impact),
                result=impact.get("outcome") or impact.get("result"),
                payload=impact,
                timestamp=self._timestamp_from_impact(impact),
            )

    def _resolve_type(self, impact: dict) -> WorldEventType:
        raw_type = (impact.get("type") or impact.get("sceneType") or "").upper()
        try:
            return WorldEventType(raw_type)
        except Exception:
            return WorldEventType.GENERIC

    def _importance_from_scene(self, scene_type: str | None) -> Importance:
        scene_type = (scene_type or "").lower()
        if scene_type in {"combat", "boss"}:
            return Importance.MESO
        if scene_type in {"epilogue", "finale"}:
            return Importance.MACRO
        return Importance.MICRO

    def _actors_from_impact(self, impact: dict) -> list[str]:
        actors: list[str] = []
        party_id = impact.get("partyId") or impact.get("party_id")
        if party_id:
            actors.append(f"party:{party_id}")
        for character_id in impact.get("characterIds") or []:
            actors.append(f"char:{character_id}")
        return actors

    def _targets_from_impact(self, impact: dict) -> list[str]:
        targets: list[str] = []
        for key in ("npcId", "factionId", "cityId", "locationId"):
            value = impact.get(key)
            if value:
                targets.append(f"{key.replace('Id', '').lower()}:{value}")
        return targets

    def _tags_from_impact(self, impact: dict) -> list[str]:
        tags: list[str] = []
        if arc := impact.get("storyArc"):
            tags.append(str(arc))
        if scene := impact.get("sceneType"):
            tags.append(f"scene:{scene}")
        return tags

    def _timestamp_from_impact(self, impact: dict) -> datetime:
        ts = impact.get("timestamp")
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts)
            except ValueError:
                pass
        if isinstance(ts, datetime):
            return ts
        return datetime.utcnow()


__all__ = ["RetconIngestService"]
