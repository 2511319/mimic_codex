"""Доменные сервисы поверх слоя данных."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Iterable, List, Optional

from rpg_gateway_api.data import (
    AdventureSummaryRecord,
    CampaignRunRecord,
    CharacterEventRecord,
    CharacterRecord,
    DataStoreProtocol,
    NotFoundError,
    PartyMemberRecord,
    PartyRecord,
    PlayerRecord,
    SceneStateRecord,
)


class PlayerService:
    def __init__(self, store: DataStoreProtocol) -> None:
        self._store = store

    def resolve_player(self, *, telegram_id: int, display_name: str) -> PlayerRecord:
        return self._store.get_or_create_player(telegram_id=telegram_id, display_name=display_name)


class CharacterService:
    def __init__(self, store: DataStoreProtocol) -> None:
        self._store = store

    def list_for_player(self, player_id: int) -> List[CharacterRecord]:
        return self._store.list_characters(player_id=player_id)

    def get(self, character_id: int) -> CharacterRecord:
        return self._store.get_character(character_id)

    def create(
        self,
        *,
        player_id: int,
        name: str,
        archetype: str,
        race: Optional[str] = None,
        core_stats: Optional[dict] = None,
        skills: Optional[dict] = None,
    ) -> CharacterRecord:
        return self._store.create_character(
            player_id=player_id,
            name=name,
            archetype=archetype,
            race=race,
            core_stats=core_stats,
            skills=skills,
        )

    def update(self, character_id: int, *, name: Optional[str], archetype: Optional[str], race: Optional[str]) -> CharacterRecord:
        return self._store.update_character(
            character_id,
            name=name,
            archetype=archetype,
            race=race,
        )

    def retire(self, character_id: int) -> CharacterRecord:
        return self._store.retire_character(character_id)

    def ensure_owner(self, *, character_id: int, player_id: int) -> CharacterRecord:
        record = self.get(character_id)
        if record.player_id != player_id:
            raise PermissionError("Character does not belong to player")
        return record


class PartyService:
    def __init__(self, store: DataStoreProtocol, character_service: CharacterService) -> None:
        self._store = store
        self._characters = character_service

    def list_for_player(self, player_id: int) -> List[PartyRecord]:
        return self._store.list_parties_for_player(player_id=player_id)

    def create_party(self, *, name: Optional[str], leader_character_id: int, player_id: int) -> PartyRecord:
        self._characters.ensure_owner(character_id=leader_character_id, player_id=player_id)
        return self._store.create_party(name=name, leader_character_id=leader_character_id)

    def join_party(self, *, party_id: int, character_id: int, player_id: int) -> PartyMemberRecord:
        self._characters.ensure_owner(character_id=character_id, player_id=player_id)
        return self._store.add_party_member(party_id=party_id, character_id=character_id)

    def leave_party(self, *, party_id: int, character_id: int, player_id: int) -> None:
        self._characters.ensure_owner(character_id=character_id, player_id=player_id)
        self._store.leave_party(party_id=party_id, character_id=character_id)

    def get_party(self, party_id: int) -> PartyRecord:
        return self._store.get_party(party_id)


class ChronicleService:
    def __init__(self, store: DataStoreProtocol) -> None:
        self._store = store

    def record_event(
        self,
        *,
        character_id: Optional[int],
        party_id: Optional[int],
        campaign_run_id: Optional[str],
        world_event_type: str,
        importance: str,
        payload: Optional[dict] = None,
    ) -> CharacterEventRecord:
        return self._store.record_event(
            character_id=character_id,
            party_id=party_id,
            campaign_run_id=campaign_run_id,
            world_event_type=world_event_type,
            importance=importance,
            payload=payload,
        )


def to_serializable(record) -> dict:
    """Утилита для выдачи наружу простых словарей."""

    return asdict(record)
