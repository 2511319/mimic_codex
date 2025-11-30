from __future__ import annotations

import hmac
import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Iterator
from urllib.parse import quote_plus

import pytest
from fastapi.testclient import TestClient

from rpg_gateway_api.app import create_app
from rpg_gateway_api.auth.telegram import InitDataValidationError, InitDataValidator
from rpg_gateway_api.config import get_settings


@pytest.fixture(autouse=True)
def reset_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def build_init_data(bot_token: str, **overrides: str) -> str:
    base_user = {
        "id": 123456789,
        "is_bot": False,
        "first_name": "Test",
        "last_name": "User",
        "username": "test_user",
        "language_code": "ru",
    }
    now = datetime.now(tz=UTC)
    user_json = json.dumps(base_user, separators=(",", ":"), ensure_ascii=False)
    data: dict[str, str] = {
        "auth_date": str(int(now.timestamp())),
        "query_id": "AAAABBBBCCCC",
        "user": user_json,
    }
    data.update({k: str(v) for k, v in overrides.items()})
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), sha256).digest()
    hash_value = hmac.new(secret_key, data_check_string.encode("utf-8"), sha256).hexdigest()
    signed = {**data, "hash": hash_value}
    return "&".join(f"{key}={quote_plus(value)}" for key, value in signed.items())


def test_validator_accepts_valid_payload() -> None:
    bot_token = "123456:ABCDEF"
    init_data = build_init_data(bot_token)
    validator = InitDataValidator(bot_token=bot_token)

    payload = validator.validate(init_data)

    assert payload.user.username == "test_user"
    assert payload.query_id == "AAAABBBBCCCC"
    assert payload.auth_date <= datetime.now(tz=UTC)


def test_validator_rejects_invalid_hash() -> None:
    bot_token = "123456:ABCDEF"
    init_data = build_init_data(bot_token) + "tampered"
    validator = InitDataValidator(bot_token=bot_token)

    with pytest.raises(InitDataValidationError):
        validator.validate(init_data)


def test_validator_rejects_expired_payload() -> None:
    bot_token = "123456:ABCDEF"
    expired_timestamp = int((datetime.now(tz=UTC) - timedelta(minutes=10)).timestamp())
    init_data = build_init_data(bot_token, auth_date=str(expired_timestamp))
    validator = InitDataValidator(bot_token=bot_token, max_clock_skew=timedelta(minutes=5))

    with pytest.raises(InitDataValidationError):
        validator.validate(init_data)


def test_api_exchanges_init_data_for_token(monkeypatch: pytest.MonkeyPatch) -> None:
    bot_token = "123456:ABCDEF"
    monkeypatch.setenv("BOT_TOKEN", bot_token)
    monkeypatch.setenv("JWT_SECRET", "super-secret-key-123456")
    monkeypatch.setenv("JWT_TTL_SECONDS", "900")
    monkeypatch.setenv("API_VERSION", "1.0.0")
    init_data = build_init_data(bot_token)

    app = create_app()
    client = TestClient(app)

    response = client.post("/v1/auth/telegram", json={"initData": init_data})

    assert response.status_code == 200
    body = response.json()
    assert body["tokenType"] == "Bearer"
    assert body["user"]["username"] == "test_user"
    assert body["expiresIn"] == 900


def test_api_rejects_invalid_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    bot_token = "123456:ABCDEF"
    monkeypatch.setenv("BOT_TOKEN", bot_token)
    monkeypatch.setenv("JWT_SECRET", "super-secret-key-123456")
    monkeypatch.setenv("JWT_TTL_SECONDS", "900")
    monkeypatch.setenv("API_VERSION", "1.0.0")

    app = create_app()
    client = TestClient(app)

    tampered = build_init_data(bot_token) + "tampered"
    response = client.post("/v1/auth/telegram", json={"initData": tampered})

    assert response.status_code == 400
