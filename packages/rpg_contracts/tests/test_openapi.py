from __future__ import annotations

import pytest

from rpg_contracts import OPENAPI_PATH, load_openapi


def test_load_openapi_returns_dict() -> None:
    spec = load_openapi()

    assert spec["openapi"] == "3.1.0"
    assert "/v1/auth/telegram" in spec["paths"]


def test_missing_spec_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rpg_contracts.OPENAPI_PATH", OPENAPI_PATH.with_name("missing.yaml"))

    with pytest.raises(FileNotFoundError):
        load_openapi()
