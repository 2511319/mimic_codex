from __future__ import annotations

import json
from pathlib import Path

import jsonschema

SCHEMA_DIR = Path("contracts/jsonschema")
GOLDEN_DIR = Path("qa/golden")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def test_scene_response_matches_schema() -> None:
    schema = load_json(SCHEMA_DIR / "scene_response.schema.json")
    data = load_json(GOLDEN_DIR / "scene_response.json")
    jsonschema.validate(instance=data, schema=schema)

