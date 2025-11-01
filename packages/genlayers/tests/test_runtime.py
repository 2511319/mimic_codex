from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from genlayers import GenerationError, GenerationSettings, create_engine
from genlayers.providers import LanguageModelProvider


class StubProvider(LanguageModelProvider):
    def __init__(self, payload: str) -> None:
        self._payload = payload

    def generate(
        self,
        *,
        prompt: str,
        temperature: float,
        max_output_tokens: int,
        schema: dict[str, Any],
        schema_name: str,
    ) -> str:
        return self._payload


def _write_schema(schema_dir: Path) -> str:
    schema_dir.mkdir(parents=True, exist_ok=True)
    schema_path = schema_dir / "scene.json"
    schema_path.write_text(
        """
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["title"],
  "properties": {
    "title": { "type": "string" }
  },
  "additionalProperties": false
}
""",
        encoding="utf-8",
    )
    return schema_path.name


def _write_config(config_path: Path, schema_name: str) -> None:
    config_path.write_text(
        f"""
profiles:
  scene:
    temperature: 0.7
    max_output_tokens: 300
    response_schema: {schema_name}
""",
        encoding="utf-8",
    )


def test_create_engine_with_stub_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    schema_dir = tmp_path / "schemas"
    schema_name = _write_schema(schema_dir)
    config_path = tmp_path / "profiles.yaml"
    _write_config(config_path, schema_name)

    monkeypatch.chdir(tmp_path)

    settings = GenerationSettings(
        profiles_path=Path("profiles.yaml"),
        schema_root=Path("schemas"),
        max_retries=1,
    )
    provider = StubProvider('{"title": "Structured"}')

    engine = create_engine(settings, provider=provider)
    result = engine.generate("scene", "Describe the scene.")

    assert result == {"title": "Structured"}


def test_create_engine_requires_openai_sdk(tmp_path: Path) -> None:
    schema_dir = tmp_path / "schemas"
    schema_name = _write_schema(schema_dir)
    config_path = tmp_path / "profiles.yaml"
    _write_config(config_path, schema_name)

    settings = GenerationSettings(
        profiles_path=config_path,
        schema_root=schema_dir,
        openai_model="gpt-4.1",
    )

    with pytest.raises(GenerationError):
        create_engine(settings)
