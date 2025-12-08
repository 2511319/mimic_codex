"""Простейшее хранилище данных OBT-1 (in-memory, без внешней БД)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Protocol
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


@dataclass
class PlayerRecord:
    id: int
    telegram_id: int
    display_name: str
    settings: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    last_login_at: datetime = field(default_factory=_utcnow)


@dataclass
class CharacterRecord:
    id: int
    player_id: int
    name: str
    archetype: str
    race: Optional[str] = None
    level: int = 1
    xp: int = 0
    core_stats: Dict[str, Any] = field(default_factory=dict)
    skills: Dict[str, Any] = field(default_factory=dict)
    inventory_ref: Optional[str] = None
    status: str = "ACTIVE"
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


@dataclass
class PartyRecord:
    id: int
    name: Optional[str]
    leader_character_id: int
    created_at: datetime = field(default_factory=_utcnow)
    active_campaign_run_id: Optional[str] = None


@dataclass
class PartyMemberRecord:
    party_id: int
    character_id: int
    role: str = "MEMBER"
    joined_at: datetime = field(default_factory=_utcnow)
    left_at: Optional[datetime] = None


@dataclass
class CharacterCampaignRunRecord:
    character_id: int
    campaign_run_id: str
    role: str = "MAIN"


@dataclass
class CharacterEventRecord:
    id: int
    character_id: Optional[int]
    party_id: Optional[int]
    campaign_run_id: Optional[str]
    world_event_type: str
    importance: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass
class CampaignTemplateRecord:
    id: str
    title: str
    description: str
    season_version: str = "S1-v0.1"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EpisodeRecord:
    id: str
    campaign_template_id: str
    order: int
    type: str = "main"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CampaignRunRecord:
    id: str
    campaign_template_id: str
    party_id: int
    status: str = "IN_PROGRESS"
    current_episode_id: Optional[str] = None
    current_scene_id: Optional[str] = None
    created_at: datetime = field(default_factory=_utcnow)
    finished_at: Optional[datetime] = None
    canon_version: Optional[str] = None


@dataclass
class SceneStateRecord:
    id: str
    campaign_run_id: str
    episode_id: str
    scene_order: int
    scene_type: str
    profile: Optional[str]
    input_context: Dict[str, Any] = field(default_factory=dict)
    generated_payload: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    result_flags: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    resolved_at: Optional[datetime] = None


@dataclass
class FlagStateRecord:
    id: int
    campaign_run_id: str
    key: str
    value: Any
    source_scene_id: Optional[str] = None


@dataclass
class AdventureSummaryRecord:
    campaign_run_id: str
    summary: Dict[str, Any]
    retcon_package: Dict[str, Any]
    created_at: datetime = field(default_factory=_utcnow)


class DataStoreProtocol(Protocol):
    """Протокол для хранилища (in-memory или Postgres)."""

    def get_or_create_player(self, *, telegram_id: int, display_name: str) -> PlayerRecord: ...
    def get_player(self, player_id: int) -> PlayerRecord: ...

    def list_characters(self, *, player_id: int) -> List[CharacterRecord]: ...
    def get_character(self, character_id: int) -> CharacterRecord: ...
    def create_character(
        self,
        *,
        player_id: int,
        name: str,
        archetype: str,
        race: Optional[str] = None,
        core_stats: Optional[Dict[str, Any]] = None,
        skills: Optional[Dict[str, Any]] = None,
    ) -> CharacterRecord: ...
    def update_character(self, character_id: int, **updates: Any) -> CharacterRecord: ...
    def retire_character(self, character_id: int) -> CharacterRecord: ...

    def list_parties_for_player(self, player_id: int) -> List[PartyRecord]: ...
    def get_party(self, party_id: int) -> PartyRecord: ...
    def create_party(self, *, name: Optional[str], leader_character_id: int) -> PartyRecord: ...
    def add_party_member(self, *, party_id: int, character_id: int, role: str = "MEMBER") -> PartyMemberRecord: ...
    def leave_party(self, *, party_id: int, character_id: int) -> None: ...
    def list_active_party_members(self, party_id: int) -> List[PartyMemberRecord]: ...

    def upsert_campaign_template(self, template: CampaignTemplateRecord) -> None: ...
    def upsert_episode(self, episode: EpisodeRecord) -> None: ...
    def list_campaign_templates(self) -> List[CampaignTemplateRecord]: ...

    def start_campaign_run(
        self,
        *,
        campaign_template_id: str,
        party_id: int,
        current_episode_id: Optional[str],
        status: str | None = None,
    ) -> CampaignRunRecord: ...
    def get_campaign_run(self, run_id: str) -> CampaignRunRecord: ...
    def update_campaign_run(self, run_id: str, **updates: Any) -> CampaignRunRecord: ...
    def add_character_to_run(self, *, character_id: int, run_id: str, role: str = "MAIN") -> CharacterCampaignRunRecord: ...
    def list_characters_in_run(self, run_id: str) -> List[CharacterCampaignRunRecord]: ...
    def record_scene_state(
        self,
        *,
        campaign_run_id: str,
        episode_id: str,
        scene_order: int,
        scene_type: str,
        profile: Optional[str],
        input_context: Dict[str, Any],
        generated_payload: Dict[str, Any],
        resolved: bool,
        result_flags: Dict[str, Any],
    ) -> SceneStateRecord: ...
    def get_scene_state(self, scene_id: str) -> SceneStateRecord: ...
    def resolve_scene(self, scene_id: str, result_flags: Dict[str, Any]) -> SceneStateRecord: ...
    def list_scenes_for_run(self, run_id: str) -> List[SceneStateRecord]: ...
    def add_flag(self, *, campaign_run_id: str, key: str, value: Any, source_scene_id: Optional[str]) -> FlagStateRecord: ...

    def record_event(
        self,
        *,
        character_id: Optional[int],
        party_id: Optional[int],
        campaign_run_id: Optional[str],
        world_event_type: str,
        importance: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> CharacterEventRecord: ...
    def store_adventure_summary(
        self,
        *,
        campaign_run_id: str,
        summary: Dict[str, Any],
        retcon_package: Dict[str, Any],
    ) -> AdventureSummaryRecord: ...
    def get_adventure_summary(self, run_id: str) -> AdventureSummaryRecord: ...


class DataStoreError(RuntimeError):
    """Общее исключение слоя данных."""


class NotFoundError(DataStoreError):
    """Запрашиваемая сущность не найдена."""


class InMemoryDataStore:
    """Минимальная in-memory реализация, пригодная для тестов и dev."""

    def __init__(self) -> None:
        self._player_seq = 1
        self._character_seq = 1
        self._party_seq = 1
        self._event_seq = 1
        self._flag_seq = 1
        self.players: Dict[int, PlayerRecord] = {}
        self.characters: Dict[int, CharacterRecord] = {}
        self.parties: Dict[int, PartyRecord] = {}
        self.party_members: List[PartyMemberRecord] = []
        self.character_campaign_runs: List[CharacterCampaignRunRecord] = []
        self.character_events: List[CharacterEventRecord] = []
        self.campaign_runs: Dict[str, CampaignRunRecord] = {}
        self.scene_states: Dict[str, SceneStateRecord] = {}
        self.flag_states: List[FlagStateRecord] = []
        self.adventure_summaries: Dict[str, AdventureSummaryRecord] = {}
        self.campaign_templates: Dict[str, CampaignTemplateRecord] = {}
        self.episodes: Dict[str, EpisodeRecord] = {}
        self._campaign_templates_order: List[str] = []

    # Players
    def get_or_create_player(self, *, telegram_id: int, display_name: str) -> PlayerRecord:
        for player in self.players.values():
            if player.telegram_id == telegram_id:
                player.last_login_at = _utcnow()
                player.display_name = display_name or player.display_name
                return player
        player = PlayerRecord(
            id=self._player_seq,
            telegram_id=telegram_id,
            display_name=display_name or f"Player-{telegram_id}",
        )
        self.players[player.id] = player
        self._player_seq += 1
        return player

    def get_player(self, player_id: int) -> PlayerRecord:
        try:
            return self.players[player_id]
        except KeyError as exc:
            raise NotFoundError(f"Player {player_id} not found") from exc

    # Characters
    def list_characters(self, *, player_id: int) -> List[CharacterRecord]:
        return [c for c in self.characters.values() if c.player_id == player_id]

    def get_character(self, character_id: int) -> CharacterRecord:
        try:
            return self.characters[character_id]
        except KeyError as exc:
            raise NotFoundError(f"Character {character_id} not found") from exc

    def create_character(
        self,
        *,
        player_id: int,
        name: str,
        archetype: str,
        race: Optional[str] = None,
        core_stats: Optional[Dict[str, Any]] = None,
        skills: Optional[Dict[str, Any]] = None,
    ) -> CharacterRecord:
        record = CharacterRecord(
            id=self._character_seq,
            player_id=player_id,
            name=name,
            archetype=archetype,
            race=race,
            core_stats=core_stats or {},
            skills=skills or {},
        )
        self.characters[record.id] = record
        self._character_seq += 1
        return record

    def update_character(self, character_id: int, **updates: Any) -> CharacterRecord:
        record = self.get_character(character_id)
        for key, value in updates.items():
            if hasattr(record, key) and value is not None:
                setattr(record, key, value)
        record.updated_at = _utcnow()
        return record

    def retire_character(self, character_id: int) -> CharacterRecord:
        record = self.get_character(character_id)
        record.status = "RETIRED"
        record.updated_at = _utcnow()
        return record

    # Parties
    def list_parties_for_player(self, player_id: int) -> List[PartyRecord]:
        character_ids = {c.id for c in self.list_characters(player_id=player_id)}
        party_ids = {
            m.party_id
            for m in self.party_members
            if m.character_id in character_ids and m.left_at is None
        }
        return [p for p in self.parties.values() if p.id in party_ids]

    def get_party(self, party_id: int) -> PartyRecord:
        try:
            return self.parties[party_id]
        except KeyError as exc:
            raise NotFoundError(f"Party {party_id} not found") from exc

    def create_party(self, *, name: Optional[str], leader_character_id: int) -> PartyRecord:
        record = PartyRecord(
            id=self._party_seq,
            name=name,
            leader_character_id=leader_character_id,
        )
        self.parties[record.id] = record
        self._party_seq += 1
        self.party_members.append(
            PartyMemberRecord(party_id=record.id, character_id=leader_character_id, role="LEADER")
        )
        return record

    def add_party_member(self, *, party_id: int, character_id: int, role: str = "MEMBER") -> PartyMemberRecord:
        self.get_party(party_id)  # ensure exists
        existing = [
            m for m in self.party_members if m.party_id == party_id and m.character_id == character_id and m.left_at is None
        ]
        if existing:
            return existing[0]
        member = PartyMemberRecord(party_id=party_id, character_id=character_id, role=role)
        self.party_members.append(member)
        return member

    def list_active_party_members(self, party_id: int) -> List[PartyMemberRecord]:
        return [m for m in self.party_members if m.party_id == party_id and m.left_at is None]

    def leave_party(self, *, party_id: int, character_id: int) -> None:
        changed = False
        for member in self.party_members:
            if member.party_id == party_id and member.character_id == character_id and member.left_at is None:
                member.left_at = _utcnow()
                changed = True
        if not changed:
            raise NotFoundError(f"Character {character_id} is not in party {party_id}")

    # Campaigns
    def upsert_campaign_template(self, template: CampaignTemplateRecord) -> None:
        self.campaign_templates[template.id] = template
        if template.id not in self._campaign_templates_order:
            self._campaign_templates_order.append(template.id)

    def upsert_episode(self, episode: EpisodeRecord) -> None:
        self.episodes[episode.id] = episode

    def list_campaign_templates(self) -> List[CampaignTemplateRecord]:
        ordered = [self.campaign_templates[tid] for tid in self._campaign_templates_order if tid in self.campaign_templates]
        remaining = [t for tid, t in self.campaign_templates.items() if tid not in self._campaign_templates_order]
        return ordered + remaining

    def start_campaign_run(
        self,
        *,
        campaign_template_id: str,
        party_id: int,
        current_episode_id: Optional[str],
        status: str | None = None,
    ) -> CampaignRunRecord:
        run_id = uuid4().hex
        record = CampaignRunRecord(
            id=run_id,
            campaign_template_id=campaign_template_id,
            party_id=party_id,
            status=status or "IN_PROGRESS",
            current_episode_id=current_episode_id,
            current_scene_id=None,
        )
        self.campaign_runs[run_id] = record
        return record

    def get_campaign_run(self, run_id: str) -> CampaignRunRecord:
        try:
            return self.campaign_runs[run_id]
        except KeyError as exc:
            raise NotFoundError(f"CampaignRun {run_id} not found") from exc

    def update_campaign_run(self, run_id: str, **updates: Any) -> CampaignRunRecord:
        run = self.get_campaign_run(run_id)
        for key, value in updates.items():
            if hasattr(run, key):
                setattr(run, key, value)
        return run

    def add_character_to_run(self, *, character_id: int, run_id: str, role: str = "MAIN") -> CharacterCampaignRunRecord:
        link = CharacterCampaignRunRecord(character_id=character_id, campaign_run_id=run_id, role=role)
        self.character_campaign_runs.append(link)
        return link

    def list_characters_in_run(self, run_id: str) -> List[CharacterCampaignRunRecord]:
        return [c for c in self.character_campaign_runs if c.campaign_run_id == run_id]

    def record_scene_state(
        self,
        *,
        campaign_run_id: str,
        episode_id: str,
        scene_order: int,
        scene_type: str,
        profile: Optional[str],
        input_context: Dict[str, Any],
        generated_payload: Dict[str, Any],
        resolved: bool,
        result_flags: Dict[str, Any],
    ) -> SceneStateRecord:
        scene_id = uuid4().hex
        record = SceneStateRecord(
            id=scene_id,
            campaign_run_id=campaign_run_id,
            episode_id=episode_id,
            scene_order=scene_order,
            scene_type=scene_type,
            profile=profile,
            input_context=input_context,
            generated_payload=generated_payload,
            resolved=resolved,
            result_flags=result_flags,
            resolved_at=_utcnow() if resolved else None,
        )
        self.scene_states[scene_id] = record
        return record

    def get_scene_state(self, scene_id: str) -> SceneStateRecord:
        try:
            return self.scene_states[scene_id]
        except KeyError as exc:
            raise NotFoundError(f"SceneState {scene_id} not found") from exc

    def resolve_scene(self, scene_id: str, result_flags: Dict[str, Any]) -> SceneStateRecord:
        scene = self.scene_states.get(scene_id)
        if not scene:
            raise NotFoundError(f"SceneState {scene_id} not found")
        scene.resolved = True
        scene.result_flags = result_flags
        scene.resolved_at = _utcnow()
        return scene

    def list_scenes_for_run(self, run_id: str) -> List[SceneStateRecord]:
        return [s for s in self.scene_states.values() if s.campaign_run_id == run_id]

    def add_flag(self, *, campaign_run_id: str, key: str, value: Any, source_scene_id: Optional[str]) -> FlagStateRecord:
        record = FlagStateRecord(
            id=self._flag_seq,
            campaign_run_id=campaign_run_id,
            key=key,
            value=value,
            source_scene_id=source_scene_id,
        )
        self._flag_seq += 1
        self.flag_states.append(record)
        return record

    def record_event(
        self,
        *,
        character_id: Optional[int],
        party_id: Optional[int],
        campaign_run_id: Optional[str],
        world_event_type: str,
        importance: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> CharacterEventRecord:
        record = CharacterEventRecord(
            id=self._event_seq,
            character_id=character_id,
            party_id=party_id,
            campaign_run_id=campaign_run_id,
            world_event_type=world_event_type,
            importance=importance,
            payload=payload or {},
        )
        self._event_seq += 1
        self.character_events.append(record)
        return record

    def store_adventure_summary(
        self,
        *,
        campaign_run_id: str,
        summary: Dict[str, Any],
        retcon_package: Dict[str, Any],
    ) -> AdventureSummaryRecord:
        record = AdventureSummaryRecord(
            campaign_run_id=campaign_run_id,
            summary=summary,
            retcon_package=retcon_package,
        )
        self.adventure_summaries[campaign_run_id] = record
        return record

    def get_adventure_summary(self, run_id: str) -> AdventureSummaryRecord:
        try:
            return self.adventure_summaries[run_id]
        except KeyError as exc:
            raise NotFoundError(f"AdventureSummary for run {run_id} not found") from exc


class PostgresDataStore:
    """Хранилище на Postgres для боевого режима OBT-1."""

    def __init__(self, dsn: str) -> None:
        import psycopg
        from psycopg.types.json import Json

        self._psycopg = psycopg
        self._dsn = dsn
        self._json = Json
        self._ensure_schema()

    def _connect(self):
        return self._psycopg.connect(self._dsn, autocommit=True)

    def _ensure_schema(self) -> None:
        ddl = """
        create table if not exists players (
            id bigserial primary key,
            telegram_id bigint unique not null,
            display_name text not null,
            settings jsonb not null default '{}'::jsonb,
            created_at timestamptz not null default now(),
            last_login_at timestamptz not null default now()
        );
        create table if not exists characters (
            id bigserial primary key,
            player_id bigint not null references players(id) on delete cascade,
            name text not null,
            archetype text not null,
            race text,
            level int not null default 1,
            xp int not null default 0,
            core_stats jsonb not null default '{}'::jsonb,
            skills jsonb not null default '{}'::jsonb,
            inventory_ref text,
            status text not null default 'ACTIVE',
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now()
        );
        create table if not exists parties (
            id bigserial primary key,
            name text,
            leader_character_id bigint not null references characters(id),
            active_campaign_run_id text,
            created_at timestamptz not null default now()
        );
        create table if not exists party_members (
            party_id bigint not null references parties(id) on delete cascade,
            character_id bigint not null references characters(id) on delete cascade,
            role text not null default 'MEMBER',
            joined_at timestamptz not null default now(),
            left_at timestamptz,
            primary key (party_id, character_id)
        );
        create table if not exists campaign_templates (
            id text primary key,
            title text not null,
            description text not null,
            season_version text not null,
            metadata jsonb not null default '{}'::jsonb
        );
        create table if not exists episodes (
            id text primary key,
            campaign_template_id text not null references campaign_templates(id) on delete cascade,
            ord int not null,
            type text not null,
            metadata jsonb not null default '{}'::jsonb
        );
        create table if not exists campaign_runs (
            id text primary key,
            campaign_template_id text not null references campaign_templates(id),
            party_id bigint not null references parties(id),
            status text not null,
            current_episode_id text,
            current_scene_id text,
            created_at timestamptz not null default now(),
            finished_at timestamptz,
            canon_version text
        );
        create table if not exists scene_states (
            id text primary key,
            campaign_run_id text not null references campaign_runs(id) on delete cascade,
            episode_id text not null,
            scene_order int not null,
            scene_type text not null,
            profile text,
            input_context jsonb not null default '{}'::jsonb,
            generated_payload jsonb not null default '{}'::jsonb,
            resolved boolean not null default false,
            result_flags jsonb not null default '{}'::jsonb,
            created_at timestamptz not null default now(),
            resolved_at timestamptz
        );
        create table if not exists flag_states (
            id bigserial primary key,
            campaign_run_id text not null references campaign_runs(id) on delete cascade,
            key text not null,
            value jsonb,
            source_scene_id text
        );
        create table if not exists character_campaign_runs (
            character_id bigint not null references characters(id) on delete cascade,
            campaign_run_id text not null references campaign_runs(id) on delete cascade,
            role text not null default 'MAIN',
            primary key (character_id, campaign_run_id)
        );
        create table if not exists character_events (
            id bigserial primary key,
            character_id bigint references characters(id) on delete set null,
            party_id bigint references parties(id) on delete set null,
            campaign_run_id text references campaign_runs(id) on delete set null,
            world_event_type text not null,
            importance text not null,
            payload jsonb not null default '{}'::jsonb,
            timestamp timestamptz not null default now()
        );
        create table if not exists adventure_summaries (
            campaign_run_id text primary key references campaign_runs(id) on delete cascade,
            summary jsonb not null,
            retcon_package jsonb not null,
            created_at timestamptz not null default now()
        );
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)

    # Players
    def get_or_create_player(self, *, telegram_id: int, display_name: str) -> PlayerRecord:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into players (telegram_id, display_name)
                values (%s, %s)
                on conflict (telegram_id) do update
                set display_name = excluded.display_name,
                    last_login_at = now()
                returning id, telegram_id, display_name, settings, created_at, last_login_at
                """,
                (telegram_id, display_name),
            )
            row = cur.fetchone()
        return PlayerRecord(
            id=row[0],
            telegram_id=row[1],
            display_name=row[2],
            settings=row[3],
            created_at=row[4],
            last_login_at=row[5],
        )

    def get_player(self, player_id: int) -> PlayerRecord:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "select id, telegram_id, display_name, settings, created_at, last_login_at from players where id=%s",
                (player_id,),
            )
            row = cur.fetchone()
        if not row:
            raise NotFoundError(f"Player {player_id} not found")
        return PlayerRecord(
            id=row[0],
            telegram_id=row[1],
            display_name=row[2],
            settings=row[3],
            created_at=row[4],
            last_login_at=row[5],
        )

    # Characters
    def list_characters(self, *, player_id: int) -> List[CharacterRecord]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                select id, player_id, name, archetype, race, level, xp, core_stats, skills, inventory_ref,
                       status, created_at, updated_at
                from characters where player_id=%s
                order by id asc
                """,
                (player_id,),
            )
            rows = cur.fetchall()
        return [
            CharacterRecord(
                id=r[0],
                player_id=r[1],
                name=r[2],
                archetype=r[3],
                race=r[4],
                level=r[5],
                xp=r[6],
                core_stats=r[7],
                skills=r[8],
                inventory_ref=r[9],
                status=r[10],
                created_at=r[11],
                updated_at=r[12],
            )
            for r in rows
        ]

    def get_character(self, character_id: int) -> CharacterRecord:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                select id, player_id, name, archetype, race, level, xp, core_stats, skills, inventory_ref,
                       status, created_at, updated_at
                from characters where id=%s
                """,
                (character_id,),
            )
            row = cur.fetchone()
        if not row:
            raise NotFoundError(f"Character {character_id} not found")
        return CharacterRecord(
            id=row[0],
            player_id=row[1],
            name=row[2],
            archetype=row[3],
            race=row[4],
            level=row[5],
            xp=row[6],
            core_stats=row[7],
            skills=row[8],
            inventory_ref=row[9],
            status=row[10],
            created_at=row[11],
            updated_at=row[12],
        )

    def create_character(
        self,
        *,
        player_id: int,
        name: str,
        archetype: str,
        race: Optional[str] = None,
        core_stats: Optional[Dict[str, Any]] = None,
        skills: Optional[Dict[str, Any]] = None,
    ) -> CharacterRecord:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into characters (player_id, name, archetype, race, core_stats, skills)
                values (%s, %s, %s, %s, %s, %s)
                returning id, player_id, name, archetype, race, level, xp, core_stats, skills, inventory_ref,
                          status, created_at, updated_at
                """,
                (player_id, name, archetype, race, self._json(core_stats or {}), self._json(skills or {})),
            )
            row = cur.fetchone()
        return CharacterRecord(
            id=row[0],
            player_id=row[1],
            name=row[2],
            archetype=row[3],
            race=row[4],
            level=row[5],
            xp=row[6],
            core_stats=row[7],
            skills=row[8],
            inventory_ref=row[9],
            status=row[10],
            created_at=row[11],
            updated_at=row[12],
        )

    def update_character(self, character_id: int, **updates: Any) -> CharacterRecord:
        allowed = {k: v for k, v in updates.items() if v is not None}
        if not allowed:
            return self.get_character(character_id)
        for key, value in list(allowed.items()):
            if isinstance(value, dict):
                allowed[key] = self._json(value)
        sets = ", ".join(f"{k}=%s" for k in allowed.keys())
        values = list(allowed.values())
        values.append(character_id)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"update characters set {sets}, updated_at=now() where id=%s returning id, player_id, name, archetype, race, level, xp, core_stats, skills, inventory_ref, status, created_at, updated_at", values)
            row = cur.fetchone()
        if not row:
            raise NotFoundError(f"Character {character_id} not found")
        return CharacterRecord(
            id=row[0],
            player_id=row[1],
            name=row[2],
            archetype=row[3],
            race=row[4],
            level=row[5],
            xp=row[6],
            core_stats=row[7],
            skills=row[8],
            inventory_ref=row[9],
            status=row[10],
            created_at=row[11],
            updated_at=row[12],
        )

    def retire_character(self, character_id: int) -> CharacterRecord:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                update characters set status='RETIRED', updated_at=now() where id=%s
                returning id, player_id, name, archetype, race, level, xp, core_stats, skills, inventory_ref,
                          status, created_at, updated_at
                """,
                (character_id,),
            )
            row = cur.fetchone()
        if not row:
            raise NotFoundError(f"Character {character_id} not found")
        return CharacterRecord(
            id=row[0],
            player_id=row[1],
            name=row[2],
            archetype=row[3],
            race=row[4],
            level=row[5],
            xp=row[6],
            core_stats=row[7],
            skills=row[8],
            inventory_ref=row[9],
            status=row[10],
            created_at=row[11],
            updated_at=row[12],
        )

    # Parties
    def list_parties_for_player(self, player_id: int) -> List[PartyRecord]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                select distinct p.id, p.name, p.leader_character_id, p.active_campaign_run_id, p.created_at
                from parties p
                join party_members pm on pm.party_id = p.id and pm.left_at is null
                join characters c on c.id = pm.character_id
                where c.player_id = %s
                order by p.id asc
                """,
                (player_id,),
            )
            rows = cur.fetchall()
        return [
            PartyRecord(
                id=r[0],
                name=r[1],
                leader_character_id=r[2],
                active_campaign_run_id=r[3],
                created_at=r[4],
            )
            for r in rows
        ]

    def get_party(self, party_id: int) -> PartyRecord:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "select id, name, leader_character_id, active_campaign_run_id, created_at from parties where id=%s",
                (party_id,),
            )
            row = cur.fetchone()
        if not row:
            raise NotFoundError(f"Party {party_id} not found")
        return PartyRecord(
            id=row[0],
            name=row[1],
            leader_character_id=row[2],
            active_campaign_run_id=row[3],
            created_at=row[4],
        )

    def create_party(self, *, name: Optional[str], leader_character_id: int) -> PartyRecord:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into parties (name, leader_character_id)
                values (%s, %s)
                returning id, name, leader_character_id, active_campaign_run_id, created_at
                """,
                (name, leader_character_id),
            )
            row = cur.fetchone()
            cur.execute(
                """
                insert into party_members (party_id, character_id, role)
                values (%s, %s, %s)
                on conflict (party_id, character_id) do update set left_at=null, role=excluded.role
                """,
                (row[0], leader_character_id, "LEADER"),
            )
        return PartyRecord(
            id=row[0],
            name=row[1],
            leader_character_id=row[2],
            active_campaign_run_id=row[3],
            created_at=row[4],
        )

    def add_party_member(self, *, party_id: int, character_id: int, role: str = "MEMBER") -> PartyMemberRecord:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into party_members (party_id, character_id, role, left_at)
                values (%s, %s, %s, null)
                on conflict (party_id, character_id) do update set role=excluded.role, left_at=null
                returning party_id, character_id, role, joined_at, left_at
                """,
                (party_id, character_id, role),
            )
            row = cur.fetchone()
        return PartyMemberRecord(
            party_id=row[0],
            character_id=row[1],
            role=row[2],
            joined_at=row[3],
            left_at=row[4],
        )

    def leave_party(self, *, party_id: int, character_id: int) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "update party_members set left_at=now() where party_id=%s and character_id=%s and left_at is null",
                (party_id, character_id),
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"Character {character_id} is not in party {party_id}")

    def list_active_party_members(self, party_id: int) -> List[PartyMemberRecord]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                select party_id, character_id, role, joined_at, left_at
                from party_members
                where party_id=%s and left_at is null
                """,
                (party_id,),
            )
            rows = cur.fetchall()
        return [
            PartyMemberRecord(
                party_id=r[0],
                character_id=r[1],
                role=r[2],
                joined_at=r[3],
                left_at=r[4],
            )
            for r in rows
        ]

    # Campaigns
    def upsert_campaign_template(self, template: CampaignTemplateRecord) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into campaign_templates (id, title, description, season_version, metadata)
                values (%s, %s, %s, %s, %s)
                on conflict (id) do update set
                    title=excluded.title,
                    description=excluded.description,
                    season_version=excluded.season_version,
                    metadata=excluded.metadata
                """,
                (template.id, template.title, template.description, template.season_version, self._json(template.metadata)),
            )

    def upsert_episode(self, episode: EpisodeRecord) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into episodes (id, campaign_template_id, ord, type, metadata)
                values (%s, %s, %s, %s, %s)
                on conflict (id) do update set ord=excluded.ord, type=excluded.type, metadata=excluded.metadata
                """,
                (episode.id, episode.campaign_template_id, episode.order, episode.type, self._json(episode.metadata)),
            )

    def list_campaign_templates(self) -> List[CampaignTemplateRecord]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "select id, title, description, season_version, metadata from campaign_templates order by id asc"
            )
            rows = cur.fetchall()
        return [
            CampaignTemplateRecord(
                id=r[0],
                title=r[1],
                description=r[2],
                season_version=r[3],
                metadata=r[4],
            )
            for r in rows
        ]

    def start_campaign_run(
        self,
        *,
        campaign_template_id: str,
        party_id: int,
        current_episode_id: Optional[str],
        status: str | None = None,
    ) -> CampaignRunRecord:
        run_id = uuid4().hex
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into campaign_runs (id, campaign_template_id, party_id, status, current_episode_id, current_scene_id)
                values (%s, %s, %s, %s, %s, %s)
                returning id, campaign_template_id, party_id, status, current_episode_id, current_scene_id, created_at, finished_at, canon_version
                """,
                (run_id, campaign_template_id, party_id, status or "IN_PROGRESS", current_episode_id, None),
            )
            row = cur.fetchone()
        return CampaignRunRecord(
            id=row[0],
            campaign_template_id=row[1],
            party_id=row[2],
            status=row[3],
            current_episode_id=row[4],
            current_scene_id=row[5],
            created_at=row[6],
            finished_at=row[7],
            canon_version=row[8],
        )

    def get_campaign_run(self, run_id: str) -> CampaignRunRecord:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                select id, campaign_template_id, party_id, status, current_episode_id, current_scene_id, created_at, finished_at, canon_version
                from campaign_runs where id=%s
                """,
                (run_id,),
            )
            row = cur.fetchone()
        if not row:
            raise NotFoundError(f"CampaignRun {run_id} not found")
        return CampaignRunRecord(
            id=row[0],
            campaign_template_id=row[1],
            party_id=row[2],
            status=row[3],
            current_episode_id=row[4],
            current_scene_id=row[5],
            created_at=row[6],
            finished_at=row[7],
            canon_version=row[8],
        )

    def update_campaign_run(self, run_id: str, **updates: Any) -> CampaignRunRecord:
        allowed = {k: v for k, v in updates.items() if hasattr(CampaignRunRecord, k)}
        if not allowed:
            return self.get_campaign_run(run_id)
        sets = ", ".join(f"{k}=%s" for k in allowed.keys())
        values = list(allowed.values())
        values.append(run_id)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"update campaign_runs set {sets} where id=%s returning id, campaign_template_id, party_id, status, current_episode_id, current_scene_id, created_at, finished_at, canon_version",
                values,
            )
            row = cur.fetchone()
        if not row:
            raise NotFoundError(f"CampaignRun {run_id} not found")
        return CampaignRunRecord(
            id=row[0],
            campaign_template_id=row[1],
            party_id=row[2],
            status=row[3],
            current_episode_id=row[4],
            current_scene_id=row[5],
            created_at=row[6],
            finished_at=row[7],
            canon_version=row[8],
        )

    def add_character_to_run(self, *, character_id: int, run_id: str, role: str = "MAIN") -> CharacterCampaignRunRecord:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into character_campaign_runs (character_id, campaign_run_id, role)
                values (%s, %s, %s)
                on conflict (character_id, campaign_run_id) do update set role=excluded.role
                returning character_id, campaign_run_id, role
                """,
                (character_id, run_id, role),
            )
            row = cur.fetchone()
        return CharacterCampaignRunRecord(character_id=row[0], campaign_run_id=row[1], role=row[2])

    def list_characters_in_run(self, run_id: str) -> List[CharacterCampaignRunRecord]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "select character_id, campaign_run_id, role from character_campaign_runs where campaign_run_id=%s",
                (run_id,),
            )
            rows = cur.fetchall()
        return [CharacterCampaignRunRecord(character_id=r[0], campaign_run_id=r[1], role=r[2]) for r in rows]

    def record_scene_state(
        self,
        *,
        campaign_run_id: str,
        episode_id: str,
        scene_order: int,
        scene_type: str,
        profile: Optional[str],
        input_context: Dict[str, Any],
        generated_payload: Dict[str, Any],
        resolved: bool,
        result_flags: Dict[str, Any],
    ) -> SceneStateRecord:
        scene_id = uuid4().hex
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into scene_states (id, campaign_run_id, episode_id, scene_order, scene_type, profile, input_context,
                                          generated_payload, resolved, result_flags, resolved_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning id, campaign_run_id, episode_id, scene_order, scene_type, profile, input_context, generated_payload,
                          resolved, result_flags, created_at, resolved_at
                """,
                (
                    scene_id,
                    campaign_run_id,
                    episode_id,
                    scene_order,
                    scene_type,
                    profile,
                    self._json(input_context),
                    self._json(generated_payload),
                    resolved,
                    self._json(result_flags),
                    _utcnow() if resolved else None,
                ),
            )
            row = cur.fetchone()
        return SceneStateRecord(
            id=row[0],
            campaign_run_id=row[1],
            episode_id=row[2],
            scene_order=row[3],
            scene_type=row[4],
            profile=row[5],
            input_context=row[6],
            generated_payload=row[7],
            resolved=row[8],
            result_flags=row[9],
            created_at=row[10],
            resolved_at=row[11],
        )

    def get_scene_state(self, scene_id: str) -> SceneStateRecord:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                select id, campaign_run_id, episode_id, scene_order, scene_type, profile, input_context, generated_payload,
                       resolved, result_flags, created_at, resolved_at
                from scene_states where id=%s
                """,
                (scene_id,),
            )
            row = cur.fetchone()
        if not row:
            raise NotFoundError(f"SceneState {scene_id} not found")
        return SceneStateRecord(
            id=row[0],
            campaign_run_id=row[1],
            episode_id=row[2],
            scene_order=row[3],
            scene_type=row[4],
            profile=row[5],
            input_context=row[6],
            generated_payload=row[7],
            resolved=row[8],
            result_flags=row[9],
            created_at=row[10],
            resolved_at=row[11],
        )

    def resolve_scene(self, scene_id: str, result_flags: Dict[str, Any]) -> SceneStateRecord:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                update scene_states set resolved=true, result_flags=%s, resolved_at=now()
                where id=%s
                returning id, campaign_run_id, episode_id, scene_order, scene_type, profile, input_context, generated_payload,
                          resolved, result_flags, created_at, resolved_at
                """,
                (self._json(result_flags), scene_id),
            )
            row = cur.fetchone()
        if not row:
            raise NotFoundError(f"SceneState {scene_id} not found")
        return SceneStateRecord(
            id=row[0],
            campaign_run_id=row[1],
            episode_id=row[2],
            scene_order=row[3],
            scene_type=row[4],
            profile=row[5],
            input_context=row[6],
            generated_payload=row[7],
            resolved=row[8],
            result_flags=row[9],
            created_at=row[10],
            resolved_at=row[11],
        )

    def list_scenes_for_run(self, run_id: str) -> List[SceneStateRecord]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                select id, campaign_run_id, episode_id, scene_order, scene_type, profile, input_context, generated_payload,
                       resolved, result_flags, created_at, resolved_at
                from scene_states where campaign_run_id=%s
                order by scene_order asc
                """,
                (run_id,),
            )
            rows = cur.fetchall()
        return [
            SceneStateRecord(
                id=r[0],
                campaign_run_id=r[1],
                episode_id=r[2],
                scene_order=r[3],
                scene_type=r[4],
                profile=r[5],
                input_context=r[6],
                generated_payload=r[7],
                resolved=r[8],
                result_flags=r[9],
                created_at=r[10],
                resolved_at=r[11],
            )
            for r in rows
        ]

    def add_flag(self, *, campaign_run_id: str, key: str, value: Any, source_scene_id: Optional[str]) -> FlagStateRecord:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into flag_states (campaign_run_id, key, value, source_scene_id)
                values (%s, %s, %s, %s)
                returning id, campaign_run_id, key, value, source_scene_id
                """,
                (campaign_run_id, key, self._json(value), source_scene_id),
            )
            row = cur.fetchone()
        return FlagStateRecord(
            id=row[0],
            campaign_run_id=row[1],
            key=row[2],
            value=row[3],
            source_scene_id=row[4],
        )

    def record_event(
        self,
        *,
        character_id: Optional[int],
        party_id: Optional[int],
        campaign_run_id: Optional[str],
        world_event_type: str,
        importance: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> CharacterEventRecord:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into character_events (character_id, party_id, campaign_run_id, world_event_type, importance, payload)
                values (%s, %s, %s, %s, %s, %s)
                returning id, character_id, party_id, campaign_run_id, world_event_type, importance, payload, timestamp
                """,
                (character_id, party_id, campaign_run_id, world_event_type, importance, self._json(payload or {})),
            )
            row = cur.fetchone()
        return CharacterEventRecord(
            id=row[0],
            character_id=row[1],
            party_id=row[2],
            campaign_run_id=row[3],
            world_event_type=row[4],
            importance=row[5],
            payload=row[6],
            timestamp=row[7],
        )

    def store_adventure_summary(
        self,
        *,
        campaign_run_id: str,
        summary: Dict[str, Any],
        retcon_package: Dict[str, Any],
    ) -> AdventureSummaryRecord:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into adventure_summaries (campaign_run_id, summary, retcon_package)
                values (%s, %s, %s)
                on conflict (campaign_run_id) do update set summary=excluded.summary, retcon_package=excluded.retcon_package
                returning campaign_run_id, summary, retcon_package, created_at
                """,
                (campaign_run_id, self._json(summary), self._json(retcon_package)),
            )
            row = cur.fetchone()
        return AdventureSummaryRecord(
            campaign_run_id=row[0],
            summary=row[1],
            retcon_package=row[2],
            created_at=row[3],
        )

    def get_adventure_summary(self, run_id: str) -> AdventureSummaryRecord:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "select campaign_run_id, summary, retcon_package, created_at from adventure_summaries where campaign_run_id=%s",
                (run_id,),
            )
            row = cur.fetchone()
        if not row:
            raise NotFoundError(f"AdventureSummary for run {run_id} not found")
        return AdventureSummaryRecord(
            campaign_run_id=row[0],
            summary=row[1],
            retcon_package=row[2],
            created_at=row[3],
        )
