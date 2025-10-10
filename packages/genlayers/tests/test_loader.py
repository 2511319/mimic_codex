from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from genlayers.loader import load_generation_config


@pytest.fixture(autouse=True)
def reset_cache() -> Iterator[None]:
    load_generation_config.cache_clear()
    yield
    load_generation_config.cache_clear()


def test_load_generation_config(tmp_path: Path) -> None:
    config_path = tmp_path / "generation.yaml"
    config_path.write_text(
        """
profiles:
  scene:
    temperature: 0.7
    max_output_tokens: 500
    response_schema: scene.json
""",
        encoding="utf-8",
    )

    config = load_generation_config(config_path)

    assert config.require_profile("scene").max_output_tokens == 500


def test_missing_profile_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "generation.yaml"
    config_path.write_text(
        """
profiles: {}
""",
        encoding="utf-8",
    )

    config = load_generation_config(config_path)

    with pytest.raises(KeyError):
        config.require_profile("combat")
