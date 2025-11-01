from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pytest

from genlayers import (
    GenerationConfig,
    GenerationError,
    PromptProfile,
    SchemaLoader,
    StructuredGenerationEngine,
)
from genlayers.providers import LanguageModelProvider


class StubProvider(LanguageModelProvider):
    def __init__(self, outputs: list[str]) -> None:
        self._outputs = outputs
        self.prompts: list[str] = []

    def generate(
        self,
        *,
        prompt: str,
        temperature: float,
        max_output_tokens: int,
        schema: dict[str, Any],
        schema_name: str,
    ) -> str:
        self.prompts.append(prompt)
        if not self._outputs:
            raise GenerationError("No more outputs.")
        return self._outputs.pop(0)


@pytest.fixture()
def schema_dir(tmp_path: Path) -> Iterator[Path]:
    schema_path = tmp_path / "scene_schema.json"
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
    yield tmp_path


def make_engine(provider: LanguageModelProvider, schema_dir: Path) -> StructuredGenerationEngine:
    config = GenerationConfig(
        profiles={
            "scene": PromptProfile(
                temperature=0.7,
                max_output_tokens=400,
                response_schema="scene_schema.json",
            )
        }
    )
    loader = SchemaLoader(schema_dir)
    return StructuredGenerationEngine(config=config, schema_loader=loader, provider=provider, max_retries=2)


def test_generate_valid_payload(schema_dir: Path) -> None:
    provider = StubProvider(['{"title": "Moonlit scene"}'])
    engine = make_engine(provider, schema_dir)

    result = engine.generate("scene", "Describe the scene.")

    assert result == {"title": "Moonlit scene"}
    assert len(provider.prompts) == 1


def test_generate_retries_on_invalid_json(schema_dir: Path) -> None:
    provider = StubProvider(["not json", '{"title": "Valid"}'])
    engine = make_engine(provider, schema_dir)

    result = engine.generate("scene", "Describe the scene.")

    assert result == {"title": "Valid"}
    assert len(provider.prompts) == 2
    assert "Ошибка предыдущей попытки" in provider.prompts[-1]


def test_generate_raises_on_schema_error(schema_dir: Path) -> None:
    provider = StubProvider(['{"title": 42}'])
    engine = make_engine(provider, schema_dir)

    with pytest.raises(GenerationError):
        engine.generate("scene", "Describe the scene.")


def test_generate_propagates_provider_failure(schema_dir: Path) -> None:
    provider = StubProvider([])
    engine = make_engine(provider, schema_dir)

    with pytest.raises(GenerationError):
        engine.generate("scene", "Describe the scene.")
