from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from memory37.loader import load_knowledge_config


@pytest.fixture(autouse=True)
def reset_loader_cache() -> Iterator[None]:
    load_knowledge_config.cache_clear()
    yield
    load_knowledge_config.cache_clear()


def test_load_knowledge_config(tmp_path: Path) -> None:
    config_path = tmp_path / "knowledge.yaml"
    config_path.write_text(
        """
knowledge:
  srd:
    store: pgvector
    embedding:
      provider: openai
      model: text-embedding-3-large
      dimensions: 1536
    retrieval:
      mode: hybrid
      k_vector: 12
      k_keyword: 50
      fuse: rrf
""",
        encoding="utf-8",
    )

    config = load_knowledge_config(config_path)

    srd = config.require_domain("srd")
    assert srd.embedding.model == "text-embedding-3-large"
    assert srd.retrieval.mode == "hybrid"


def test_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_knowledge_config("does-not-exist.yaml")


def test_missing_domain_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "knowledge.yaml"
    config_path.write_text(
        """
knowledge:
  episode:
    store: pgvector
    embedding:
      provider: openai
      model: text-embedding-3-large
      dimensions: 768
    retrieval:
      mode: vector
      k_vector: 8
""",
        encoding="utf-8",
    )

    config = load_knowledge_config(config_path)

    with pytest.raises(KeyError):
        config.require_domain("srd")
