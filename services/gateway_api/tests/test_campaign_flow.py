from __future__ import annotations

from typing import Iterator, Optional

import pytest
from fastapi.testclient import TestClient
from jsonschema import validate

from rpg_gateway_api.app import create_app
from rpg_gateway_api.config import get_settings


def build_init_data(bot_token: str, *, user_id: int = 123456789, username: Optional[str] = "test_user") -> str:
    base_user = {
        "id": user_id,
        "is_bot": False,
        "first_name": "Test",
        "last_name": "User",
        "username": username,
        "language_code": "ru",
    }
    import hmac
    import json
    from hashlib import sha256
    from datetime import UTC, datetime
    from urllib.parse import quote_plus

    now = datetime.now(tz=UTC)
    user_json = json.dumps(base_user, separators=(",", ":"), ensure_ascii=False)
    data: dict[str, str] = {
        "auth_date": str(int(now.timestamp())),
        "query_id": "AAAABBBBCCCC",
        "user": user_json,
    }
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), sha256).digest()
    hash_value = hmac.new(secret_key, data_check_string.encode("utf-8"), sha256).hexdigest()
    signed = {**data, "hash": hash_value}
    return "&".join(f"{key}={quote_plus(value)}" for key, value in signed.items())


@pytest.fixture(autouse=True)
def reset_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def issue_token(client: TestClient, bot_token: str, *, user_id: int = 123456789) -> str:
    init_data = build_init_data(bot_token, user_id=user_id)
    response = client.post("/v1/auth/telegram", json={"initData": init_data})
    assert response.status_code == 200
    body = response.json()
    return body["accessToken"]


def test_full_campaign_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    bot_token = "123456:ABCDEF"
    monkeypatch.setenv("BOT_TOKEN", bot_token)
    monkeypatch.setenv("JWT_SECRET", "super-secret-key-123456")
    monkeypatch.setenv("JWT_TTL_SECONDS", "900")
    monkeypatch.setenv("API_VERSION", "1.0.0")
    monkeypatch.setenv("DATABASE_URL", "postgres://codex:codex@127.0.0.1:5433/codex")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    app = create_app()
    client = TestClient(app)
    token = issue_token(client, bot_token)
    headers = {"Authorization": f"Bearer {token}"}

    me_resp = client.get("/v1/me", headers=headers)
    assert me_resp.status_code == 200
    player = me_resp.json()["player"]
    assert player["telegramId"] == 123456789

    char_resp = client.post(
        "/v1/characters",
        json={"name": "Test Hero", "archetype": "warrior", "coreStats": {"hp": 12}},
        headers=headers,
    )
    assert char_resp.status_code == 201
    character_id = char_resp.json()["id"]
    char2_resp = client.post(
        "/v1/characters",
        json={"name": "Test Rogue", "archetype": "rogue", "coreStats": {"hp": 8}},
        headers=headers,
    )
    char2 = char2_resp.json()["id"]

    party_resp = client.post(
        "/v1/parties",
        json={"leaderCharacterId": character_id},
        headers=headers,
    )
    assert party_resp.status_code == 201
    party_id = party_resp.json()["id"]
    join_resp = client.post(
        f"/v1/parties/{party_id}/join",
        json={"characterId": char2},
        headers=headers,
    )
    assert join_resp.status_code == 200

    campaigns_resp = client.get("/v1/campaigns")
    assert campaigns_resp.status_code == 200
    campaigns = campaigns_resp.json()["items"]
    assert campaigns
    template_id = campaigns[0]["id"]

    start_resp = client.post(
        "/v1/campaign-runs",
        json={"campaignTemplateId": template_id, "partyId": party_id},
        headers=headers,
    )
    assert start_resp.status_code == 201
    run = start_resp.json()
    run_id = run["id"]
    assert run["currentScene"]["sceneOrder"] == 1
    assert run["status"] in ["IN_PROGRESS", "INIT", "SCENE"]

    status = run["status"]
    # прогоняем сцены до завершения
    while status != "COMPLETED":
        action_resp = client.post(
            f"/v1/campaign-runs/{run_id}/action",
            json={"actionType": "advance", "payload": {"choice": "continue"}},
            headers=headers,
        )
        assert action_resp.status_code == 200
        run = action_resp.json()
        status = run["status"]
        assert status in ["IN_PROGRESS", "COMPLETED", "SCENE", "RESOLVE", "APPLY_EFFECTS"]

    summary_resp = client.get(f"/v1/campaign-runs/{run_id}/summary", headers=headers)
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["adventureSummary"]["campaignRunId"] == run_id
    assert summary["retconPackage"]["campaignRunId"] == run_id
    import psycopg
    with psycopg.connect("postgres://codex:codex@127.0.0.1:5433/codex") as conn, conn.cursor() as cur:
        cur.execute("select count(*) from character_events where campaign_run_id=%s", (run_id,))
        assert cur.fetchone()[0] >= 1
    assert summary["adventureSummary"]["timeline"][0]["sceneType"]
    assert "outcome" in summary["adventureSummary"]["timeline"][0]["resultFlags"]
    # JSON Schema минимальная проверка
    summary_schema = {
        "type": "object",
        "properties": {
            "timeline": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["sceneType", "phase", "outcome"],
                    "properties": {
                        "sceneType": {"type": "string"},
                        "phase": {"type": "string"},
                        "outcome": {
                            "type": ["object", "null"],
                            "properties": {
                                "checks": {
                                    "type": ["array", "null"],
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "dc": {"type": ["number", "integer"]},
                                            "roll": {"type": ["number", "integer"]},
                                        },
                                        "required": ["dc", "roll"],
                                    },
                                }
                            },
                        },
                        "effects": {
                            "type": ["array", "null"],
                            "items": {
                                "type": "object",
                                "properties": {
                                    "hpDelta": {"type": ["number", "integer"], "optional": True},
                                    "relationDelta": {"type": ["number", "integer"], "optional": True},
                                    "statChanges": {"type": ["object", "null"]},
                                },
                            },
                        },
                    },
                },
            }
        },
    }
    validate(instance=summary["adventureSummary"], schema=summary_schema)
    # эффекты применились: relation вырос после социальных сцен
    import psycopg
    with psycopg.connect("postgres://codex:codex@127.0.0.1:5433/codex") as conn, conn.cursor() as cur:
        cur.execute("select core_stats->>'relation' from characters where id=%s", (character_id,))
        relation1 = int(cur.fetchone()[0] or 0)
        cur.execute("select core_stats->>'relation' from characters where id=%s", (char2,))
        relation2 = int(cur.fetchone()[0] or 0)
    assert relation1 >= 1 and relation2 >= 1


def test_action_forbidden_for_non_member(monkeypatch: pytest.MonkeyPatch) -> None:
    bot_token = "123456:ABCDEF"
    monkeypatch.setenv("BOT_TOKEN", bot_token)
    monkeypatch.setenv("JWT_SECRET", "super-secret-key-123456")
    monkeypatch.setenv("JWT_TTL_SECONDS", "900")
    monkeypatch.setenv("API_VERSION", "1.0.0")
    monkeypatch.setenv("DATABASE_URL", "postgres://codex:codex@127.0.0.1:5433/codex")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    app = create_app()
    client = TestClient(app)
    token_owner = issue_token(client, bot_token)
    headers_owner = {"Authorization": f"Bearer {token_owner}"}

    # создаём ресурсы от имени владельца
    character_id = client.post(
        "/v1/characters",
        json={"name": "Test Hero", "archetype": "warrior"},
        headers=headers_owner,
    ).json()["id"]
    party_id = client.post(
        "/v1/parties",
        json={"leaderCharacterId": character_id},
        headers=headers_owner,
    ).json()["id"]
    template_id = client.get("/v1/campaigns").json()["items"][0]["id"]
    run = client.post(
        "/v1/campaign-runs",
        json={"campaignTemplateId": template_id, "partyId": party_id},
        headers=headers_owner,
    ).json()
    run_id = run["id"]

    # неучастник пытается совершить действие
    token_intruder = issue_token(client, bot_token, user_id=987654321)
    headers_intruder = {"Authorization": f"Bearer {token_intruder}"}
    resp = client.post(
        f"/v1/campaign-runs/{run_id}/action",
        json={"actionType": "advance"},
        headers=headers_intruder,
    )
    assert resp.status_code == 403


def test_action_conflict_on_completed(monkeypatch: pytest.MonkeyPatch) -> None:
    bot_token = "123456:ABCDEF"
    monkeypatch.setenv("BOT_TOKEN", bot_token)
    monkeypatch.setenv("JWT_SECRET", "super-secret-key-123456")
    monkeypatch.setenv("JWT_TTL_SECONDS", "900")
    monkeypatch.setenv("API_VERSION", "1.0.0")
    monkeypatch.setenv("DATABASE_URL", "postgres://codex:codex@127.0.0.1:5433/codex")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    app = create_app()
    client = TestClient(app)
    token = issue_token(client, bot_token)
    headers = {"Authorization": f"Bearer {token}"}
    character_id = client.post(
        "/v1/characters",
        json={"name": "Hero", "archetype": "warrior"},
        headers=headers,
    ).json()["id"]
    party_id = client.post(
        "/v1/parties",
        json={"leaderCharacterId": character_id},
        headers=headers,
    ).json()["id"]
    template_id = client.get("/v1/campaigns").json()["items"][0]["id"]
    run = client.post(
        "/v1/campaign-runs",
        json={"campaignTemplateId": template_id, "partyId": party_id},
        headers=headers,
    ).json()
    run_id = run["id"]
    # завершить кампанию
    status = run["status"]
    while status != "COMPLETED":
        run = client.post(
            f"/v1/campaign-runs/{run_id}/action",
            json={"actionType": "advance"},
            headers=headers,
        ).json()
        status = run["status"]
    resp = client.post(
        f"/v1/campaign-runs/{run_id}/action",
        json={"actionType": "advance"},
        headers=headers,
    )
    assert resp.status_code == 409


def test_party_sync_broadcast(monkeypatch: pytest.MonkeyPatch) -> None:
    bot_token = "123456:ABCDEF"
    monkeypatch.setenv("BOT_TOKEN", bot_token)
    monkeypatch.setenv("JWT_SECRET", "super-secret-key-123456")
    monkeypatch.setenv("JWT_TTL_SECONDS", "900")
    monkeypatch.setenv("API_VERSION", "1.0.0")
    monkeypatch.setenv("DATABASE_URL", "postgres://codex:codex@127.0.0.1:5433/codex")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    class DummyNotifier:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def broadcast(self, campaign_id: str, event_type: str, payload: dict, trace_id: str | None = None) -> None:
            self.calls.append({"campaign_id": campaign_id, "event_type": event_type, "payload": payload, "trace_id": trace_id})

    app = create_app()
    dummy = DummyNotifier()
    app.state.campaign_engine._notifier = dummy  # type: ignore[attr-defined]
    client = TestClient(app)
    token = issue_token(client, bot_token)
    headers = {"Authorization": f"Bearer {token}"}
    character_id = client.post(
        "/v1/characters",
        json={"name": "Hero", "archetype": "warrior"},
        headers=headers,
    ).json()["id"]
    party_id = client.post(
        "/v1/parties",
        json={"leaderCharacterId": character_id},
        headers=headers,
    ).json()["id"]
    template_id = client.get("/v1/campaigns").json()["items"][0]["id"]
    run = client.post(
        "/v1/campaign-runs",
        json={"campaignTemplateId": template_id, "partyId": party_id},
        headers=headers,
    ).json()
    run_id = run["id"]
    # один шаг для вызова phase_applied
    client.post(
        f"/v1/campaign-runs/{run_id}/action",
        json={"actionType": "advance"},
        headers=headers,
    )
    event_types = [c["event_type"] for c in dummy.calls]
    assert "campaign.scene_started" in event_types
    assert "campaign.phase_applied" in event_types


def test_character_update_forbidden_for_other_player(monkeypatch: pytest.MonkeyPatch) -> None:
    bot_token = "123456:ABCDEF"
    monkeypatch.setenv("BOT_TOKEN", bot_token)
    monkeypatch.setenv("JWT_SECRET", "super-secret-key-123456")
    monkeypatch.setenv("JWT_TTL_SECONDS", "900")
    monkeypatch.setenv("API_VERSION", "1.0.0")
    monkeypatch.setenv("DATABASE_URL", "postgres://codex:codex@127.0.0.1:5433/codex")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    app = create_app()
    client = TestClient(app)
    token_owner = issue_token(client, bot_token, user_id=111)
    headers_owner = {"Authorization": f"Bearer {token_owner}"}
    character_id = client.post(
        "/v1/characters",
        json={"name": "Owner", "archetype": "mage"},
        headers=headers_owner,
    ).json()["id"]

    token_other = issue_token(client, bot_token, user_id=222)
    headers_other = {"Authorization": f"Bearer {token_other}"}
    resp = client.patch(
        f"/v1/characters/{character_id}",
        json={"name": "Hacker"},
        headers=headers_other,
    )
    assert resp.status_code == 403


def test_party_create_forbidden_with_foreign_character(monkeypatch: pytest.MonkeyPatch) -> None:
    bot_token = "123456:ABCDEF"
    monkeypatch.setenv("BOT_TOKEN", bot_token)
    monkeypatch.setenv("JWT_SECRET", "super-secret-key-123456")
    monkeypatch.setenv("JWT_TTL_SECONDS", "900")
    monkeypatch.setenv("API_VERSION", "1.0.0")
    monkeypatch.setenv("DATABASE_URL", "postgres://codex:codex@127.0.0.1:5433/codex")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    app = create_app()
    client = TestClient(app)
    token_owner = issue_token(client, bot_token, user_id=333)
    headers_owner = {"Authorization": f"Bearer {token_owner}"}
    character_id = client.post(
        "/v1/characters",
        json={"name": "Owner", "archetype": "mage"},
        headers=headers_owner,
    ).json()["id"]

    token_other = issue_token(client, bot_token, user_id=444)
    headers_other = {"Authorization": f"Bearer {token_other}"}
    resp = client.post(
        "/v1/parties",
        json={"leaderCharacterId": character_id},
        headers=headers_other,
    )
    assert resp.status_code == 403


def test_run_not_found_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    bot_token = "123456:ABCDEF"
    monkeypatch.setenv("BOT_TOKEN", bot_token)
    monkeypatch.setenv("JWT_SECRET", "super-secret-key-123456")
    monkeypatch.setenv("JWT_TTL_SECONDS", "900")
    monkeypatch.setenv("API_VERSION", "1.0.0")
    monkeypatch.setenv("DATABASE_URL", "postgres://codex:codex@127.0.0.1:5433/codex")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    app = create_app()
    client = TestClient(app)
    token = issue_token(client, bot_token)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/v1/campaign-runs/nonexistent", headers=headers)
    assert resp.status_code == 404
