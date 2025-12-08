-- Core schema for gateway_api domain entities (players, characters, parties, campaigns).
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
create index if not exists idx_characters_player on characters(player_id);

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
create index if not exists idx_party_members_active on party_members(party_id) where left_at is null;

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
create index if not exists idx_episodes_template on episodes(campaign_template_id, ord);

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
create index if not exists idx_campaign_runs_party on campaign_runs(party_id);

create table if not exists character_campaign_runs (
    character_id bigint not null references characters(id) on delete cascade,
    campaign_run_id text not null references campaign_runs(id) on delete cascade,
    role text not null default 'MAIN',
    primary key (character_id, campaign_run_id)
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
create index if not exists idx_scene_states_run_order on scene_states(campaign_run_id, scene_order);

create table if not exists flag_states (
    id bigserial primary key,
    campaign_run_id text not null references campaign_runs(id) on delete cascade,
    key text not null,
    value jsonb,
    source_scene_id text
);
create index if not exists idx_flag_states_run on flag_states(campaign_run_id, key);

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
create index if not exists idx_character_events_character on character_events(character_id);
create index if not exists idx_character_events_campaign on character_events(campaign_run_id);

create table if not exists adventure_summaries (
    campaign_run_id text primary key references campaign_runs(id) on delete cascade,
    summary jsonb not null,
    retcon_package jsonb not null,
    created_at timestamptz not null default now()
);
