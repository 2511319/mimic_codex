from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from genlayers.cli import app
from genlayers.settings import GenerationSettings


class DummyEngine:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, profile: str, prompt: str) -> dict[str, str]:
        self.calls.append((profile, prompt))
        return {"title": f"{profile}:{prompt}"}


def test_cli_generate(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "profiles.yaml"
    config_path.write_text("profiles: {}", encoding="utf-8")
    schema_root = tmp_path / "schemas"
    schema_root.mkdir()

    engine = DummyEngine()

    def fake_create_engine(settings: GenerationSettings) -> DummyEngine:
        fake_create_engine.settings = settings
        return engine

    monkeypatch.setattr("genlayers.cli.create_engine", fake_create_engine)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "generate",
            "--profile",
            "scene",
            "--prompt",
            "Hello",
            "--profiles-path",
            str(config_path),
            "--schema-root",
            str(schema_root),
            "--max-retries",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert engine.calls == [("scene", "Hello")]
    payload = json.loads(result.stdout.strip())
    assert payload["title"] == "scene:Hello"
    used_settings: GenerationSettings = fake_create_engine.settings
    assert used_settings.profiles_path == config_path
    assert used_settings.schema_root == schema_root
    assert used_settings.max_retries == 1
